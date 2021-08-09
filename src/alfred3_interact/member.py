"""
Functionality related to group members.
"""

import time
import datetime
import json
from typing import Iterator, List
from dataclasses import asdict, dataclass, field

from pymongo.collection import ReturnDocument
from alfred3.data_manager import DataManager as dm
from alfred3.quota import SessionGroup

from ._util import saving_method
from ._util import MatchingError


@dataclass
class GroupMemberData:
    exp_id: str
    session_id: str
    group_id: str = None
    role: str = None
    created: float = field(default_factory=time.time)
    ping: float = field(default_factory=time.time)
    type: str = "match_member"


class MemberHelper:
    def __init__(self, member):
        self.member = member
        self.sid = self.member.data.session_id
        self.mm = self.member.mm
        self.exp = self.member.exp
        self.saving_method = saving_method(self.exp)


class GroupMemberIO(MemberHelper):
    def __init__(self, member):
        super().__init__(member)

        self.path = self.mm.io.path
        self.db = self.member.exp.db_misc

    @property
    def query(self) -> dict:
        q = {}
        q["type"] = self.mm._DATA_TYPE
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        return q

    def load(self):
        if self.saving_method == "mongo":
            data = self._load_mongo()
        elif self.saving_method == "local":
            data = self._load_local()
        data = data["members"][self.sid]
        self.member.data = GroupMemberData(**data)

    def _load_local(self) -> dict:
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_mongo(self) -> dict:
        data = self.db.find_one(self.query, projection={f"members.{self.sid}"})
        return data

    def save(self):
        if self.saving_method == "mongo":
            self._save_mongo()
        elif self.saving_method == "local":
            self._save_local()

    def _save_local(self):
        with open(self.path, "r", encoding="utf-8") as f:
            mm = json.load(f)

        sid = self.member.data.session_id
        mm["members"][sid] = asdict(self.member.data)

        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(mm, f, sort_keys=True, indent=4)

    def _save_mongo(self):
        data = {"members": {self.sid: asdict(self.member.data)}}
        self.db.find_one_and_update(self.query, [{"$set": data}])

    def ping(self):
        if saving_method(self.exp) == "local":
            return
        now = time.time()
        data = {"members": {self.sid: {"ping": now}}}
        self.db.find_one_and_update(self.query, [{"$set": data}])
        self.member.data.ping = now

# TODO Manuell deaktivieren für MatchMaker-Chaining
@dataclass
class GroupMemberStatus:
    def __init__(self, member):
        self.member = member
        self.exp = member.exp
        self.status = SessionGroup(sessions=[member.data.session_id])

    @property
    def finished(self) -> bool:
        return self.status.finished(self.exp)

    @property
    def aborted(self) -> bool:
        return self.status.aborted(self.exp)

    @property
    def expired(self) -> bool:
        return self.status.expired(self.exp)

    @property
    def active(self) -> bool:
        return self.status.pending(self.exp)

    @property
    def matched(self) -> bool:
        return self.member.data.group_id is not None

    def ping_expired(self, ping_timeout: int) -> bool:
        now = time.time()
        expired = now - self.member.data.ping > ping_timeout
        return expired

    def print_status(self) -> str:
        if self.active:
            return "active"
        elif self.finished:
            return "finished"
        elif self.aborted:
            return "aborted"
        elif self.expired:
            return "expired"


class GroupMemberExpData(MemberHelper):
    
    @property
    def db(self):
        return self.exp.db_main

    @property
    def query(self) -> dict:
        d = {}
        d["exp_id"] = self.exp.exp_id
        d["exp_session_id"] = self.sid
        d["type"] = dm.EXP_DATA

        return d

    def _load_local(self) -> dict:
        dt = dm.EXP_DATA
        directory = self.exp.config.get("local_saving_agent", "path")
        directory = self.exp.subpath(directory)
        cursor = dm.iterate_local_data(dt, directory)
        session = (data for data in cursor if data["exp_session_id"] == self.sid)
        return next(session, None)

    def load(self, projection=None) -> dict:
        if self.saving_method == "mongo":
            data = self.db.find_one(self.query, projection=projection)
            data.pop("_id")

        elif self.saving_method == "local":
            data = self._load_local()

            if isinstance(projection, list):
                data = {k: v for k, v in data.items() if k in projection}
            elif isinstance(projection, dict):
                data = {k: v for k, v in data.items() if projection[k]}

        return data

    @property
    def start_time_unix(self) -> float:
        data = self.load(["exp_start_time"])
        return data["exp_start_time"]


