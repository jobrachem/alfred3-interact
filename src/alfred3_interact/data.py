import time
from collections import UserDict

from alfred3.util import prefix_keys_safely
from pymongo.collection import ReturnDocument

from ._util import saving_method


class SharedGroupData(UserDict):

    def __init__(self, *args, group, **kwargs):
        super().__init__(*args, **kwargs)
        self.group = group
        self._db = self.group.exp.db_misc
    
    def _push_remote(self):
        doc = self._db.find_one_and_update(
            filter={"group_id": self.group.group_id}, 
            update={"$set": {"shared_data": self.data}},
            projection={"shared_data": True, "_id": False},
            return_document=ReturnDocument.AFTER
            )
        
        self.data = doc["shared_data"]
    
    def _fetch_remote(self):
        doc = self._db.find_one(
            filter={"group_id": self.group.group_id},
            # update={"$set": {"shared_data": {"__last_access": time.time()}}},
            projection={"shared_data": True, "_id": False},
            # return_document=ReturnDocument.AFTER,
            )
        self.data = doc["shared_data"]
    
    def _push_local(self):
        self.group._save()
    
    def _fetch(self):
        if saving_method(self.group.exp) == "mongo":
            self._fetch_remote()
        
        self.data["__last_access"] = time.time()
        self._push()
    
    def _push(self):
        self._push_additional_data()
        self.data["__group_id"] = self.group.group_id
        self.data["__last_change"] = time.time()


        if saving_method(self.group.exp) == "mongo":
            self._push_remote()
        elif saving_method(self.group.exp) == "local":
            self._push_local()
    
    def _push_additional_data(self):
        entry = {"__group_data": self.data}
        self.group.exp.adata.update(entry)

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
        self._push()
    
    def __delitem__(self, key):
        self._fetch()
        super().__delitem__(key)
        self._push()


