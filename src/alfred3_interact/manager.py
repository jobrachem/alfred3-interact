import json
from typing import Iterator

from .group import Group
from .member import GroupMember
from ._util import saving_method
from ._util import MatchingError

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

    def waiting(self):
        for m in self.active():
            if m.waiting:
                yield m
        # return (m for m in self.active() if m.waiting)

    def find(self, id: str):
        try:
            return next(m for m in self.members() if m.data.session_id == id)
        except StopIteration:
            raise MatchingError("The member you are looking for was not found.")


class GroupManager:
    def __init__(self, matchmaker):
        self.mm = matchmaker
        self.exp = self.mm.exp

    @property
    def query(self):
        q = {}
        q["type"] = Group.DATA_TYPE
        q["matchmaker_id"] = self.mm.matchmaker_id
        q["exp_id"] = self.mm.exp.exp_id
        return q

    @property
    def path(self):
        return self.mm.io.path.parent

    def groups(self) -> Iterator[Group]:
        if saving_method(self.exp) == "local":
            return self._local_groups()
        elif saving_method(self.exp) == "mongo":
            return self._mongo_groups()
        else:
            raise MatchingError("No saving method found. Try defining a saving agent.")

    def active(self):
        return (g for g in self.groups() if g.active)

    def notfull(self) -> Iterator[Group]:
        return (g for g in self.active() if not g.full)

    def find(self, id: str):
        try:
            return next(g for g in self.groups() if g.data.group_id == id)
        except StopIteration:
            raise MatchingError("The group you are looking for was not found.")

    def _local_groups(self):
        for fpath in self.path.iterdir():
            if fpath.is_dir():
                continue

            elif not fpath.name.startswith("group"):
                continue

            else:
                with open(fpath, "r", encoding="utf-8") as f:
                    gdata = json.load(f)
                    yield Group(matchmaker=self.mm, **gdata)

    def _mongo_groups(self):
        for doc in self.exp.db_misc.find(self.query):
            yield Group(matchmaker=self.mm, **doc)
