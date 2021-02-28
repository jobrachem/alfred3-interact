from dataclasses import dataclass
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4
from typing import List
from typing import Iterator
import json
import time
import random
import copy

from alfred3.alfredlog import QueuedLoggingInterface
from alfred3.data_manager import DataManager as dm


class MatchingTimeout(Exception):
    pass


class MatchingError(Exception):
    pass


def saving_method(exp) -> bool:
    if not exp.secrets.getboolean("mongo_saving_agent", "use"):
        if exp.config.getboolean("local_saving_agent", "use"):
            return "local"
    elif exp.secrets.getboolean("mongo_saving_agent", "use"):
        return "mongo"
    else:
        return None


@dataclass
class GroupMemberData:
    session_id: str
    exp_id: str
    exp_version: str
    match_size: int
    match_maker_name: str
    match_group: str = None
    match_role: str = None
    type: str = "match_member"
    timestamp: float = time.time()
    assignment_ongoing: bool = False


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
        return time.time() - self.timestamp < timeout

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


class MemberList:
    def __init__(self, exp, match_maker_name: str, timeout: int = None):
        self.exp = exp
        self.timeout = timeout
        p = self.exp.config.get("interact", "path", fallback="save/interact")
        self.path = self.exp.subpath(p) / "members"
        self.path.mkdir(exist_ok=True, parents=True)
        self.match_maker_name = match_maker_name

    def members(self, exp_version: str) -> Iterator[GroupMember]:
        if saving_method(self.exp) == "local":
            return self._local_members(exp_version)
        elif saving_method(self.exp) == "mongo":
            return self._mongo_members(exp_version)
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def _local_members(self, exp_version: str):
        for member in self.path.iterdir():
            if member.is_dir():
                continue

            with open(member, "r") as f:
                d = json.load(f)
                if self._data_fits(d, exp_version):
                    yield GroupMember(data=d, exp=self.exp)

    def _mongo_members(self, exp_version: str):
        query = {"exp_id": self.exp.exp_id, "type": "match_member"}
        if exp_version:
            query["exp_version"] = exp_version

        for d in self.exp.db_misc.find(query):
            if self._data_fits(d, exp_version):
                d.pop("_id", None)
                yield GroupMember(data=d, exp=self.exp)

    def _data_fits(self, d: dict, exp_version: str) -> bool:
        c1 = d["type"] == "match_member"
        c2 = d["match_maker_name"] == self.match_maker_name
        c3 = d["exp_version"] == exp_version or not exp_version
        c4 = time.time() - d["timestamp"] < self.timeout
        return all((c1, c2, c3, c4))

    def matched(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.members(exp_version) if m.match_group is not None)

    def unmatched(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.members(exp_version) if m.match_group is None)

    def ready(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.unmatched(exp_version) if not m.assignment_ongoing)

    def waiting(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.unmatched(exp_version) if m.assignment_ongoing)


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
    timeout: int = None
    assignment_ongoing: bool = True
    expired: bool = False
    group_timeout: int = 60 * 60 * 1


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
            other = []
            for role in self._open_roles():
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

    def _discard_expired_members(self):
        if self.timeout is not None:
            self.data.members = [m for m in self.members if m.active(self.timeout)]
            member_ids = [m.session_id for m in self.members]
            for role, sid in self.match_roles.items():
                if sid not in member_ids:
                    self.match_roles[role] = None

    def _assigned_roles(self) -> Iterator[str]:
        return (role for role, member_id in self.match_roles.items() if member_id is not None)

    def _open_roles(self) -> Iterator[str]:

        return (role for role, member_id in self.match_roles.items() if member_id is None)

    def _assign_next_role(self, to_member: GroupMember):
        if not any(self._open_roles()):
            return
        role = next(self._open_roles())
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
        import pprint

        # self.log.warning(pprint.pformat(self._asdict()))

        if saving_method(self.exp) == "local":
            with open(self.path, "w") as p:
                json.dump(self._asdict(), p, indent=4)
        elif saving_method(self.exp) == "mongo":
            query = {"type": "match_group", "group_id": self.group_id}
            self.exp.db_misc.find_one_and_replace(query, self._asdict(), upsert=True)
            d = self.exp.db_misc.find_one(query)
            self.log.warning(pprint.pformat(d))
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def _set_assignment_status(self, status: bool = True):
        self.data.assignment_ongoing = status
        self._save()

    def __iadd__(self, member):
        member.data.match_group = self.group_id
        if "_group" in member._exp.adata:
            member._exp.adata[f"_group_{self.group_id}"] = self.group_id
        else:
            member._exp.adata["_group"] = self.group_id
        self.members.append(member)
        return self

    def __enter__(self):
        self._operation_start = time.time()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if (time.time() - self._operation_start) > self.group_timeout:
            self.data.expired = True
        self.data.assignment_ongoing = False
        self._save()

    def __str__(self):
        return f"{type(self).__name__}(roles={str(list(self.match_roles.keys()))}, {len(self.members)}/{len(self.match_roles)} roles filled)"

    def __eq__(self, other):
        return (type(self) == type(other)) and (self.group_id == other.group_id)

    def __getattr__(self, name):
        try:
            return getattr(self.data, name)
        except AttributeError:
            return self.get_one_by_role(role=name)