class GroupMemberInfo(MemberHelper):
    def __init__(self, member):
        super().__init__(member)
        self.expdata = self.member.expdata
        self._start_time_unix = self.expdata.start_time_unix

    @property
    def start_time_unix(self) -> float:
        if self._start_time_unix:
            start_time = self._start_time_unix
        else:
            start_time = self.expdata.start_time_unix
            self._start_time_unix = start_time

        return start_time

    @property
    def start_time(self) -> str:
        """
        str: Session start-time in human-readbale format (H:M:S)
        """
        if self.start_time_unix:
            return time.strftime("%H:%M:%S", time.localtime(self.start_time_unix))
        else:
            return "None"

    @property
    def start_day(self) -> str:
        """
        str: Session start-day in human-readbale format (yyyy-mm-dd)
        """
        date = datetime.date.fromtimestamp(self.start_time_unix)
        return date.isoformat()

    @property
    def last_move(self) -> str:
        moves = self.member.move_history
        if moves:
            t = moves[-1]["hide_time"]
            time_print = time.strftime("%H:%M:%S", time.localtime(t))
            return time_print

        return None
    
    @property
    def last_save(self) -> float:
        projection = {"exp_save_time": True, "_id": False}
        data = self.member.expdata.load(projection)
        return data["exp_save_time"]

    @property
    def last_page(self) -> str:
        try:
            return self.member.move_history[-1]["target_page"]
        except IndexError:
            return "-landing page-"


class GroupMember:
    """
    The group member object grants access to a member's experiment data.
    
    The group member object's most important job is to provide easy
    access to the member's experiment data through the following
    attributes. They provide the same objects as the corresponding
    attributes of the :class:`alfred3.experiment.ExperimentSession`
    object:

    - :attr:`.values`
    - :attr:`.session_data`
    - :attr:`.metadata`
    - :attr:`.client_data`
    - :attr:`.adata`
    """
    def __init__(self, matchmaker, **data):

        self.mm = matchmaker
        self.exp = self.mm.exp

        self.data = GroupMemberData(**self._prepare_data(data))
        self.io = GroupMemberIO(self)
        self.status = GroupMemberStatus(self)
        self.expdata = GroupMemberExpData(self)
        self.info = GroupMemberInfo(self)

    def _prepare_data(self, data: dict) -> dict:
        exp_id = data.get("exp_id", None)
        sid = data.get("session_id", None)

        data["exp_id"] = exp_id if exp_id is not None else self.exp.exp_id
        data["session_id"] = sid if sid is not None else self.exp.session_id

        data.pop("_id", None)
        return data

    @property
    def role(self) -> str:
        """
        str: The member's role.
        """
        return self.data.role

    @property
    def matched(self) -> bool:
        """
        bool: Indicates whether the member is associated with a group.
        """
        return self.status.matched
    
    @property
    def group_id(self) -> str:
        """
        str: If the member is associated with a group, this property
        returns the group id.
        """
        return self.data.group_id

    @property
    def values(self) -> dict:
        """
        dict: Flat dictionary of input element values.

        Gives access to the member's experiment inputs.
        
        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.values`. The keys are
            the names of input elements in the member's experiment session.
            The values are the user inputs. 
        """
        projection = {}
        projection.update({key: False for key in dm._client_data_keys})
        projection.update({key: False for key in dm._metadata_keys})

        data = self.expdata.load(projection)
        return dm.flatten(data)
    
    @property
    def session_data(self) -> dict:
        """
        dict: Full dictionary of experiment session data.

        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.session_data`.
        """
        return self.expdata.load()

    @property
    def client_data(self) -> dict:
        """
        dict: Dictionary of client data.

        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.client_data`.
        """
        client_data = list(dm._client_data_keys)
        return self.expdata.load(client_data)

    @property
    def metadata(self) -> dict:
        """
        dict: Dictionary of experiment metadata.

        See Also:
            The dict works just like
            :attr:`alfred3.experiment.ExperimentSession.metadata`.
        """
        metadata = list(dm._metadata_keys)
        return self.expdata.load(metadata)

    @property
    def move_history(self) -> dict:
        """
        dict: Dictionary of movement history.

        See Also:
            The dict works just like
            :attr:`alfred3.experiment.ExperimentSession.move_history`.
        """
        data = self.expdata.load(["exp_move_history"])
        return data["exp_move_history"]

    @property
    def adata(self) -> dict:
        """
        dict: Dictionary of additional data.

        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.adata`.
        """
        data = self.expdata.load(["additional_data"])
        return data["additional_data"]

    @property
    def additional_data(self) -> dict:
        """
        dict: Alias for :attr:`.adata`
        """
        return self.adata

    def __repr__(self) -> str:
        gid = self.data.group_id[-4:] if self.data.group_id is not None else "-"
        repr = (
            f"{type(self).__name__}(role='{self.data.role}', "
            f"session_id='{self.data.session_id[-4:]}', "
            f"group='{gid}', start='{self.info.start_time}')"
        )

        return repr

    def __eq__(self, other) -> bool:
        class_equal = type(self) == type(other)
        session_id_equal = self.data.session_id == other.data.session_id

        return class_equal and session_id_equal


