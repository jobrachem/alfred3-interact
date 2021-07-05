from .randomizer import GroupRandomizer


class GroupQuota:
    def __init__(self, n, exp, group_type: str, respect_version: bool = True, inclusive: bool = False):
        self.rd = GroupRandomizer(("count", n), exp=exp, group_type=group_type, respect_version=respect_version, randomizer_id=None, inclusive=inclusive)
        self.n = n

    def _update(self, group):
        if not group.data.type.endswith(self.rd.group_type):
            raise ValueError(f"Group type {self.rd.group_type} != {group.data.type}")
        self.rd.group_id = group.data.group_id
        self.rd.session_ids = group.data.members
        

    def count(self, group, raise_exception: bool = False):
        self._update(group)
        self.rd.get_condition(group, raise_exception=raise_exception)
    
    @property
    def nopen(self) -> int:
        return self.rd.nopen
    
    @property
    def npending(self) -> int:
        return self.rd.npending

    @property
    def nslots(self) -> int:
        return self.rd.nslots

    @property
    def nfinished(self) -> int:
        return self.rd.nfinished
        
    @property
    def allfinished(self) -> bool:
        return self.rd.allfinished
