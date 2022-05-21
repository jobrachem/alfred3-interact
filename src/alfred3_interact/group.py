"""
Functionality related to groups.
"""
import json
import random
import time
from traceback import format_exception
from itertools import chain
from collections import UserDict
from uuid import uuid4
from pathlib import Path
from typing import Iterator, List
from dataclasses import asdict, dataclass, field
from enum import Enum, auto
from abc import ABC, abstractproperty

from pymongo.collection import ReturnDocument

from .member import MemberManager
from .member import GroupMember
from ._util import MatchingError, BusyGroup
from ._util import saving_method
from .element import Chat


class GroupType:
    SEQUENTIAL = "sequential_group"
    PARALLEL = "parallel_group"


@dataclass
class GroupData:
    exp_id: str
    exp_version: str
    matchmaker_id: str
    roles: dict
    group_type: str
    spec_name: str
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
        sessions = list(chain(finished, pending))
        roles = (role for role, sid in self.roles.items() if sid not in sessions)
        return roles

    def assign(self, role: str, member: GroupMember):
        self.group.data.roles[role] = member.data.session_id
        member.data.role = role
        self.group.io.save()

    def next(self) -> str:
        role = next(self.open(), None)
        return role

    def shuffle(self):
        role_list = list(self.data.roles.items())
        random.shuffle(role_list)
        self.data.roles = dict(role_list)
        self.group.io.save()


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
        self.group.data = self.group.io.load()
        members = self.group.data.members
        active = list(self.manager.find_active_sessions(members))
        return len(active)

    @property
    def nfinished(self) -> int:
        self.group.data = self.group.io.load()
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
    """
    The group object holds members and keeps track of their roles.

    The group's main task is providing access to the group members
    via their roles. Most importantly, the group offers the attributes
    :attr:`.me` and :attr:`.you`. Beyond that, you can use dot notation,
    using any member's role like an attribute on the group. The group will
    return a :class:`.GroupMember` object for the member inhabiting that
    role.

    Typically, you will not initialize a group object yourself, but
    receive it as a result of the matchmaking process via :class:`.MatchMaker`

    See Also:
        See :class:`.GroupMember` for information about member objects.

    Examples:
        
        In this basic example, we access both group members through their
        roles and print their inputs on the last page::

            import alfred3 as al
            import alfred3_interact as ali

            exp = al.Experiment()

            @exp.setup
            def setup(exp):
                spec = ali.SequentialSpec("a", "b", nslots=10, name="spec1")
                exp.plugins.mm = ali.MatchMaker(spec, exp=exp)
            
            @exp.member
            class Demo:

                def on_exp_access(self):
                    self += al.TextEntry(leftlab="Enter some text", force_input=True, name="el1")
            
            @exp.member
            class Match(ali.WaitingPage):

                def wait_for(self):
                    group = self.exp.plugins.mm.match()
                    self.exp.plugins.group = group
                    return True
            
            @exp.member
            class Success(al.Page):

                def on_first_show(self):
                    group = self.exp.plugins.group
                    role = group.me.role
                    
                    self += al.Text(f"Successfully matched to role: {role}")

                    a = group.a
                    b = group.b

                    self += al.Text(f"Values of group member a: {a.values}")
                    self += al.Text(f"Values of group member b: {b.values}")
                    
    """
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

        self.exp.append_plugin_data_query(self._plugin_data_query)

    def _prepare_data(self, data: dict) -> dict:
        roles = data.get("roles", None)

        if not isinstance(roles, dict):
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
        """
        str: Unique group identification number.
        """
        return self.data.group_id

    @property
    def full(self) -> bool:
        """
        bool: Indicates whether all roles in the group are filled. Counts only
        active and finished members.
        """
        nactive = self.groupmember_manager.nactive
        nfinished = self.groupmember_manager.nfinished
        return nactive + nfinished == len(self.data.roles)

    def takes_members(self, ongoing_sessions_ok: bool = False):
        """
        Indicates whether the group accepts members.

        Returns:
            bool
        """
        open_roles = len(list(self.roles.open()))
        pending_roles = len(list(self.roles.pending()))

        pending_ok = pending_roles == 0 if not ongoing_sessions_ok else True

        return bool(open_roles) and pending_ok

    @property
    def finished(self) -> bool:
        """
        bool: Indicates whether all group members have finished their
        experiment sessions.
        """
        nfinished = self.groupmember_manager.nfinished
        return nfinished == len(self.data.roles)

    @property
    def nfinished(self) -> int:
        """
        int: Number of group members who have finished their experiment
        session.
        """
        return self.groupmember_manager.nfinished

    @property
    def nactive(self) -> int:
        """
        int: Number of group members currently working on the experiment.
        """
        return self.groupmember_manager.nactive

    @property
    def shared_data(self):
        """
        DEPRECATED shared group data dictionary.
        """
        self._shared_data._fetch()
        return self._shared_data

    @property
    def me(self) -> GroupMember:
        """
        GroupMember: :class:`.GroupMember` object for the own session.
        Useful to access the own role.
        """
        return self.groupmember_manager.me

    @property
    def you(self) -> GroupMember:
        """
        GroupMember: :class:`.GroupMember`  object for
        the *other* participant in a dyad (i.e. a two-member-group).
        """
        return self.groupmember_manager.you

    @property
    def spec_name(self) -> str:
        """
        str: Name of the spec that was used to create this group.
        """
        return self.data.spec_name

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
        A generator, iterating over *all* members of the group.
        Yields :class:`.GroupMember` objects.

        Yields:
            :class:`.GroupMember`
        
        See Also:
            - :meth:`.active_members`
            - :meth:`.other_members`
        
        """
        return self.groupmember_manager.members()

    def active_members(self) -> Iterator[GroupMember]:
        """
        A generator, iterating over all *active* members of the
        group. Yields :class:`.GroupMember` objects.

        Yields:
            :class:`.GroupMember`

        See Also:
            - :attr:`.GroupMember.active`
        """
        return self.groupmember_manager.active_members()

    def other_members(self) -> Iterator[GroupMember]:
        """
        A generator, iterating over the group members
        except for :attr:`.me`. Yields :class:`.GroupMember` objects.

        Yields:
            :class:`.GroupMember`        
        """
        return self.groupmember_manager.other_members()

    def active_other_members(self) -> Iterator[GroupMember]:
        """
        A generator, iterating over all *active* members of the
        group except for :attr:`.me`. Yields :class:`.GroupMember` objects.

        Yields:
            :class:`.GroupMember`
        
        See Also:
            - :attr:`.GroupMember.active`
        """
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
        self.io.save()
        return self
    
    def deactivate(self):
        with self as group:
            group.data.active = False
            group.io.save()

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
            tb = "".join(format_exception(exc_type, exc_value, tb))
            self.exp.log.error(
                (
                    f"There was an error when operating on {self}: {exc_value}."
                    "The group was deactivated.\n{tb}"
                )
            )
            self.data.active = False
            self.io.save()

        self.io.release()


class GroupManager:
    def __init__(self, matchmaker, group_type: str = None, spec_name: str = None):
        self.mm = matchmaker
        self.exp = self.mm.exp
        self.db = self.exp.db_misc
        self.saving_method = saving_method(self.exp)
        self.group_type = group_type
        self.spec_name = spec_name
        self.query = self._init_query()

    def _init_query(self):
        q = {
            "matchmaker_id": self.mm.name,
            "exp_id": self.exp.exp_id,
            "exp_version": self.mm.exp_version,
        }

        if self.spec_name is not None:
            q["spec_name"] = self.spec_name

        if self.group_type is not None:
            q["group_type"] = self.group_type

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
                    d = json.load(f)
                    version_matches = d["exp_version"] == self.mm.exp_version
                    spec_matches = d["spec_name"] == self.spec_name
                    if version_matches and spec_matches:
                        yield d

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
