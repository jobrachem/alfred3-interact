from dataclasses import dataclass, field
import random
import time
import typing as t
import json
from typing import List, Iterator

from alfred3._helper import inherit_kwargs
from alfred3.data_manager import DataManager as dm, saving_method
from alfred3.exceptions import AllConditionsFull
from alfred3.randomizer import Slot, ListRandomizer, RandomizerData

from .group import Group


@dataclass
class GroupSlot:
    condition: str
    group_ids: List[str] = field(default_factory=list)

    def get_data(self, exp) -> dict:
        if saving_method(exp) == "local":
            return self._get_data_local(exp)
        elif saving_method(exp) == "mongo":
            return self._get_data_mongo(exp)
    
    def _get_data_mongo(self, exp) -> t.Iterator[dict]:
        return exp.db_misc.find({"group_id": {"$in": self.group_ids}})
    
    def _get_data_local(self, exp) -> t.Iterator[dict]:
        path = exp.config.get("interact", "path", fallback="save/interact")
        path = exp.subpath(path)

        for fp in path.iterdir():
            if not "group" in str(fp):
                continue
            with open(fp, "r", encoding="utf-8") as f:
                group_data = json.load(f)
            if group_data["group_id"] in self.group_ids:
                yield group_data
    
    def most_recent_save(self, exp) -> float:
        data = self.get_data(exp)
        oldest_saves = []
        # for each group, we count the oldest activity of pending members
        # because this is the "weakest link"
        # Thus, we get the newest save time of the slowest member of each group
        for group_data in data:
            # query for active sessions
            members = self._pending_members(exp, group_data, ["exp_save_time"])
            save_times = [m["exp_save_time"] for m in members]
            oldest_saves.append(min(save_times))
        
        # from the oldest activities, we take the newest one
        return max(oldest_saves)
    
    def _pending_members(self, exp, group_data, projection: t.Union[dict, list] = None) -> t.Iterator[dict]:
        if saving_method(exp) == "local":
            return self._pending_members_local(exp, group_data)
        elif saving_method(exp) == "mongo":
            return self._pending_members_mongo(exp, group_data, projection)
    
    def _pending_members_local(self, exp, group_data) -> t.Iterator[dict]:
        earliest_start = time.time() - exp.session_timeout
        path = exp.config.get("local_saving_agent", "path")
        path = exp.subpath(path)
        for session_data in dm.iterate_local_data(dm.EXP_DATA, path):
            in_group = session_data["exp_session_id"] in group_data["members"]
            aborted = session_data["exp_aborted"]
            finished = session_data["exp_finished"]
            start = session_data["exp_start_time"]
            expired = False if start is None else start < earliest_start
            if in_group and not aborted and not finished and not expired:
                yield session_data
    
    def _pending_members_mongo(self, exp, group_data, projection: t.Union[dict, list] = None) -> t.Iterator[dict]:
        earliest_start = time.time() - exp.session_timeout

        q = {
                "type": dm.EXP_DATA,
                "exp_session_id": {"$in": group_data["members"]},
                "exp_finished": False,
                "exp_aborted": False,
                "$or": [{"exp_start_time": {"$gte": earliest_start}}, {"exp_start_time": None}]
            }
        
        return exp.db_main.find(q, projection=projection)
    
    def npending(self, exp) -> int:
        if saving_method(exp) == "local":
            return self._npending_groups_local(exp)
        elif saving_method(exp) == "mongo":
            return self._npending_groups_mongo(exp)
        
    def _count_pending(self, exp, members, data: list, cursor: t.Iterator):
        earliest_start = time.time() - exp.session_timeout
        gids = [d["group_id"] for d in data]
        
        counts = {gid: 0 for gid in gids}
        exited = {gid: False for gid in gids}
        
        for session_data in cursor:
            aborted = session_data["exp_aborted"]
            finished = session_data["exp_finished"]
            start = session_data["exp_start_time"]
            expired = False if start is None else start < earliest_start
            
            gid = members.get(session_data["exp_session_id"], None)

            if gid and not aborted and not finished and not expired:
                counts[gid] += 1
            
            if "groupwise" in data[0]["type"] and (aborted or expired):
                exited[gid] = True
        
        pending = [gid for gid, npending in counts.items() if npending > 0 and gid not in exited]
        
        return len(pending)

    def _npending_groups_local(self, exp) -> int:
        data = self.get_data(exp)
        data = list(data)
        
        path = exp.config.get("local_saving_agent", "path")
        path = exp.subpath(path)
        cursor = dm.iterate_local_data(dm.EXP_DATA, path)
        
        members = {}
        for group_data in data:
            members.update({sid: group_data["group_id"] for sid in group_data["members"]})

        return self._count_pending(exp, members, data, cursor)
    
    def _npending_groups_mongo(self, exp) -> int:
        p = ["group_id", "members", "type"]
        data = exp.db_misc.find({"group_id": {"$in": self.group_ids}}, projection=p)
        data = list(data)
        members = {}
        for group_data in data:
            members.update({sid: group_data["group_id"] for sid in group_data["members"]})
        
        q = {"exp_session_id": {"$in": list(members)}, "type": dm.EXP_DATA}
        p = ["exp_finished", "exp_aborted", "exp_start_time", "exp_session_id"]
        cursor = exp.db_main.find(q, p)

        return self._count_pending(exp, members, data, cursor)

    def _finished_members(self, exp, group_data: dict, projection: t.Union[dict, list]) -> t.Iterator[dict]:
        if saving_method(exp) == "local":
            return self._finished_members_local(exp, group_data)
        elif saving_method(exp) == "mongo":
            return self._finished_members_mongo(exp, group_data, projection)
    
    def _finished_members_local(self, exp, group_data: dict) -> t.Iterator[dict]:
        path = exp.config.get("local_saving_agent", "path")
        path = exp.subpath(path)
        for session_data in dm.iterate_local_data(dm.EXP_DATA, path):
            sid = session_data["exp_session_id"]
            finished = session_data["exp_finished"]
            if sid in group_data["members"] and finished:
                yield session_data
    
    def _finished_members_mongo(self, exp, group_data: dict, projection: t.Union[dict, list]) -> t.Iterator[dict]:
        q = {
                "type": dm.EXP_DATA,
                "exp_session_id": {"$in": group_data["members"]},
                "exp_finished": True,
            }
        
        return exp.db_main.find(q, projection=projection)

    def finished(self, exp) -> bool:
        data = self.get_data(exp)

        for group_data in data:
            cursor = self._finished_members(exp, group_data, ["exp_finished"])
            nfinished = sum([session["exp_finished"] for session in cursor])
            nroles = len(group_data["roles"])

            if nfinished == nroles:
                return True

        return False

    def pending(self, exp) -> bool:
        return not self.finished(exp) and not self.open

    @property
    def open(self) -> bool:
        return not self.group_ids

    def __contains__(self, group_ids: List[str]) -> bool:
        if self.group_ids is None:
            return False
        group_in_slot = [gid in self.group_ids for gid in group_ids]
        return any(group_in_slot)


