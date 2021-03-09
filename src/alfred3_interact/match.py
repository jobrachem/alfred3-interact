
import time
import json
import copy
import string
from dataclasses import asdict

from pymongo.collection import ReturnDocument
from alfred3.page import Page
from alfred3.alfredlog import QueuedLoggingInterface
from alfred3.experiment import ExperimentSession

from .group import Group
from .member import GroupMember
from .manager import MemberManager
from .manager import GroupManager
from .data import MatchMakerData
from ._util import saving_method
from ._util import MatchingError
from ._util import BusyGroup
from ._util import MatchingTimeout

class MatchMakerIO:
    def __init__(self, matchmaker):
        self.mm = matchmaker
        self.path.parent.mkdir(exist_ok=True, parents=True)

    @property
    def db(self):
        return self.mm.exp.db_misc

    @property
    def path(self):
        p = self.mm.exp.config.get("interact", "path", fallback="save/interact")
        name = f"{self.mm.matchmaker_id}{self.mm.exp_version}.json"
        return self.mm.exp.subpath(p) / name

    @property
    def query(self):
        q = {}
        q["type"] = self.mm.DATA_TYPE
        q["exp_id"] = self.mm.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        q["matchmaker_id"] = self.mm.matchmaker_id
        return q

    def save(self, data: MatchMakerData):
        if saving_method(self.mm.exp) == "mongo":
            self._save_mongo(data)
        elif saving_method(self.mm.exp) == "local":
            self._save_local(data)
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def load(self) -> MatchMakerData:
        """
        Loads MatchMakerData. If there is none, creates a MatchMakerData
        document.
        """
        if saving_method(self.mm.exp) == "mongo":
            return self._load_mongo()
        elif saving_method(self.mm.exp) == "local":
            return self._load_local()

    def load_markbusy(self) -> MatchMakerData:
        """
        Loads MatchMakerData and marks it as busy, if it is not busy
        already. In the latter case, returns None.
        """
        self.mm.busy = True
        if saving_method(self.mm.exp) == "mongo":
            return self._load_markbusy_mongo()
        elif saving_method(self.mm.exp) == "local":
            return self._load_markbusy_local()

    def release(self) -> MatchMakerData:
        """
        Releases MatchMakerData from a 'busy' state.
        Happens only in groupwise matching, so there is only a mongoDB
        version of this one.
        """
        q = copy.copy(self.query)
        q["busy"] = True
        self.db.find_one_and_update(q, {"$set": {"busy": False}})

    def _save_mongo(self, data: MatchMakerData):
        self.db.find_one_and_replace(self.query, asdict(data))

    def _save_local(self, data: MatchMakerData):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(asdict(data), f, sort_keys=True, indent=4)

    def _load_mongo(self):

        insert = MatchMakerData(
            exp_id=self.mm.exp.exp_id,
            exp_version=self.mm.exp_version,
            matchmaker_id=self.mm.matchmaker_id,
        )

        data = self.db.find_one_and_update(
            self.query,
            {"$setOnInsert": asdict(insert)},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        data.pop("_id", None)
        return MatchMakerData(**data)

    def _load_local(self) -> MatchMakerData:
        """
        If there is a matchmaker json file, this returns the data from
        that file. Otherwise, it inserts the needed json file and then
        returns the corresponding data.
        """
        if self.path.exists() and self.path.is_file():
            with open(self.path, "r", encoding="utf-8") as f:
                return MatchMakerData(**json.load(f))
        else:
            data = MatchMakerData(
                exp_id=self.mm.exp.exp_id,
                exp_version=self.mm.exp_version,
                matchmaker_id=self.mm.matchmaker_id,
            )

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(asdict(data), f, sort_keys=True, indent=4)
            return data

    def _load_markbusy_local(self):
        data = self._load_local()
        if not data.busy:
            data.busy = True
            self._save_local(data)
            return MatchMakerData(**data)
        else:
            return None

    def _load_markbusy_mongo(self):
        q = self.query
        q["busy"] = False
        data = self.db.find_one_and_update(q, {"$set": {"busy": True}})
        if data is not None:
            data.pop("_id", None)
            data["busy"] = True
            return MatchMakerData(**data)
        else:
            return None


class MatchMaker:
    TIMEOUT_MSG = "MatchMaking timeout"
    DATA_TYPE = "match_maker"

    def __init__(
        self,
        *roles,
        exp: ExperimentSession,
        id: str = "matchmaker",
        member_timeout: int = None,
        group_timeout: int = 60 * 60,  # one hour
        match_timeout: int = 60 * 15,  # 15 minutes
        timeout_page: Page = None,
        raise_exception: bool = False,
        shuffle_roles: bool = False,
        respect_version: bool = True,
    ):
        self.exp = exp
        self.exp_version = self.exp.version if respect_version else ""
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)

        self.shuffle_roles = shuffle_roles
        self.member_timeout = (
            member_timeout if member_timeout is not None else self.exp.session_timeout
        )

        # if a single operation in a group takes longer than this, the group
        # is marked as inactive
        self.group_timeout = group_timeout

        # if
        self.match_timeout = match_timeout

        # for groupwise matching - only members with active ping are considered
        self.ping_timeout = 100
        self.timeout_page = timeout_page
        self.raise_exception = raise_exception

        self.roles = roles
        self.matchmaker_id = id
        self.io = MatchMakerIO(self)

        self._data = self.io.load()

        self.member_manager = MemberManager(self)
        self.group_manager = GroupManager(self)
        self.member = None
        self.group = None

        self.exp.abort_functions.append(self._deactivate)

    @classmethod
    def from_size(cls, nroles: int, **kwargs):
        roles = []
        for i in range(nroles):
            letter = string.ascii_letters[i]
            while letter in roles:
                letter = letter + string.ascii_letters[i]
            roles.append(letter)
        
        return cls(*roles, **kwargs)

    @property
    def data(self):
        self._data.members[self.member.session_id] = asdict(self.member.data)
        return self._data

    def match_stepwise(self, wait: bool = False) -> Group:
        if wait and saving_method(self.exp) == "local":
            raise MatchingError("Can't wait for full group in local experiment.")

        self.member = GroupMember(self)
        self.member._save()

        if any(self.group_manager.notfull()):
            try:
                self.group = self._match_next_group()
            except BusyGroup:
                # TODO: Assignment timeout?
                self.group = self._wait_until_free(self.match_timeout)
            if wait:
                self.group = self._wait_until_full(self.group)

            return self.group

        else:
            roles = {role: None for role in self.roles}
            with Group(self, roles=roles) as group:
                self.log.info(f"Starting new group: {group}.")

                if self.shuffle_roles:
                    group._shuffle_roles()

                group += self.member
                group._assign_next_role(to_member=self.member)
                self.member._save()
                self.group = group
                self.log.info(f"Session matched to role '{self.member.role}' in {group}.")

            if wait:
                self.group = self._wait_until_full(self.group)

            return self.group

    def match_groupwise(self) -> Group:
        if not saving_method(self.exp) == "mongo":
            raise MatchingError("Must use a database for groupwise matching.")

        self.member = GroupMember(self)
        self.member._save()

        start = time.time()
        expired = (time.time() - start) > self.match_timeout

        i = 0
        while not self.group:
            self.member._ping()

            self.group = self._do_match_groupwise()

            if not self.group:
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
                return self._matching_timeout(self.group)
        else:
            self.log.info(f"{self.group} filled in groupwise match.")
            return self.group

    def _wait_until_free(self, wait_max: int):
        if saving_method(self.exp) == "local":
            raise MatchingError("Can't wait for result in local experiment.")

        self.log.info(
            f"Waiting for ongoing group assignment to finish. Waiting for a maximum of {wait_max} seconds."
        )
        group = next(self.group_manager.notfull())
        start = time.time()
        timeout = False

        while group.busy and not timeout:
            timeout = time.time() - start > wait_max
            group = self.group_manager.find(group.group_id)
            time.sleep(1)

        if not timeout and not group.busy:
            self.log.info("Previous group assignment finished. Proceeding.")
            return group

        elif timeout:
            msg1 = f"{group} was in waiting position for too long. "
            msg2 = f"Starting a new group for session {self.exp.session_id}."
            self.log.warning(msg1 + msg2)

            group = Group(self, roles=self.roles)
            if self.shuffle_roles:
                group._shuffle_roles()

            return group

    def _wait_until_full(self, group: Group):
        start = time.time()
        timeout = False
        group_id = group.group_id

        while not group.full and not timeout:
            group = self.group_manager.find(group_id)
            time.sleep(1)
            timeout = (time.time() - start) > self.match_timeout

        if timeout:
            self.exp.log.error("Stepwise matchmaking timed out.")
            if self.raise_exception:
                raise MatchingTimeout
            else:
                return self._matching_timeout(group)

        return group

    def _match_next_group(self):
        with next(self.group_manager.notfull()) as group:
            self.log.info(f"Starting stepwise match of session to existing group: {group}.")

            group += self.member
            group._assign_next_role(to_member=self.member)
            self.member._save()

            self.log.info(f"Session matched to role '{self.member.role}' in {group}.")
            return group

    def _do_match_groupwise(self):
        member = self.member._load_if_notbusy()
        if member is None:
            self.log.debug("Returning. Member not found, MM is busy")
            return None

        elif member.matched:
            self.log.debug("Returning. Found group")
            return self.group_manager.find(member.data.group_id)

        # returns None if MatchMaker is busy, marks as busy otherwise
        data = self.io.load_markbusy()
        if data is None:
            self.log.debug("Returning. Data marked, MM is busy.")
            return None

        waiting_members = list(self.member_manager.waiting())
        waiting_members = [m for m in waiting_members if m != self.member]
        waiting_members.insert(0, self.member)

        if len(waiting_members) >= len(self.roles):
            self.log.debug("Filling group.")
            roles = {role: None for role in self.roles}
            group = Group(matchmaker=self, roles=roles)
            if self.shuffle_roles:
                group._shuffle_roles()

            candidates = (m for m in waiting_members)
            while not group.full:
                group += next(candidates)

            group._assign_all_roles(to_members=waiting_members)
            group._save()

            # update matchmaker data
            for m in waiting_members:
                data.members[m.data.session_id] = asdict(m.data)
            self.io.save(data=data)

            # release busy-lock
            self.io.release()
            self._data = self.io.load()
            self.log.debug("Returning filled group.")
            return group

        else:  # if there were not enough members
            self.io.release()
            self._data = self.io.load()
            return None

    def _matching_timeout(self, group):
        if group:
            group.data.active = False
            group._save()
        self.log.warning(f"{group} marked as expired. Releasing MatchMaker busy lock.")
        self.io.release()
        self._data = self.io.load()

        if self.timeout_page:
            self.exp.abort(reason=self.TIMEOUT_MSG, page=self.timeout_page)
        else:
            self.exp.abort(
                reason=self.TIMEOUT_MSG,
                title="Timeout",
                msg="Sorry, the matchmaking process timed out.",
                icon="user-clock",
            )

        return None

    def _deactivate(self, exp):
        # gets called when the experiment aborts!
        if self.member:
            self.member.data.active = False
            self.member._save()

    def __str__(self):
        return f"{type(self).__name__}(id='{self.matchmaker_id}', roles={str(self.roles)})"

    def __repr__(self):
        return self.__str__()
