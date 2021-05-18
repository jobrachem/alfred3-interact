"""
Functionality related to group members.
"""

import time
import json
from dataclasses import asdict

from pymongo.collection import ReturnDocument
from alfred3.data_manager import DataManager as dm

from .data import GroupMemberData
from ._util import saving_method
from ._util import MatchingError


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

    """

    def __init__(self, matchmaker, **kwargs):
        kwargs.pop("_id", None)
        self.mm = matchmaker
        self.exp = self.mm.exp
        exp_id = kwargs.get("exp_id", None)
        kwargs["exp_id"] = exp_id if exp_id is not None else self.exp.exp_id
        sid = kwargs.get("session_id", None)
        kwargs["session_id"] = sid if sid is not None else self.exp.session_id
        
        self.data = GroupMemberData(**kwargs)

    @property
    def _path(self):
        return self.mm.io.path
    
    @property
    def status(self) -> str:
        """
        str: Returns a string, indicating the member's status.
        """
        ping_timeout = self.mm.io.load().ping_timeout
        if self.finished:
            return "finished"
        elif self.session_data["exp_aborted"]:
            return "aborted"
        elif self.active:
            if self.group_id:
                return "matched"
            elif ping_timeout and time.time() - self.ping > ping_timeout:
                return "ping timeout"
            else:
                return "unmatched"
        elif self.expired:
            return "session timeout"
        else:
            return "pre-matching"
        
    @property
    def start_time(self) -> str:
        """
        str: Session start-time in human-readbale format (H:M:S)
        """
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))
    
    @property
    def last_move(self) -> str:
        """
        str: Time of last movement in human-readable format (H:M:S)
        """
        if self.move_history:
            t = self.move_history[-1]["hide_time"]
            if t:
                return time.strftime("%H:%M:%S", time.localtime(t))
            else:
                return None
        else:
            return None

    
    @property
    def last_page(self) -> str:
        """
        str: Returns the name of the member's current page.
        """
        try:
            return self.move_history[-1]["target_page"]
        except IndexError:
            return "-landing page-"

    @property
    def expired(self) -> bool:
        """
        bool: True, if the session is expired. False otherwise.
        """
        return time.time() - self.data.timestamp > self.mm.member_timeout

    @property
    def active(self) -> bool:
        """
        bool: True, if :attr:`.GroupMember.data.active` is True and the
        member has not timed out. A member is deactivated, e.g. when the
        experiment session of that member aborts.
        """
        return self.data.active and not self.expired and not self.finished
    
    @property
    def finished(self) -> bool:
        """
        bool: Indicates, whether the member's experiment session is finished.
        """
        return self.session_data["exp_finished"]

    @property
    def matched(self) -> bool:
        """
        bool: Indicates, whether the member has been added to a group.
        """
        return True if self.data.group_id is not None else False

    @property
    def values(self) -> dict:
        """
        dict: Flat dictionary of input element values.
        
        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.values`. The keys are
            the names of input elements in the member's experiment session.
            The values are the user inputs. 
        """
        d = dm.flatten(self.session_data).items()
        return {k: v for k, v in d if k not in dm._metadata and k not in dm.client_data}

    @property
    def session_data(self) -> dict:
        """
        dict: Full dictionary of experiment session data.

        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.session_data`.
        """
        if saving_method(self.exp) == "local":
            p = self.exp.config.get("local_saving_agent", "path")
            iterator = dm.iterate_local_data(dm.EXP_DATA, directory=self.exp.subpath(p))
            d = next((d for d in iterator if d["exp_session_id"] == self.session_id), None)
            return d
        elif saving_method(self.exp) == "mongo":
            query = {"exp_id": self.exp.exp_id, "exp_session_id": self.session_id, "type": dm.EXP_DATA}
            
            d = self.exp.db_main.find_one(query)

            if d is None:
                self.mm.log.warning(f"{self} did not find any session data. Trying to recover by waiting.")
                start = time.time()
                while d is None:
                    if time.time() - start > 10:
                        break
                    time.sleep(1)
                    d = self.exp.db_main.find_one(query)
            
            if not d:
                raise MatchingError(f"Could not find session data for {self}.")
            
            return d


    @property
    def move_history(self) -> dict:
        """
        dict: Dictionary of movement history.

        See Also:
            The dict works just like
            :attr:`alfred3.experiment.ExperimentSession.move_history`.
        """
        return self.session_data.get("exp_move_history", None)

    @property
    def metadata(self) -> dict:
        """
        dict: Dictionary of experiment metadata.

        See Also:
            The dict works just like
            :attr:`alfred3.experiment.ExperimentSession.metadata`.
        """
        data = dm.flatten(self.session_data).items()
        return {k: v for k, v in data if k in dm._metadata}

    @property
    def client_data(self) -> dict:
        """
        dict: Dictionary of client data.

        See Also:
            The dict works just like 
            :attr:`alfred3.experiment.ExperimentSession.client_data`.
        """

        data = dm.flatten(self.session_data).items()
        return {k: v for k, v in data if k in dm.client_data}

    
    def _save(self):
        if saving_method(self.exp) == "local":
            self._save_local()
        elif saving_method(self.exp) == "mongo":
            self._save_mongo()

    def _save_local(self):
        """
        Updates the entry for the member in the matchmaker data.
        """
        with open(self._path, "r", encoding="utf-8") as f:
            mm = json.load(f)

        mm["members"][self.session_id] = asdict(self.data)

        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(mm, f, sort_keys=True, indent=4)

    def _save_mongo(self):
        """
        Updates only the entry for the member in the matchmaker data.
        """
        q = {}
        q["type"] = self.mm._DATA_TYPE
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        d = {"members": {self.session_id: asdict(self.data)}}
        mm = self.exp.db_misc.find_one_and_update(
            q, [{"$set": d}], return_document=ReturnDocument.AFTER
        )

        if not self.session_id in mm["members"]:
            raise MatchingError

    def _load_if_notbusy(self):
        """
        Returns an updated version of self, if the corresponsing matchmaker
        is not busy.
        """
        if saving_method(self.exp) == "local":
            mm = self._load_if_notbusy_local()
        elif saving_method(self.exp) == "mongo":
            mm = self._load_if_notbusy_mongo()

        if mm is None:
            return None

        self.data = GroupMemberData(**mm["members"][self.session_id])
        return self

    def _load_if_notbusy_local(self):
        with open(self._path, "r", encoding="utf-8") as f:
            mm = json.load(f)

        if mm["busy"]:
            return None
        else:
            return mm

    def _load_if_notbusy_mongo(self):
        q = {}
        q["type"] = self.mm._DATA_TYPE
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.exp.exp_id
        q["exp_version"] = self.mm.exp_version
        q["busy"] = False
        return self.exp.db_misc.find_one(q)

    def __str__(self):
        gid = self.data.group_id[-4:] if self.group_id is not None else "-"
        return f"{type(self).__name__}(role='{self.data.role}', session_id='{self.data.session_id[-4:]}', group='{gid}', start='{self.start_time}')"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        c1 = type(self) == type(other)
        c2 = self.data.session_id == other.data.session_id

        return all([c1, c2])

    def __getattr__(self, name):
        return getattr(self.data, name)

class MemberManager:
    def __init__(self, matchmaker):
        self.mm = matchmaker

    def members(self):
        data = self.mm.io.load().members.values()
        for mdata in data:
            yield GroupMember(matchmaker=self.mm, **mdata)

    def active(self):
        return (m for m in self.members() if m.active)

    def unmatched(self):
        return (m for m in self.active() if not m.matched)
    
    def matched(self):
        return (m for m in self.members() if m.matched)

    def waiting(self, ping_timeout: int):
        now = time.time()
        for m in self.active():
            ping_timeout = now - m.ping > ping_timeout
            if not m.matched and not ping_timeout:
                yield m

    def find(self, id: str):
        return next((m for m in self.members() if m.data.session_id == id), None)
