import copy
import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterator, List
from uuid import uuid4

from alfred3.alfredlog import QueuedLoggingInterface
from alfred3.data_manager import DataManager as dm

from ._util import MatchingError, MatchingTimeout, saving_method
from .data import SharedGroupData
from .group import Group, GroupMember


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
        c5 = d["member_active"]
        return all((c1, c2, c3, c4, c5))

    def matched(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.members(exp_version) if m.match_group is not None)

    def unmatched(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.members(exp_version) if m.match_group is None)

    def ready(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.unmatched(exp_version) if not m.assignment_ongoing)

    def waiting(self, exp_version: str) -> Iterator[GroupMember]:
        return (m for m in self.unmatched(exp_version) if m.assignment_ongoing)


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

    TIMEOUT_MSG = "MatchMaking timeout"

    def __init__(
        self,
        *roles,
        exp,
        name: str = "matchmaker",
        member_timeout: int = None,
        group_timeout: int = 60 * 60,
        match_timeout: int = 60 * 15,
        timeout_page=None,
        raise_exception: bool = False,
        shuffle_roles: bool = False,
        respect_version: bool = True,
    ):
        self.exp = exp
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)
        self.exp_version = self.exp.version if respect_version else ""
        self.shuffle_roles = shuffle_roles

        self.member_timeout = member_timeout if member_timeout is not None else self.exp.session_timeout
        self.group_timeout = group_timeout
        self.match_timeout = match_timeout
        self.timeout_page = timeout_page
        self.raise_exception = raise_exception

        self.roles = roles
        self.size = len(roles)
        self.name = name
        self.member = GroupMember._from_exp(
            self.exp, match_size=self.size, match_maker_name=self.name
        )
        self.member._save()
        self.group = None

        self.memberlist = MemberList(self.exp, self.name, self.member_timeout)
        self.grouplist = GroupList(self.exp, self.name)

        self.exp.abort_functions.append(self._deactivate)

        self.log.info("MatchMaker initialized.")
    
    def _deactivate(self, exp):
        self.member.deactivate()
        if self.group:
            self.group.data.expired = True
            self.group._save()

    def match_stepwise(self, assignment_timeout: int = 60, wait: bool = False):
        """
        Raises:
            MatchingError
        """
        if wait and saving_method(self.exp) == "local":
            raise MatchingError("Can't wait for full group in local experiment.")

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

    def match_groupwise(self) -> Group:
        """
        Raises:
            MatchingError
        """
        if not saving_method(self.exp) == "mongo":
            raise MatchingError("Must use a database for groupwise matching.")

        start = time.time()
        expired = (time.time() - start) > self.match_timeout

        group = None
        i = 0
        while not group:
            group = self._do_match_groupwise()
            self.group = group
            
            expired = (time.time() - start) > self.match_timeout
            if expired:
                break
            
            if (i == 0) or (i % 10 == 0):
                msg = f"Incomplete group in groupwise matching. Waiting. Member: {self.member}"
                self.log.debug(msg)
            i += 1
            time.sleep(1)

        if expired:
            self.log.error("Groupwise matchmaking timed out.")
            if self.raise_exception:
                raise MatchingTimeout
            else:
                return self._matching_timeout(group)
        else:
            self.log.info(f"{group} filled in groupwise match.")
            return self.group
    
    def _matching_timeout(self, group):
        if group:
            group.data.expired = True
            group._save()
            self.log.warning(f"{group} marked as expired.")
        
        if self.timeout_page:
            self.exp.abort(reason=self.TIMEOUT_MSG, page=self.timeout_page)
        else:
            self.exp.abort(reason=self.TIMEOUT_MSG, title="Timeout", msg="Sorry, the matchmaking process timed out.", icon="user-clock")
        
        return None
    
    def _wait_until_full(self, group: Group) -> Group:
        start = time.time()
        timeout = False
        while not group.full and not timeout:
            group = Group._from_id(group.group_id, exp=self.exp)
            time.sleep(1)
            timeout = (time.time() - start) > self.match_timeout
        
        if not group.full:
            self.exp.log.error("Stepwise matchmaking timed out.")
            if self.raise_exception:
                raise MatchingTimeout
            else:
                return self._matching_timeout(group)
        self.group = group
        return group

    def _start_group_and_assign(self):
        with self._start_group() as group:
            self.log.info(f"Starting stepwise match of session to new group: {group}.")
            group += self.member
            group._assign_next_role(to_member=self.member)
            self.log.info(f"Session matched to role '{self.member.match_role}' in {group}.")
            self.group = group
            return group

    def _match_next_group(self):
        with next(self.grouplist.ready(self.exp_version)) as group:
            self.log.info(f"Starting stepwise match of session to existing group: {group}.")
            group._discard_expired_members()
            group += self.member
            group._assign_next_role(to_member=self.member)
            self.log.info(f"Session matched to role '{self.member.match_role}' in {group}.")
            self.group = group
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
                    # we leave the odd group open for the time being but start a new one
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
        # to avoid racing between different MatchMaker sessions
        if any(self.grouplist.notfull(self.exp_version)):  
            return None

        # if another matchmaker has created the group
        # we rebuild the group object from the database and return it here
        member = self.member._reload()
        if member.match_group:
            self.member = member
            return Group._from_id(group_id=member.match_group, exp=self.exp)

        # if this matchmaker is creating the group
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

            return group
        else:
            return None

    def _start_group(self) -> Group:
        data = {}
        data["group_id"] = uuid4().hex
        data["match_maker_name"] = self.name
        data["match_size"] = self.size
        data["match_roles"] = {r: None for r in self.roles}
        data["member_timeout"] = self.member_timeout
        data["group_timeout"] = self.group_timeout

        group = Group._from_exp(exp=self.exp, **data)
        if self.shuffle_roles:
            group._shuffle_roles()
        group._save()
        return group

    def __str__(self):
        return f"{type(self).__name__}(name='{self.name}', roles={str(self.roles)})"
