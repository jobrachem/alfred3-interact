"""
Functionality related to groups.
"""
import json
import random
import time
import traceback
from itertools import chain
from collections import UserDict
from uuid import uuid4
from pathlib import Path
from typing import Iterator, List
from dataclasses import asdict, dataclass, field

from pymongo.collection import ReturnDocument

from .member import MemberManager
from .member import GroupMember
from ._util import MatchingError, BusyGroup
from ._util import saving_method
from .element import Chat


@dataclass
class GroupData:
    exp_id: str
    exp_version: str
    matchmaker_id: str
    roles: dict
    group_id: str = field(default_factory=lambda: "group-" + uuid4().hex)
    members: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    active: bool = True
    busy: bool = False
    shared_data: dict = field(default_factory=dict)
    type: str = "match_group"


class SharedGroupData(UserDict):
    """
    Shared group data dictionary.

    This dictionary can be used just like a normal dictionary.
    Its benefit is that it synchronises data to a database.
    This way, the data is always automatically shared between all group
    members.
    """

    _ACCEPTED = (int, float, str, tuple, bool)

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self._db = self.group.exp.db_misc

        if self.group.data.shared_data:
            self.data = self.group.data.shared_data

        self.data["__group_id"] = self.group.data.group_id

    def _push_remote(self):
        doc = self._db.find_one_and_update(
            filter={"group_id": self.group.data.group_id},
            update={"$set": {"shared_data": self.data}},
            projection={"shared_data": True, "_id": False},
            return_document=ReturnDocument.AFTER,
        )
        if doc is not None:
            self.data = doc["shared_data"]

    def _fetch_remote(self):
        doc = self._db.find_one(
            filter={"group_id": self.group.data.group_id},
            projection={"shared_data": True, "_id": False},
        )
        if doc is not None:
            self.data = doc["shared_data"]

    def _push_local(self):
        self.group.data.shared_data = self.data
        self.group.io.save()

    def _fetch(self):
        if saving_method(self.group.exp) == "mongo":
            self._fetch_remote()

        self.data["__last_access"] = time.time()
        self._push()

    def _push(self):
        if saving_method(self.group.exp) == "mongo":
            self._push_remote()
        elif saving_method(self.group.exp) == "local":
            self._push_local()

    def last_change(self, format: str = "%Y-%m-%d, %X") -> str:
        return time.strftime(format, time.localtime(self.data["__last_change"]))

    def last_access(self, format: str = "%Y-%m-%d, %X") -> str:
        return time.strftime(format, time.localtime(self.data["__last_access"]))

    def _validate(self, key, value):

        if isinstance(value, self._ACCEPTED):
            return True

        else:
            msg = (
                f"You are setting or getting item '{key}', which refers "
                f"to an object of type {type(value)}. This is most likely a mutable type. "
                "Using a mutable object in SharedGroupData is very dangerous. "
                "You may end up losing data, because SharedGroupData can only write "
                "to the database when an item is set, not when it is changed. "
                "Please switch to using only immutable types, like "
                "tuple, str, int, float, and bool."
            )
            self.group.exp.log.warning(msg)

    def __getitem__(self, key):
        self._fetch()
        item = super().__getitem__(key)
        self._validate(key, item)
        return item

    def __setitem__(self, key, item):
        self._fetch()
        super().__setitem__(key, item)
        self.data["__last_change"] = time.time()
        self._push()
        self._validate(key, item)

    def __delitem__(self, key):
        self._fetch()
        super().__delitem__(key)
        self.data["__last_change"] = time.time()
        self._push()


class GroupHelper:
    def __init__(self, group):
        self.group = group
        self.mm = group.mm
        self.exp = group.exp


