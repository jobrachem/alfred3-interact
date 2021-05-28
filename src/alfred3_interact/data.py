"""
Data representation classes for interactive components.
"""

import time
from uuid import uuid4
from collections import UserDict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from alfred3.util import prefix_keys_safely
from pymongo.collection import ReturnDocument

from ._util import saving_method


class SharedGroupData(UserDict):
    """
    Shared group data dictionary.

    This dictionary can be used just like a normal dictionary. 
    Its benefit is that it synchronises data to a database. 
    This way, the data is always automatically shared between all group 
    members.
    """

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self._db = self.group.exp.db_misc

        if self.group.data.shared_data:
            self.data = self.group.data.shared_data
        
        self.data["__group_id"] = self.group.group_id
    
    def _push_remote(self):
        doc = self._db.find_one_and_update(
            filter={"group_id": self.group.group_id}, 
            update={"$set": {"shared_data": self.data}},
            projection={"shared_data": True, "_id": False},
            return_document=ReturnDocument.AFTER
            )
        if doc is not None:
            self.data = doc["shared_data"]
    
    def _fetch_remote(self):
        doc = self._db.find_one(
            filter={"group_id": self.group.group_id},
            projection={"shared_data": True, "_id": False},
            )
        if doc is not None:
            self.data = doc["shared_data"]
    
    def _push_local(self):
        self.group.data.shared_data = self.data
        self.group._save()
    
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

    def __getitem__(self, key):
        self._fetch()
        return super().__getitem__(key)
    
    def __setitem__(self, key, item):
        self._fetch()
        super().__setitem__(key, item)
        self.data["__last_change"] = time.time()
        self._push()
    
    def __delitem__(self, key):
        self._fetch()
        super().__delitem__(key)
        self.data["__last_change"] = time.time()
        self._push()


@dataclass
class GroupMemberData:
    exp_id: str
    session_id: str
    group_id: str = None
    role: str = None
    timestamp: float = field(default_factory=time.time)
    ping: float = field(default_factory=time.time)
    active: bool = True
    type: str = "match_member"


@dataclass
class GroupData:
    exp_id: str
    exp_version: str
    matchmaker_id: str
    roles: dict
    group_id: str = field(default_factory=lambda: uuid4().hex)
    members: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    active: bool = True
    busy: bool = False
    shared_data: dict = field(default_factory=dict)
    type: str = "match_group"


@dataclass
class MatchMakerData:
    exp_id: str
    exp_version: str
    matchmaker_id: str 
    members: dict = field(default_factory=dict)
    busy: bool = False
    active: bool = False
    ping_timeout: int = None
    type: str = "match_maker"