@dataclass
class GroupSlotManager:
    slots: List[dict]

    def __post_init__(self):
        self.slots = [GroupSlot(**slot_data) for slot_data in self.slots]

    def open_slots(self, exp) -> Iterator[Slot]:
        return (slot for slot in self.slots if slot.open)

    def pending_slots(self, exp) -> Iterator[Slot]:
        return (slot for slot in self.slots if slot.pending(exp))

    def find_slot(self, group_ids: List[str]) -> Slot:
        for slot in self.slots:
            if group_ids in slot:
                return slot
    
    def next_pending(self, exp) -> Slot:
        """
        This method returns the next pending slot that is
        most likely not to finish the experiment.

        1. If there is only one pending slot, this slot is returned
        2. The slot with the least number of pending groups operating
           in it is returned.
        3. If there are multiple slots with equal numbers of pending
           groups, the method returns the slot where the most recent
           activity of the slowest member is oldest - because this slot
           is most likely to need extra groups.
        """
        slots = list(self.pending_slots(exp))
        
        if len(slots) == 1:
            return slots[0]
        
        slots = self._sparsest_slots(slots, exp)

        if len(slots) == 1:
            return slots[0]
        
        return self._oldest_slot(slots, exp)
    
    def _sparsest_slots(self, slots, exp) -> List[Slot]:

        npending = [slot.npending(exp) for slot in slots]
        n = min(npending)
        minimal_pending = [slot for slot in slots if slot.npending(exp) == n]
        if len(minimal_pending) == 1:
            return minimal_pending
        else:
            return minimal_pending
    
    def _oldest_slot(self, slots, exp) -> Slot:
        most_recent_save = [slot.most_recent_save(exp) for slot in slots]
        oldest = min(most_recent_save)
        i = most_recent_save.index(oldest)
        return slots[i]

