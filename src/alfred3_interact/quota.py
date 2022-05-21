from dataclasses import asdict, dataclass, field
import time
import json
from typing import List, Iterator
import typing as t

from alfred3.data_manager import DataManager as dm, saving_method
from alfred3.quota import Slot, SessionQuota, QuotaData, SlotManager
from alfred3._helper import inherit_kwargs

from .group import GroupType


@dataclass
class GroupSlot:
    label: str
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

    def _pending_members(
        self, exp, group_data, projection: t.Union[dict, list] = None
    ) -> t.Iterator[dict]:
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

    def _pending_members_mongo(
        self, exp, group_data, projection: t.Union[dict, list] = None
    ) -> t.Iterator[dict]:
        earliest_start = time.time() - exp.session_timeout

        q = {
            "type": dm.EXP_DATA,
            "exp_session_id": {"$in": group_data["members"]},
            "exp_finished": False,
            "exp_aborted": False,
            "$or": [{"exp_start_time": {"$gte": earliest_start}}, {"exp_start_time": None}],
        }

        return exp.db_main.find(q, projection=projection)

    def npending(self, exp) -> int:
        counts = self._npending_members(exp)
        npending_groups = len([gid for gid, npending in counts.items() if npending > 0])
        return npending_groups

    def _npending_members(self, exp) -> dict:
        if saving_method(exp) == "local":
            counts = self._npending_groups_local(exp)
        elif saving_method(exp) == "mongo":
            counts = self._npending_groups_mongo(exp)

        return counts

    def _count_pending(self, exp, members, data: list, cursor: t.Iterator) -> dict:
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

        return counts

    def _npending_groups_local(self, exp) -> int:
        data = self.get_data(exp)
        data = list(data)

        path = exp.config.get("local_saving_agent", "path")
        path = exp.subpath(path)
        cursor = dm.iterate_local_data(dm.EXP_DATA, path)

        members = {}
        for group_data in data:
            members.update({sid: group_data["group_id"] for sid in group_data["members"]})

        counts = self._count_pending(exp, members, data, cursor)

        return counts

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
        counts = self._count_pending(exp, members, data, cursor)

        return counts

    def _finished_members(
        self, exp, group_data: dict, projection: t.Union[dict, list]
    ) -> t.Iterator[dict]:
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

    def _finished_members_mongo(
        self, exp, group_data: dict, projection: t.Union[dict, list]
    ) -> t.Iterator[dict]:
        q = {
            "type": dm.EXP_DATA,
            "exp_session_id": {"$in": group_data["members"]},
            "exp_finished": True,
        }

        return exp.db_main.find(q, projection=projection)

    # def contains_incomplete_group(self, exp) -> bool:
    #     # case 1: at least one existing member is pending
    #     # case 2: no existing member is pending (either finished or aborted)

    #     counts_pending = self._npending_members(exp)
    #     counts_finished = self._nfinished_members(exp)

    #     data = self.get_data(exp)

    #     finished = []
    #     incomplete = []

    #     for group_data in data:
    #         cursor = self._finished_members(exp, group_data, ["exp_finished"])
    #         gid = group_data["group_id"]

    #         nroles = len(group_data["roles"])
    #         nfinished = sum([session["exp_finished"] for session in cursor])
    #         nfilled = counts_pending[gid] + counts_finished[gid]

    #         finished.append(nfinished == nroles)
    #         incomplete.append(nfilled < nroles)

    #     return not any(finished) and any(incomplete)

    def _nfinished_members(self, exp):
        data = self.get_data(exp)

        counts = {}
        for group_data in data:
            cursor = self._finished_members(exp, group_data, ["exp_finished"])
            nfinished = sum([session["exp_finished"] for session in cursor])
            gid = group_data["group_id"]
            counts[gid] = nfinished

        return counts

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

    # def incomplete_slots(self, exp) -> Iterator[Slot]:
    #     return (slot for slot in self.slots if slot.contains_incomplete_group(exp))

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
        return minimal_pending

    def _oldest_slot(self, slots, exp) -> Slot:
        most_recent_save = [slot.most_recent_save(exp) for slot in slots]
        oldest = min(most_recent_save)
        i = most_recent_save.index(oldest)
        return slots[i]


