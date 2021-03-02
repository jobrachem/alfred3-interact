import copy
import json
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Iterator, List

from alfred3.alfredlog import QueuedLoggingInterface
from alfred3.data_manager import DataManager as dm

from ._util import MatchingError, saving_method
from .data import SharedGroupData


@dataclass
class GroupMemberData:
    session_id: str
    exp_id: str
    exp_version: str
    match_size: int
    match_maker_name: str
    match_group: str = None
    match_role: str = None
    timestamp: float = time.time()
    assignment_ongoing: bool = False
    member_active: bool = True
    type: str = "match_member"


class GroupMember:
    def __init__(self, data: dict = None, exp=None):
        self.data = GroupMemberData(**data)
        self._exp = exp
        p = self._exp.config.get("interact", "path", fallback="save/interact")
        self.path = self._exp.subpath(p) / "members" / f"member_{self.session_id}.json"
        self.path.parent.mkdir(exist_ok=True, parents=True)

        psave = self._exp.config.get("local_saving_agent", "path")
        self._save_path = self._exp.subpath(psave)

    @classmethod
    def _from_exp(cls, exp, **kwargs):
        kwargs_version = kwargs.get("exp_version", None)
        version = kwargs_version if kwargs_version is not None else exp.version
        data = {
            **{"session_id": exp.session_id, "exp_id": exp.exp_id, "exp_version": version},
            **kwargs,
        }
        return cls(data=data, exp=exp)

    @property
    def exp(self):
        return self._exp

    def __getattr__(self, name):
        return getattr(self.data, name)

    def _save(self):
        if saving_method(self._exp) == "local":
            with open(self.path, "w") as p:
                json.dump(asdict(self.data), p, indent=4, sort_keys=True)
        elif saving_method(self._exp) == "mongo":
            query = {"type": "match_member", "session_id": self.session_id}
            self._exp.db_misc.find_one_and_replace(query, asdict(self.data), upsert=True)
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def _reload(self):
        if saving_method(self._exp) == "local":
            with open(self.path, "r") as p:
                return GroupMember(data=json.load(p), exp=self._exp)
        elif saving_method(self._exp) == "mongo":
            query = {"type": "match_member", "session_id": self.session_id}
            d = self._exp.db_misc.find_one(query)
            d.pop("_id")
            return GroupMember(data=d, exp=self._exp)
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def _set_assignment_status(self, status: bool):
        self.data.assignment_ongoing = status
        self._save()

    def active(self, timeout: int):
        return self.member_active and time.time() - self.timestamp < timeout
    
    def deactivate(self):
        self.member_active = False
        self._save()

    def __repr__(self):
        return f"{type(self).__name__}(role='{self.match_role}', session_id='{self.session_id}')"

    @property
    def values(self):
        session_data = self.session_data
        if session_data:
            return {
                k: v
                for k, v in dm.flatten(session_data).items()
                if k not in dm._metadata and k not in dm.client_data
            }
        else:
            return None

    @property
    def session_data(self) -> dict:
        if self.session_id.startswith("placeholder"):
            return None
        if saving_method(self._exp) == "local":
            iterator = dm.iterate_local_data(dm.EXP_DATA, directory=self._save_path)
        elif saving_method(self._exp) == "mongo":
            iterator = dm.iterate_mongo_data(
                exp_id=self.exp_id, data_type=dm.EXP_DATA, secrets=self._exp.secrets
            )
        else:
            return None
        for data in iterator:
            if data["exp_session_id"] == self.session_id:
                return data

    @property
    def move_history(self):
        session_data = self.session_data
        if session_data:
            return session_data.get("exp_move_history", None)

    @property
    def metadata(self):
        session_data = self.session_data
        if session_data:
            return {k: v for k, v in dm.flatten(session_data).items() if k in dm._metadata}
        else:
            return None

    @property
    def client_data(self):
        session_data = self.session_data
        if session_data:
            return {k: v for k, v in dm.flatten(session_data).items() if k in dm.client_data}
        else:
            return None

    @property
    def role(self):
        return self.data.match_role

    

@dataclass
class GroupData:
    group_id: str
    exp_id: str
    exp_version: str
    match_maker_name: str
    match_size: int
    match_roles: dict
    match_time: float = time.time()
    type: str = "match_group"
    members: list = None
    member_timeout: int = None
    assignment_ongoing: bool = True
    expired: bool = False
    group_timeout: int = 60 * 60 * 1
    shared_data: dict = field(default_factory=lambda: {})