class GroupList:
    def __init__(self, exp, match_maker_name: str):
        self.exp = exp
        p = self.exp.config.get("interact", "path", fallback="save/interact")
        self.path = self.exp.subpath(p)
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.match_maker_name = match_maker_name

    def groups(self, exp_version: str):
        if saving_method(self.exp) == "local":
            return self._local_groups(exp_version)
        elif saving_method(self.exp) == "mongo":
            return self._mongo_groups(exp_version)
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def full(self, exp_version: str):
        if exp_version:
            return (g for g in self.groups(exp_version) if g.full)
        else:
            return (g for g in self.groups(exp_version) if g.full)

    def notfull(self, exp_version: str):
        if exp_version:
            return (g for g in self.groups(exp_version) if not g.full)
        else:
            return (g for g in self.groups(exp_version) if not g.full)

    def ready(self, exp_version: str):
        for group in self.notfull(exp_version):
            if not group.assignment_ongoing:
                group._set_assignment_status(status=True)
                yield group

    def waiting(self, exp_version: str):
        return (g for g in self.notfull(exp_version) if g.assignment_ongoing)

    def _local_groups(self, exp_version: str):
        for group in self.path.iterdir():
            if group.is_dir():
                continue

            with open(group, "r") as f:
                d = json.load(f)
                if self._group_fits(d, exp_version):
                    yield Group(data=d, exp=self.exp)

    def _mongo_groups(self, exp_version: str):
        query = {"exp_id": self.exp.exp_id, "type": "match_group"}
        if exp_version:
            query["exp_version"] = exp_version

        for d in self.exp.db_misc.find(query):
            if self._group_fits(d, exp_version):
                d.pop("_id", None)
                yield Group(data=d, exp=self.exp)

    def _group_fits(self, d: dict, exp_version: str) -> bool:
        c1 = d["type"] == "match_group"
        c2 = d["match_maker_name"] == self.match_maker_name
        c3 = d["exp_version"] == exp_version or not exp_version
        c4 = not d["expired"]
        return all((c1, c2, c3, c4))