# TODO add group type argument!
class GroupRandomizer(ListRandomizer):
    def __init__(
        self, *conditions, exp, group_type: str, randomizer_id: str = "group_randomizer", **kwargs
    ):

        if kwargs.pop("session_ids", False):
            raise ValueError("Unsupported argument: 'session_ids'")

        super().__init__(*conditions, exp=exp, randomizer_id=randomizer_id, **kwargs)
        self.group_type = group_type
        self.group_id = None
        self.session_ids = None
    
    def get_condition(self, group, raise_exception: bool = False):
        if not group.data.type.endswith(self.group_type):
            raise ValueError(f"Group type {group.data.type} != {self.group_type}")
        self.group_id = group.data.group_id
        self.session_ids = group.data.members

        return super().get_condition(raise_exception)

    @staticmethod
    def _use_comptability(**kwargs) -> bool:
        return False

    def _update_slot(self, slot):
        if "stepwise" in self.group_type:
            return slot.group_ids.append(self.group_id)
        else:
            return super()._update_slot(slot)

    def _own_slot(self, data: RandomizerData):
        if "stepwise" in self.group_type:
            slot_manager = self.slot_manager(data)
            slot = slot_manager.find_slot([self.group_id])
            return slot
        else:
            return super()._own_slot(data)

    def slot_manager(self, data: RandomizerData):
        if "stepwise" in self.group_type:
            return GroupSlotManager(data.slots)
        else:
            return super().slot_manager(data)


def random_matchmaker(
    *spec,
    raise_exception: bool = False,
    abort_page = None,
):
    """

    .. warning::
        The number of groups that you wish to collect with each 
        matchmaker

    Returns:
        MatchMaker

    Raises:
        AllConditionsFull
    """
    mm_ids = [mm[0].matchmaker_id for mm in spec]
    if len(set(mm_ids)) != len(spec):
        raise ValueError("MatchMakers must have different ids for randomization.")
    
    quotas = [mm[0].quota for mm in spec]
    if not all(quotas):
        raise ValueError("All MatchMakers must have a quota for randomization.")
    
    random.shuffle(spec)

    for matchmaker, n in spec:
        exp = matchmaker.exp
        quota = matchmaker.quota

        if quota.nopen > 0:
            return matchmaker
        elif not quota.inclusive:
            continue
        elif quota.npending > 0:
            return matchmaker

    if raise_exception:
        raise AllConditionsFull
    else:
        full_page_title = "Experiment closed"
        full_page_text = (
            "Sorry, the experiment currently does not accept any further participants."
        )
        exp.abort(
            reason="full",
            title=full_page_title,
            msg=full_page_text,
            icon="user-check",
            page=abort_page,
        )