@inherit_kwargs(exclude=["session_ids"])
class ParallelGroupQuota(SessionQuota):
    """
    Manages quota for parallel groups.

    Args:
        {kwargs}
    """

    group_type = GroupType.PARALLEL

    def __init__(self, nslots: int, exp, name: str = "group_quota", **kwargs):
        if kwargs.pop("session_ids", False):
            raise ValueError("Unsupported argument: 'session_ids'")

        super().__init__(nslots=nslots, exp=exp, name=name, **kwargs)
        self.group_id = None

    @staticmethod
    def _use_comptability(**kwargs) -> bool:
        return False

    def count(self, group, raise_exception: bool = False):
        if not group.data.group_type == self.group_type:
            raise ValueError(f"Group type {group.gtype} != {self.group_type}")
        self.group_id = group.data.group_id
        self.session_ids = group.data.members

        return super().count(raise_exception)

    def _slot_manager(self, data: QuotaData):
        try:
            return SlotManager(data.slots)
        except TypeError as e:
            group_ids = [slot.get("group_ids", False) for slot in data.slots]
            if any(group_ids):
                raise ValueError(
                    (
                        "Tried to initialize a quota for a parallel spec "
                        "with data for a sequential spec quota. This can occur, if you use the same"
                        "name for different specs. Please make sure that all names are unique."
                    )
                )
            else:
                raise e


@inherit_kwargs(exclude=["session_ids"])
class SequentialGroupQuota(ParallelGroupQuota):
    """
    Manages quota for sequential groups.

    Args:
        {kwargs}
    """

    group_type = GroupType.SEQUENTIAL

    def _update_slot(self, slot):
        return slot.group_ids.append(self.group_id)

    def _own_slot(self, data: QuotaData):
        slot_manager = self._slot_manager(data)
        slot = slot_manager.find_slot([self.group_id])
        return slot

    def _slot_manager(self, data: QuotaData):
        try:
            return GroupSlotManager(data.slots)
        except TypeError as e:
            session_groups = [slot.get("session_groups", False) for slot in data.slots]
            if any(session_groups):
                raise ValueError(
                    (
                        "Tried to initialize a quota for a sequential spec "
                        "with data for a parallel spec quota. This can occur, if you use the same"
                        "name for different specs. Please make sure that all names are unique."
                    )
                )
            else:
                raise e

    @property
    def full(self) -> bool:
        """
        bool: *True*, if all slots are taken *and* no group currently
        takes members.
        """
        with self.io as data:
            nopen = self._nopen(data)

            if nopen > 0:
                return False

            npending = self._npending(data)

            # no pending and no open slots means that the quota is allfinished
            if npending == 0:
                return True

            # pending is > 0, inclusive quota will allow new groups to be formed
            if self.inclusive:
                return False

            # Exclusive quota with pending slots and all groups in
            # those slots are complete. Thus, the quota is full
            return True


class MetaQuota:
    """
    Gives access to aggregated information about open, pending, and
    finished slots of multiple individual quotas.

    Args:
        *quotas: Variable number of quota
    """

    def __init__(self, *quotas):
        self.quotas = quotas

    @property
    def nopen(self) -> int:
        """
        int: Number of open slots.

        A slot is open, if there is no
        active or finished experiment session (or group of experiment
        sessions) associated with this slot.
        """
        return sum([quota.nopen for quota in self.quotas])

    @property
    def npending(self) -> int:
        """
        int: Number of pending slots.

        A slot is pending, if there is currently an active session
        (or group of sessions) associated with this slot.
        """
        return sum([quota.npending for quota in self.quotas])

    @property
    def nslots(self) -> int:
        """
        int: Total number of available slots.
        """
        return sum([quota.nslots for quota in self.quotas])

    @property
    def nfinished(self) -> int:
        """
        int: Number of finished slots.

        A slot is finished, if at least one session (or group of
        sessions in case of group quotas) associated with this slot has
        finished the experiment.
        """
        return sum([quota.nfinished for quota in self.quotas])

    @property
    def allfinished(self) -> bool:
        """
        bool: *True*, if all slots are finished.

        A slot is finished, if at least one session (or group of
        sessions in case of group quotas) associated with this slot has
        finished the experiment.
        """
        return all([quota.allfinished for quota in self.quotas])

    @property
    def full(self) -> bool:
        """
        bool: *True*, if all quotas are full.

        A quota is full, if there are no slots available to assign to
        sessions or groups.
        """
        return all([quota.full for quota in self.quotas])