class MatchMaker:
    """
    Args:
        name (str): The matchmaker name MUST be the same for all sessions
            that should be part of the matchmaking process.
    """

    def __init__(
        self,
        *roles,
        exp,
        name: str = "matchmaker",
        timeout: int = None,
        group_timeout: int = 60 * 60 * 1,
        shuffle_roles: bool = False,
        respect_version: bool = True,
    ):
        self.exp = exp
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)
        self.exp_version = self.exp.version if respect_version else ""
        self.shuffle_roles = shuffle_roles
        self.timeout = timeout if timeout is not None else self.exp.session_timeout
        self.group_timeout = group_timeout
        self.roles = roles
        self.size = len(roles)
        self.name = name
        self.member = GroupMember._from_exp(
            self.exp, match_size=self.size, match_maker_name=self.name
        )
        self.member._save()

        self.memberlist = MemberList(self.exp, self.name, self.timeout)
        self.grouplist = GroupList(self.exp, self.name)

        self.log.info("MatchMaker initialized.")

    def match_stepwise(self, assignment_timeout: int = 60, wait: bool = False):
        """
        Raises:
            MatchingError
        """
        if any(self.grouplist.notfull(self.exp_version)):
            try:
                group = self._match_next_group()
                if wait:
                    group = self._wait_until_full(group)
                return group
            except StopIteration:
                return self._wait(secs=0.5, wait_max=assignment_timeout)
        else:
            group = self._start_group_and_assign()
            if wait:
                group = self._wait_until_full(group)
            return group

    def match_groupwise(self, match_timeout: int = 60 * 15) -> Group:
        """
        Raises:
            MatchingError
        """
        if not saving_method(self.exp) == "mongo":
            raise MatchingError("Must use a database for groupwise matching.")

        start = time.time()
        expired = (time.time() - start) > match_timeout

        group = None
        i = 0
        while not group and not expired:
            group = self._do_match_groupwise()
            expired = (time.time() - start) > match_timeout
            if i % 5 == 0:
                self.log.debug(
                    f"Incomplete group in groupwise matching. Waiting. Member: {self.member}"
                )
            i += 1
            time.sleep(1)

        if expired:
            raise MatchingTimeout
        else:
            return group

    def _wait_until_full(self, group: Group) -> Group:
        start = time.time()
        while not group.full and (time.time() - start) < self.group_timeout:
            time.sleep(1)
            group = Group._from_id(group.group_id, exp=self.exp)

        return group

    def _start_group_and_assign(self):
        with self._start_group() as group:
            self.log.info(f"Starting stepwise match of session to new group: {group}.")
            group += self.member
            group._assign_next_role(to_member=self.member)
            self.log.info(f"Session matched to role '{self.member.match_role}' in {group}.")
            return group

    def _match_next_group(self):
        with next(self.grouplist.ready(self.exp_version)) as group:
            self.log.info(f"Starting stepwise match of session to existing group: {group}.")
            group._discard_expired_members()
            group += self.member
            group._assign_next_role(to_member=self.member)
            self.log.info(f"Session matched to role '{self.member.match_role}' in {group}.")
            return group

    def _wait(self, secs: int, wait_max: int):
        if saving_method(self.exp) == "local":
            raise MatchingError("Can't wait for result in local experiment.")

        self.log.info(
            f"Waiting for ongoing group assignment to finish. Waiting for a maximum of {wait_max} seconds."
        )
        try:
            total_wait_time = 0

            while next(self.grouplist.notfull(self.exp_version)) == next(
                self.grouplist.waiting(self.exp_version)
            ):

                if total_wait_time > wait_max:
                    # this is what happens, if waiting took too long
                    # something is odd in this case
                    # we leave it open for the time being and start a new one
                    group = next(self.grouplist.waiting(self.exp_version))

                    msg1 = f"{group} was in waiting position for too long. "
                    msg2 = f"Starting a new group for session {self.exp.session_id}."
                    self.log.warning(msg1 + msg2)
                    return self._start_group_and_assign()

                total_wait_time += secs
                time.sleep(secs)

        except StopIteration:
            self.log.info("Previous group assignment finished. Proceeding.")
            # this is the planned output for the waiting function
            # gets triggered, as soon as there is either no notfull group
            # or no waiting group anymore
            return self.match_stepwise()

    def _do_match_groupwise(self) -> Group:
        if any(
            self.grouplist.notfull(self.exp_version)
        ):  # to avoid racing between different MatchMaker sessions
            return None

        # another matchmaker has created the group
        # we rebuild the group object from the database and return it here
        member = self.member._reload()
        if member.match_group:
            self.member = member
            return Group._from_id(group_id=member.match_group, exp=self.exp)

        # this matchmaker is creating the group
        unmatched_members = list(self.memberlist.ready(self.exp_version))
        if len(unmatched_members) >= self.size:
            for m in unmatched_members[: self.size]:
                m._set_assignment_status(status=True)

            with self._start_group() as group:
                group += self.member
                waiting_members = self.memberlist.waiting(self.exp_version)
                while not group.full:
                    group += next(waiting_members)
                group._assign_all_roles()

                self.log.info(f"{group} filled in groupwise match.")

            return group
        else:
            return None

    def _start_group(self) -> Group:
        data = {}
        data["group_id"] = uuid4().hex
        data["match_maker_name"] = self.name
        data["match_size"] = self.size
        data["match_roles"] = {r: None for r in self.roles}
        data["timeout"] = self.timeout
        data["group_timeout"] = self.group_timeout

        group = Group._from_exp(exp=self.exp, **data)
        if self.shuffle_roles:
            group._shuffle_roles()
        group._save()
        return group

    def __str__(self):
        return f"{type(self).__name__}(name='{self.name}', roles={str(self.roles)})"