class GroupIO(GroupHelper):
    def __init__(self, group):
        super().__init__(group)
        self.saving_method = saving_method(self.exp)

    @property
    def db(self):
        return self.exp.db_misc

    @property
    def data(self):
        return self.group.data

    @property
    def query(self) -> dict:
        q = {}
        q["type"] = self.group.data.type
        q["group_id"] = self.group.data.group_id
        return q

    @property
    def path(self) -> Path:
        """
        Path: Path to group data file in offline group experiments.
        """
        parent = self.mm.io.path.parent
        return parent / f"group_{self.data.group_id}.json"

    def insert(self):
        if self.saving_method == "mongo":
            self._insert_mongo(asdict(self.data))
        elif self.saving_method == "local":
            self._insert_local(asdict(self.data))

    def _insert_mongo(self, insert: dict):
        self.db.find_one_and_update(self.query, {"$setOnInsert": insert}, upsert=True)

    def _insert_local(self, insert: dict):
        if not self.path.is_file():
            self._save_local(insert)

    def save(self):
        if self.saving_method == "mongo":
            self._save_mongo(asdict(self.data))
        elif self.saving_method == "local":
            self._save_local(asdict(self.data))

    def _save_mongo(self, data: dict):
        self.db.find_one_and_update(self.query, {"$set": data}, upsert=True)

    def _save_local(self, data: dict):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def load(self) -> GroupData:

        if self.saving_method == "mongo":
            data = self._load_mongo()
        elif self.saving_method == "local":
            data = self._load_local()

        if data:
            return GroupData(**data)

    def _load_mongo(self) -> dict:
        return self.db.find_one(self.query, {"_id": False})

    def _load_local(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as fp:
            return json.load(fp)

    def load_markbusy(self) -> GroupData:
        if self.saving_method == "mongo":
            data = self._load_markbusy_mongo()
        elif self.saving_method == "local":
            data = self._load_markbusy_local()

        if data:
            return GroupData(**data)

    def _load_markbusy_mongo(self) -> dict:
        q = self.query
        q["busy"] = False
        data = self.db.find_one_and_update(
            q,
            {"$set": {"busy": True}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": False},
        )

        return data

    def _load_markbusy_local(self):
        data = self._load_local()
        if not data["busy"]:
            data["busy"] = True
            self._save_local(data)
            return data
        else:
            return None

    def release(self):
        if self.saving_method == "mongo":
            self._release_mongo()
        elif self.saving_method == "local":
            self._release_local()

        self.group.data.busy = False

    def _release_mongo(self):
        self.db.find_one_and_update(self.query, {"$set": {"busy": False}})

    def _release_local(self):
        data = self._load_local()
        data["busy"] = False
        self._save_local(data)


class GroupRoles(GroupHelper):
    @property
    def manager(self):
        return self.group.manager

    @property
    def roles(self):
        return self.data.roles

    @property
    def data(self):
        return self.group.data

    def roles_of(self, sessions: str) -> Iterator[str]:
        roles = (role for role, sid in self.roles.items() if sid in sessions)
        return roles

    def finished(self) -> Iterator[str]:
        sessions = self.manager.find_finished_sessions(self.data.members)
        return self.roles_of(sessions)

    def pending(self) -> Iterator[str]:
        sessions = self.manager.find_active_sessions(self.data.members)
        return self.roles_of(sessions)

    def open(self) -> Iterator[str]:
        finished = self.manager.find_finished_sessions(self.data.members)
        pending = self.manager.find_active_sessions(self.data.members)
        sessions = chain(finished, pending)
        roles = (role for role, sid in self.roles.items() if sid not in sessions)
        return roles

    def assign(self, role: str, member: GroupMember):
        self.data.roles[role] = member.data.session_id
        member.data.role = role

    def next(self) -> str:
        role = next(self.open(), None)
        return role

    def shuffle(self):
        role_list = list(self.data.roles.items())
        random.shuffle(role_list)
        self.data.roles = dict(role_list)


class GroupMemberManager(GroupHelper):
    def __init__(self, group):
        super().__init__(group)
        self._me = None

    @property
    def manager(self):
        return self.group.manager

    @property
    def data(self):
        return self.group.data

    @property
    def me(self) -> GroupMember:
        if not self._me:
            me = self.manager.find([self.exp.session_id])
            self._me = next(me)

        return self._me

    @property
    def you(self) -> GroupMember:
        """
        GroupMember: :class:`.GroupMember`  object for
        the *other* participant in a dyad (i.e. a two-member-group).
        """
        if len(self.data.roles) > 2:
            raise MatchingError(
                "Can't use 'you' for groups with more than 2 slots, because it is ambiguous. Use the 'other_members()' generator instead, or access members based on their roles."
            )
        else:
            you = next(self.active_other_members(), None)
            if not you:
                you = next(self.other_members(), None)
            return you

    @property
    def nactive(self) -> int:
        self.group.load()
        members = self.group.data.members
        active = list(self.manager.find_active_sessions(members))
        return len(active)

    @property
    def nfinished(self) -> int:
        self.group.load()
        members = self.group.data.members
        finished = list(self.manager.find_finished_sessions(members))
        return len(finished)

    def get_member_by_role(self, role: str) -> GroupMember:
        """
        GroupMember: Returns the :class:`.GroupMember` that inhabits the
        given role.
        """
        if not role in self.data.roles:
            raise AttributeError(f"Role '{role}' not found in {self}.")

        active = (m for m in self.active_members() if m.data.role == role)
        member = next(active, None)

        if not member:
            inactive = (m for m in self.members() if m.data.role == role)
            member = next(inactive, None)

        return member

    def members(self) -> Iterator[GroupMember]:
        return self.manager.find(self.data.members)

    def active_members(self) -> Iterator[GroupMember]:
        sessions = self.manager.find_active_sessions(self.data.members)
        return self.manager.find(sessions)

    def other_members(self) -> Iterator[GroupMember]:
        for member in self.members():
            if member.data.session_id != self.exp.session_id:
                yield member

    def active_other_members(self) -> Iterator[GroupMember]:
        sessions = self.manager.find_active_sessions(self.data.members)
        for member in self.manager.find(sessions):
            if not member.data.session_id == self.exp.session_id:
                yield member

    @property
    def oldest_save(self) -> float:
        save_times = [m.info.last_save for m in self.active_members()]
        return min(save_times)


class Group:
    def __init__(self, matchmaker, **data):
        self.mm = matchmaker
        self.exp = self.mm.exp

        self.data = GroupData(**self._prepare_data(data))
        self.io = GroupIO(self)
        self.manager = MemberManager(self.mm)
        self.roles = GroupRoles(self)
        self.groupmember_manager = GroupMemberManager(self)

        self._shared_data = SharedGroupData(group=self)
        self.data.shared_data = self.shared_data.data
        self.io.insert()

    def _prepare_data(self, data: dict) -> dict:
        roles = data.get("roles", None)

        if roles is None:
            roles = {role: None for role in self.mm.roles}
        elif not isinstance(roles, dict):
            roles = {role: None for role in roles}

        exp_id = data.get("exp_id", None)
        mm_id = data.get("matchmaker_id", None)

        data["roles"] = roles
        data["exp_id"] = exp_id if exp_id is not None else self.exp.exp_id
        data["matchmaker_id"] = mm_id if mm_id is not None else self.mm.matchmaker_id

        if not "exp_version" in data:
            data["exp_version"] = self.mm.exp_version

        data.pop("_id", None)

        return data

    @property
    def _plugin_data_query(self):
        f = {"exp_id": self.exp.exp_id, "type": self.data.type}

        q = {}
        q["title"] = "Group Data"
        q["type"] = self.data.type
        q["query"] = {"filter": f}
        q["encrypted"] = False

        return q

    @property
    def group_id(self) -> str:
        return self.data.group_id

    @property
    def full(self) -> bool:
        nactive = self.groupmember_manager.nactive
        nfinished = self.groupmember_manager.nfinished
        return nactive + nfinished == len(self.data.roles)

    def takes_members(self, ongoing_sessions_ok: bool = False):
        open_roles = len(list(self.roles.open()))
        pending_roles = len(list(self.roles.pending()))

        pending_ok = pending_roles == 0 if not ongoing_sessions_ok else True

        return bool(open_roles) and pending_ok

    @property
    def finished(self) -> bool:
        nfinished = self.groupmember_manager.nfinished
        return nfinished == len(self.data.roles)

    @property
    def nfinished(self):
        return self.groupmember_manager.nfinished

    @property
    def nactive(self):
        return self.groupmember_manager.nactive

    @property
    def shared_data(self):
        self._shared_data._fetch()
        return self._shared_data

    @property
    def me(self) -> GroupMember:
        return self.groupmember_manager.me

    @property
    def you(self) -> GroupMember:
        return self.groupmember_manager.you

    def load(self):
        self.data = self.io.load()

    def chat(self, **kwargs) -> Chat:
        """
        Shortcut for creating a group chat.

        Args:
            **kwargs: Any argument accepted by :class:`.Chat` can be used,
                including *chat_id* and *nickname*. Specifying the latter
                two will simply override the defaults.

        See Also:
            The basic functionality is provided in the :class:`.Chat`
            element, which can be used on its own.

        Returns:
            Chat: A chat element in which the default for the chat id is
            set to the group id and the default for the nickname is set
            to each member's role.
        """
        chat_id = kwargs.pop("chat_id", self.group_id)
        nickname = kwargs.pop("nickname", self.me.role)
        return Chat(chat_id=chat_id, nickname=nickname, **kwargs)

    def members(self) -> Iterator[GroupMember]:
        return self.groupmember_manager.members()

    def active_members(self) -> Iterator[GroupMember]:
        return self.groupmember_manager.active_members()

    def other_members(self) -> Iterator[GroupMember]:
        return self.groupmember_manager.other_members()

    def active_other_members(self) -> Iterator[GroupMember]:
        return self.groupmember_manager.active_other_members()

    def __repr__(self):
        roles = str(list(self.data.roles.keys()))
        nmembers = self.groupmember_manager.nactive if self.data.members else 0
        shortid = self.data.group_id[-4:]

        return f"{type(self).__name__}(roles={roles}, active members={nmembers}, id='{shortid}')"

    def __getattr__(self, name):
        return self.groupmember_manager.get_member_by_role(role=name)

    def __getitem__(self, key):
        return self.groupmember_manager.get_member_by_role(role=key)

    def __eq__(self, other):
        return (type(self) == type(other)) and (self.data.group_id == other.data.group_id)

    def __iadd__(self, member):
        # TODO: Add group ID to member's experiment data

        if member.data.session_id in self.data.members:
            return self

        member.data.group_id = self.data.group_id
        self.data.members.append(member.data.session_id)
        return self

    def __enter__(self):
        data = self.io.load_markbusy()
        i = 0

        while not data:
            i += 1
            if i > 5:
                break
            time.sleep(1)
            data = self.io.load_markbusy()

        if not data:
            raise BusyGroup

        self.data = data
        return self

    def __exit__(self, exc_type, exc_value, tb):
        if exc_type:
            self.exp.log.error(
                f"There was an error when operating on {self}: {exc_value}. The group was deactivated. \n{traceback.format_exc()}"
            )
            self.data.active = False
            self.io.save()

        self.io.release()


class GroupManager:
    def __init__(self, matchmaker, type: str):
        self.mm = matchmaker
        self.exp = self.mm.exp
        self.db = self.exp.db_misc
        self.saving_method = saving_method(self.exp)
        self.type = type

    @property
    def query(self):
        q = {}
        q["type"] = self.type
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.mm.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        return q

    @property
    def path(self):
        return self.mm.io.path.parent

    def groups(self) -> Iterator[Group]:
        if self.saving_method == "local":
            data = self._local_groups()
        elif self.saving_method == "mongo":
            data = self._mongo_groups()

        for gdata in data:
            return Group(self.mm, **gdata)

    def _local_groups(self) -> Iterator[dict]:
        for fpath in self.path.iterdir():
            if fpath.is_dir():
                continue

            elif not fpath.name.startswith("group"):
                continue

            else:
                with open(fpath, "r", encoding="utf-8") as f:
                    gdata = json.load(f)
                    if gdata["exp_version"] == self.mm.exp_version:
                        yield gdata

    def _mongo_groups(self) -> Iterator[dict]:
        return self.db.find(self.query)

    def next(self, ongoing_sessions_ok: bool) -> Group:
        groups = list(self.takes_members(ongoing_sessions_ok=ongoing_sessions_ok))

        nfinished = [g.groupmember_manager.nfinished for g in groups]
        i = nfinished.index(max(nfinished))

        return groups[i]

    def takes_members(self, ongoing_sessions_ok: bool) -> Iterator[Group]:
        for group in self.active():
            if group.takes_members(ongoing_sessions_ok):
                yield group

    def active(self) -> Iterator[Group]:
        if self.saving_method == "local":
            data = self._active_local()
        elif self.saving_method == "mongo":
            data = self._active_mongo()

        for gdata in data:
            yield Group(self.mm, **gdata)

    def _active_local(self):
        for data in self._local_groups():
            if data["active"]:
                yield data

    def _active_mongo(self) -> Iterator[Group]:
        q = self.query
        q["active"] = True

        return self.db.find(q)

    def find(self, groups: List[str]) -> Iterator[Group]:
        if self.saving_method == "mongo":
            data = self._find_mongo(groups)
        elif self.saving_method == "local":
            data = self._find_local(groups)

        for gdata in data:
            return Group(self.mm, **gdata)

    def _find_mongo(self, groups: List[str]) -> Iterator[dict]:
        q = self.query
        q["group_id"] = {"$in": groups}
        return self.db.find(q)

    def _find_local(self, groups: List[str]) -> Iterator[dict]:
        for data in self._local_groups():
            if data["group_id"] in groups:
                yield data

    def find_one(self, group_id: str) -> Group:
        if self.saving_method == "mongo":
            data = self._find_one_mongo(group_id)
        elif self.saving_method == "local":
            data = self._find_one_local(group_id)

        if not data:
            return

        return Group(self.mm, **data)

    def _find_one_mongo(self, group_id: str) -> dict:
        q = self.query
        q["group_id"] = group_id
        return self.db.find_one(q)

    def _find_one_local(self, group_id: str) -> dict:
        return next(self._find_local([group_id]), None)


class GroupOld:
    """
    The group object holds members and keeps track of their roles.

    The group object's main task is providing access to the group members
    via their roles. Most importantly, the group offers the attributes
    :attr:`.me` and :attr:`.you`. Beyond that, you can use dot notation,
    using any member's role like an attribute on the group. The group will
    return a :class:`.GroupMember` object for the member inhabiting that
    role::

        import alfred3 as al
        from alfred3_interact import MatchMaker

        exp = al.Experiment()

        @exp.setup
        def setup(exp):
            mm = MatchMaker("a", "b", exp=exp)
            exp.plugins.group = mm.match_stepwise()
            print(exp.plugins.group.a) # Accessing the GroupMember with role "a"

        exp += al.Page(name="demo")

    See Also:
        For more details, refer to the :class:`.MatchMaker` documentation.

    """

    DATA_TYPE = "match_group"

    def __init__(self, matchmaker, **kwargs):
        kwargs.pop("_id", None)
        self.mm = matchmaker
        self.exp = self.mm.exp
        self.manager = MemberManager(matchmaker=self.mm)
        exp_id = kwargs.get("exp_id", None)
        kwargs["exp_id"] = exp_id if exp_id is not None else self.exp.exp_id
        mm_id = kwargs.get("matchmaker_id", None)
        kwargs["matchmaker_id"] = mm_id if mm_id is not None else self.mm.matchmaker_id
        if not "exp_version" in kwargs:
            kwargs["exp_version"] = self.mm.exp_version
        self.data = GroupData(**kwargs)
        self._operation_start = None

        self._shared_data = SharedGroupData(group=self)
        self._shared_data._fetch()
        self.exp.append_plugin_data_query(self._plugin_data_query)
        self._save()

    @property
    def _plugin_data_query(self):
        f = {"exp_id": self.exp.exp_id, "type": "match_group"}

        q = {}
        q["title"] = "Group Data"
        q["type"] = "match_group"
        q["query"] = {"filter": f}
        q["encrypted"] = False

        return q

    @property
    def shared_data(self) -> SharedGroupData:
        """
        SharedGroupData: Gives access to the group's shared data dictionary,
        which will always automatically synchronize data for all group
        members.

        See Also:
            :class:`.SharedGroupData`
        """
        self._shared_data._fetch()
        return self._shared_data

    @property
    def path(self) -> Path:
        """
        Path: Path to group data file in offline group experiments.
        """
        parent = self.mm.io.path.parent
        return parent / f"group_{self.group_id}.json"

    @property
    def full(self) -> bool:
        """
        bool: Indicates whether the group is full or not. Counts only
        active members.
        """
        return len(list(self.active_or_finished_members())) == len(self.data.roles)

    @property
    def you(self) -> GroupMember:
        """
        GroupMember: :class:`.GroupMember`  object for
        the *other* participant in a dyad (i.e. a two-member-group).
        """
        if len(self.data.roles) > 2:
            raise MatchingError(
                "Can't use 'you' for groups with more than 2 slots, because it is ambiguous. Use the 'other_members()' generator instead, or access members based on their roles."
            )
        else:
            return next(self.other_members())

    @property
    def me(self) -> GroupMember:
        """
        GroupMember: :class:`.GroupMember` object for the own session.
        Useful to access the own role.
        """
        return next(m for m in self.members() if m.session_id == self.exp.session_id)

    def chat(self, **kwargs) -> Chat:
        """
        Shortcut for creating a group chat.

        Args:
            **kwargs: Any argument accepted by :class:`.Chat` can be used,
                including *chat_id* and *nickname*. Specifying the latter
                two will simply override the defaults.

        See Also:
            The basic functionality is provided in the :class:`.Chat`
            element, which can be used on its own.

        Returns:
            Chat: A chat element in which the default for the chat id is
            set to the group id and the default for the nickname is set
            to each member's role.
        """
        chat_id = kwargs.pop("chat_id", self.group_id)
        nickname = kwargs.pop("nickname", self.me.role)
        return Chat(chat_id=chat_id, nickname=nickname, **kwargs)

    def members(self) -> Iterator[GroupMember]:
        """
        Iterator: A generator, iterating over *all* members of the group.
        Yields :class:`.GroupMember` objects.

        See Also:
            - :meth:`.active_members`
            - :meth:`.other_members`
        """
        return (self.manager.find(mid) for mid in self.data.members)

    def active_members(self) -> Iterator[GroupMember]:
        """
        Iterator: A generator, iterating over all *active* members of the
        group. Yields :class:`.GroupMember` objects.

        See Also:
            - :attr:`.GroupMember.active`
        """
        return (member for member in self.members() if member.active)

    def active_or_finished_members(self) -> Iterator[GroupMember]:
        for member in self.members():
            if member.active or member.finished:
                yield member

    def other_members(self) -> Iterator[GroupMember]:
        """
        Iterator: A generator, iterating over the *active* group members
        except for :attr:`.me`. Yields :class:`.GroupMember` objects.
        """
        return (
            m for m in self.active_or_finished_members() if m.session_id != self.exp.session_id
        )

    def get_member_by_role(self, role: str) -> GroupMember:
        """
        GroupMember: Returns the :class:`.GroupMember` that inhabits the
        given role.
        """
        if not role in self.data.roles:
            raise AttributeError(f"Role '{role}' not found in {self}.")

        return next(m for m in self.active_members() if m.role == role)

    def get_member_by_id(self, id: str) -> GroupMember:
        """
        GroupMember: Returns the :class:`.GroupMember` belonging to the
        experiment session with session id *id*.

        Raises:
            AttributeError: If there is no group member of the given id.
        """
        if not id in self.data.members:
            raise AttributeError(f"Member with id '{id}' not found in {self}.")

        return next(m for m in self.members() if m.data.session_id == id)

    def ongoing_roles(self) -> Iterator[str]:
        """
        Iterator: Iterates over roles for which sessions are currently
        in progess.
        """
        for role, member_id in self.data.roles.items():
            if member_id is None:
                continue
            else:
                member = self.manager.find(id=member_id)
                if member.active:
                    yield role

    def open_roles(self) -> Iterator[str]:
        """
        Iterator: Iterates over open roles (str).
        """
        for role, member_id in self.data.roles.items():
            if member_id is None:
                yield role
            else:
                member = self.manager.find(id=member_id)
                if member.finished:
                    continue
                elif not member.active:
                    yield role

    def _shuffle_roles(self):
        role_list = list(self.data.roles.items())
        random.shuffle(role_list)
        self.data.roles = dict(role_list)

    def _assign_all_roles(self, to_members):
        if not self.full:
            raise MatchingError("Can't assign all roles if group is not full.")

        if not len(list(self.open_roles())) == len(self.data.roles):
            raise MatchingError("Some roles are already assigned, can't assign all roles.")

        for role, member in zip(self.data.roles.keys(), to_members):
            member.data.role = role
            self.data.roles[role] = member.data.session_id

    def _assign_next_role(self, to_member: GroupMember):
        role = next(self.open_roles())
        to_member.data.role = role
        self.data.roles[role] = to_member.data.session_id

    def _save(self):
        if saving_method(self.exp) == "local":
            self._save_local()
        elif saving_method(self.exp) == "mongo":
            self._save_mongo()

    def _save_local(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.data), f, indent=4)

    def _save_mongo(self):
        q = {}
        q["type"] = self.data.type
        q["group_id"] = self.group_id
        data = self.exp.db_misc.find_one_and_replace(q, asdict(self.data), upsert=True)
        return data

    def __iadd__(self, member):
        # TODO: Add group ID to member's experiment data

        if member.data.session_id in self.data.members:
            return self

        member.data.group_id = self.data.group_id
        self.data.members.append(member.data.session_id)
        return self

    def __eq__(self, other):
        return (type(self) == type(other)) and (self.data.group_id == other.data.group_id)

    def __str__(self):
        roles = str(list(self.data.roles.keys()))
        nactive = len(list(self.active_members()))
        nroles = len(self.data.roles)

        return f"{type(self).__name__}(roles={roles}, {nactive}/{nroles} roles filled, id='{self.group_id[-4:]}')"

    def __repr__(self):
        return self.__str__()

    def __getattr__(self, name):
        try:
            return getattr(self.data, name)
        except AttributeError:
            return self.get_member_by_role(role=name)

    def __enter__(self):
        self.data.busy = True
        self._operation_start = time.time()
        self._save()  # returns data, if group was not busy before but is now busy
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        timeout = time.time() - self._operation_start > self.mm.group_timeout
        if timeout or exc_type:
            self.data.active = False
            self.exp.log.error(
                f"There was an error or timeout when operating on {self}. The \
                group was deactivated."
            )
        self.data.busy = False
        self._save()


class GroupManagerOld:
    def __init__(self, matchmaker):
        self.mm = matchmaker
        self.exp = self.mm.exp

    @property
    def query(self):
        q = {}
        q["type"] = Group.DATA_TYPE
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.mm.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        return q

    @property
    def path(self):
        return self.mm.io.path.parent

    def groups(self) -> Iterator[Group]:
        if saving_method(self.exp) == "local":
            return self._local_groups()
        elif saving_method(self.exp) == "mongo":
            return self._mongo_groups()
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def active(self):
        return (g for g in self.groups() if g.active)

    def notfull(self, ongoing_sessions_ok=True) -> Iterator[Group]:
        if ongoing_sessions_ok:
            for g in self.active():
                if not g.full:
                    yield g
        else:
            for g in self.active():
                if not g.full and not any(g.ongoing_roles()):
                    yield g

    def find(self, id: str):
        try:
            return next(g for g in self.groups() if g.data.group_id == id)
        except StopIteration:
            raise MatchingError("The group you are looking for was not found.")

    def _local_groups(self):
        for fpath in self.path.iterdir():
            if fpath.is_dir():
                continue

            elif not fpath.name.startswith("group"):
                continue

            else:
                with open(fpath, "r", encoding="utf-8") as f:
                    gdata = json.load(f)
                    if gdata["exp_version"] == self.mm.exp_version:
                        yield Group(matchmaker=self.mm, **gdata)

    def _mongo_groups(self):
        for doc in self.exp.db_misc.find(self.query):
            yield Group(matchmaker=self.mm, **doc)