class MemberManager:
    def __init__(self, matchmaker):
        self.mm = matchmaker
        self.exp = self.mm.exp
        self.db = self.exp.db_misc
        self._active_sessions_projection = None
        self._last_update = None
        self.method = saving_method(self.exp)

    @property
    def query_mm(self) -> dict:
        q = {}
        q["type"] = self.mm._DATA_TYPE
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        return q

    @property
    def query_exp(self) -> dict:
        q = {}
        q["type"] = dm.EXP_DATA
        q["exp_id"] = self.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        return q

    def query_active_sessions(self, sessions: List[str] = None) -> dict:
        q = self.query_exp
        q["exp_finished"] = False
        q["exp_aborted"] = False
        earliest_start = time.time() - self.exp.session_timeout
        q["$or"] = [{"exp_start_time": {"$gte": earliest_start}}, {"exp_start_time": None}]

        if sessions is not None:
            q["exp_session_id"] = {"$in": sessions}

        return q

    def find_active_sessions(self, sessions: List[str] = None) -> Iterator[str]:
        if self.method == "local":
            return self._find_active_sessions_local(sessions)
        elif self.method == "mongo":
            return self._find_active_sessions_mongo(sessions)
            
    def _find_active_sessions_local(self, sessions: List[str] = None) -> Iterator[str]:
        for member in self.members():
            if member.status.active:
                yield member.data.session_id
    
    def _find_active_sessions_mongo(self, sessions: List[str] = None) -> Iterator[str]:
        q = self.query_active_sessions(sessions)
        cursor = self.exp.db_main.find(q, projection=["exp_session_id"])
        for sessiondata in cursor:
            yield sessiondata["exp_session_id"]

    def find_finished_sessions(self, sessions: List[str] = None) -> Iterator[str]:
        if self.method == "local":
            return self._find_finished_sessions_local(sessions)

        elif self.method == "mongo":
            return self._find_finished_sessions_mongo(sessions)
    
    def _find_finished_sessions_local(self, sessions: List[str]) -> Iterator[str]:
        for m in self.members():
            if m.status.finished and m.data.session_id in sessions:
                yield m.data.session_id

    def _find_finished_sessions_mongo(self, sessions: List[str]) -> Iterator[str]:
        q = self.query_exp
        q["exp_finished"] = True
        if sessions is not None:
            q["exp_session_id"] = {"$in": sessions}
        cursor = self.exp.db_main.find(q, projection=["exp_session_id"])
        for sessiondata in cursor:
            yield sessiondata["exp_session_id"]

    def active_sessions_projection(self, cache_length: int = 1) -> dict:
        now = time.time()

        if self._last_update and self._last_update - now < cache_length:
            return self._active_sessions_projection
        else:
            p = {f"members.{sid}": True for sid in self.find_active_sessions()}
            p.update({"_id": False})
            self._active_sessions_projection = p
            self._last_update = now

    def active(self) -> GroupMember:
        if self.method == "local":
            return self._active_local()
        
        elif self.method == "mongo":
            return self._active_mongo()
    
    def _active_local(self) -> Iterator[GroupMember]:
        for m in self.members():
            if m.status.active:
                yield m
    
    def _active_mongo(self) -> Iterator[GroupMember]:
        q = self.query_mm
        p = self.active_sessions_projection()

        data = self.db.find_one(filter=q, projection=p)
        data = data["members"].values()

        for mdata in data:
            yield GroupMember(matchmaker=self.mm, **mdata)

    def waiting(self, ping_timeout: int) -> Iterator[GroupMember]:
        for m in self.unmatched():
            if not m.status.ping_expired(ping_timeout):
                yield m

    def members(self) -> Iterator[GroupMember]:
        data = self.mm.io.load().members.values()
        for mdata in data:
            yield GroupMember(matchmaker=self.mm, **mdata)

    def unmatched(self) -> Iterator[GroupMember]:
        for m in self.active():
            if not m.status.matched:
                yield m

    def matched(self) -> Iterator[GroupMember]:
        for m in self.active():
            if m.status.matched:
                yield m

    def find(self, sessions: List[str]) -> Iterator[GroupMember]:
        if self.method == "local":
            return self._find_local(sessions)
        
        elif self.method == "mongo":
            return self._find_mongo(sessions)    
    
    def _find_local(self, sessions: List[str]) -> Iterator[GroupMember]:
        data = self.mm.io.load().members.values()
        for mdata in data:
            if mdata["session_id"] in sessions:
                yield GroupMember(matchmaker=self.mm, **mdata)
    
    def _find_mongo(self, sessions: List[str]) -> Iterator[GroupMember]:
        q = self.query_mm
        p = {f"members.{sid}": True for sid in sessions}
        p.update({"_id": False})

        data = self.db.find_one(filter=q, projection=p)
        data = data["members"].values()

        for mdata in data:
            yield GroupMember(matchmaker=self.mm, **mdata)
