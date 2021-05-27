"""
Functionality related to groups.
"""

import json
import random
import time
from pathlib import Path
from typing import Iterator
from dataclasses import asdict

from .member import MemberManager
from .member import GroupMember
from .data import GroupData
from .data import SharedGroupData
from ._util import MatchingError
from ._util import saving_method
from .element import Chat

class Group:
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
        self._save()
        self._shared_data._fetch()
        self.exp.append_plugin_data_query(self._plugin_data_query)
    
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
        return (m for m in self.active_or_finished_members() if m.session_id != self.exp.session_id)

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
                self.mm.log.warning(f"{member}, active: {member.active}")
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
            json.dump(asdict(self.data), f, sort_keys=True, indent=4)

    def _save_mongo(self):
        q = {}
        q["type"] = self.DATA_TYPE
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
            self.exp.log.error(f"There was an error or timeout when operating on {self}. The \
                group was deactivated.")
        self.data.busy = False
        self._save()


class GroupManager:
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