class Group:
    def __init__(self, data: dict, exp):
        self.data = GroupData(**data)
        self.exp = exp
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)

        try:
            self.data.members = [GroupMember(data=d, exp=exp) for d in self.data.members]
        except TypeError:
            self.data.members = []

        p = self.exp.config.get("interact", "path", fallback="save/interact")
        self.path = self.exp.subpath(p) / f"group_{self.group_id}.json"
        self.path.parent.mkdir(exist_ok=True, parents=True)

        self._operation_start = None
        self._shared_data = SharedGroupData(group=self)
        self._save()
        self._shared_data._fetch()
    
    @property
    def shared_data(self):
        self._shared_data._fetch()
        return self._shared_data

    @property
    def other_members(self) -> List[GroupMember]:
        others = [m for m in self.members if m.session_id != self.exp.session_id]
        if others:
            return others
        else:
            data = {}
            data["exp_id"] = self.exp.exp_id
            data["match_group"] = self.group_id
            data["exp_version"] = self.exp_version
            data["match_size"] = self.match_size
            data["match_maker_name"] = self.match_maker_name
            data["timestamp"] = 0
            others = []
            for role in self.open_roles():
                data["session_id"] = f"placeholder_{role}"
                data["match_role"] = role
                others.append(GroupMember(data=data, exp=self.exp))
            return others

    @property
    def you(self) -> GroupMember:
        if self.match_size > 2:
            raise MatchingError(
                "Can't use 'you' for groups with more than 2 slots. Use 'other_members' instead."
            )

        return self.other_members[0]

    @property
    def me(self):
        print(self.members)
        print(self.exp.session_id)
        return [m for m in self.members if m.session_id == self.exp.session_id][0]

    @property
    def full(self) -> bool:
        return self.match_size == len(self.members)

    @classmethod
    def _from_exp(cls, exp, **kwargs):
        kwargs_version = kwargs.get("exp_version", None)
        version = kwargs_version if kwargs_version is not None else exp.version

        data = {**{"exp_id": exp.exp_id, "exp_version": version}, **kwargs}
        return cls(data=data, exp=exp)

    @classmethod
    def _from_id(cls, group_id: str, exp):
        query = {"type": "match_group", "group_id": group_id}
        d = exp.db_misc.find_one(query)
        d.pop("_id")
        return cls(data=d, exp=exp)

    def get_one_by_role(self, role: str) -> GroupMember:
        """
        GroupMember: Returns the first member with the given role.
        """
        try:
            return self.get_many_by_role(role=role)[0]
        except IndexError:
            return None

    def get_many_by_role(self, role: str) -> List[GroupMember]:
        """
        list: List of all GroupMembers with the given role.
        """
        if not role in self.match_roles:
            raise AttributeError(f"Role '{role}' not found in {self}.")

        return [m for m in self.members if m.match_role == role]

    def get_one_by_id(self, session_id: str) -> GroupMember:
        try:
            return [m for m in self.members if m.session_id == session_id][0]
        except IndexError:
            return None

    def get_many_by_id(self, session_id: str) -> List[GroupMember]:
        return [m for m in self.members if m.session_id == session_id]

    def open_roles(self) -> Iterator[str]:

        return (role for role, member_id in self.match_roles.items() if member_id is None)

    def _discard_expired_members(self):
        if self.member_timeout is not None:
            self.data.members = [m for m in self.members if m.active(self.member_timeout)]
            member_ids = [m.session_id for m in self.members]
            for role, sid in self.match_roles.items():
                if sid not in member_ids:
                    self.match_roles[role] = None

    def _assigned_roles(self) -> Iterator[str]:
        return (role for role, member_id in self.match_roles.items() if member_id is not None)

    def _assign_next_role(self, to_member: GroupMember):
        if not any(self.open_roles()):
            return
        role = next(self.open_roles())
        to_member.data.match_role = role
        self.data.match_roles[role] = to_member.session_id
        to_member._save()

    def _assign_all_roles(self):
        if not self.full:
            raise MatchingError("Can't assign all roles if group is not full.")

        for role, member in zip(self.match_roles.keys(), self.members):
            member.data.match_role = role
            self.match_roles[role] = member.session_id
            member.data.assignment_ongoing = False
            member._save()

    def _shuffle_roles(self):
        role_list = list(self.match_roles.items())
        random.shuffle(role_list)
        self.data.match_roles = dict(role_list)

    def roles(self) -> List[str]:
        return list(self.match_roles)

    def _asdict(self):
        group = copy.copy(self.data)
        group.members = [asdict(m.data) for m in group.members]
        group.data = group.members
        return asdict(group)

    def _save(self):

        if saving_method(self.exp) == "local":
            with open(self.path, "w") as p:
                json.dump(self._asdict(), p, indent=4)
        elif saving_method(self.exp) == "mongo":
            query = {"type": "match_group", "group_id": self.group_id}
            self.exp.db_misc.find_one_and_replace(query, self._asdict(), upsert=True)
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def _set_assignment_status(self, status: bool = True):
        self.data.assignment_ongoing = status
        self._save()

    def __iadd__(self, member):
        member.data.match_group = self.group_id
        if "__groups" in member._exp.adata:
            member._exp.adata[f"__groups"].append(self.group_id)
        else:
            member._exp.adata["__groups"] = [self.group_id]
        self.members.append(member)
        return self

    def __enter__(self):
        self._operation_start = time.time()
        self._set_assignment_status(status=True)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if (time.time() - self._operation_start) > self.group_timeout:
            self.data.expired = True
        self._set_assignment_status(status=False)

    def __str__(self):
        return f"{type(self).__name__}(roles={str(list(self.match_roles.keys()))}, {len(self.members)}/{len(self.match_roles)} roles filled)"

    def __eq__(self, other):
        return (type(self) == type(other)) and (self.group_id == other.group_id)

    def __getattr__(self, name):
        try:
            return getattr(self.data, name)
        except AttributeError:
            return self.get_one_by_role(role=name)

