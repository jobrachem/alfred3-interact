"""
Interfaces for defining groups.
"""

from abc import ABC, abstractmethod
from dataclasses import asdict
import re
import typing as t
import random

from .quota import ParallelGroupQuota, SequentialGroupQuota
from .group import Group, GroupManager, GroupType, BusyGroup
from .member import GroupMember
from ._util import saving_method, NoMatch, MatchingError


class SequentialMatchMaker:
    group_type = GroupType.SEQUENTIAL

    def __init__(self, *roles, matchmaker, ongoing_sessions_ok: bool, spec_name: str):
        self.roles = roles
        self.mm = matchmaker
        self.ongoing_sessions_ok = ongoing_sessions_ok

        self.log = self.mm.log
        self.group_manager = GroupManager(self.mm, self.group_type, spec_name)

        self.data = {
            "roles": self.roles, 
            "group_type": self.group_type,
            "spec_name": spec_name
        }

    @property
    def any_group_takes_members(self) -> bool:
        return any(self.group_manager.takes_members(self.ongoing_sessions_ok))

    def match(self) -> Group:
        if self.ongoing_sessions_ok and saving_method(self.mm.exp) == "local":
            raise ValueError("ongoing_sessions_ok=True is not supported in local experiments.")

        if self.mm.member.matched:
            group = self.group_manager.find_one(self.mm.member.group_id)

        elif self.any_group_takes_members:
            try:
                group = self.match_next_group()
            except BusyGroup:
                self.log.warning("Match to existing group failed. Starting new group.")
                group = self.start_group()
        else:
            group = self.start_group()

        return group

    def start_group(self) -> Group:
        
        with Group(self.mm, **self.data) as group:
            self.log.info(f"Starting new group: {group}.")

            group += self.mm.member

            role = group.roles.next()
            group.roles.assign(role, self.mm.member)

            self.mm.member.io.save()
            group.io.save()
            self.log.info(f"Session matched to role '{self.mm.member.data.role}' in {group}.")
            return group

    def match_next_group(self) -> Group:
        with self.group_manager.next(self.ongoing_sessions_ok) as group:
            self.log.info(f"Starting stepwise match of session to existing group: {group}.")

            group += self.mm.member
            role = group.roles.next()
            group.roles.assign(role, self.mm.member)

            self.mm.member.io.save()
            group.io.save()

            self.log.info(f"Session matched to role '{self.mm.member.data.role}' in {group}.")
            return group


class ParallelMatchMaker:
    group_type = GroupType.PARALLEL

    def __init__(self, *roles, matchmaker, spec_name: str, shuffle_waiting_members: bool = True):
        self.roles = roles
        self.mm = matchmaker

        self.group_manager = GroupManager(self.mm, self.group_type, spec_name)
        self.log = self.mm.log

        self.data = {
            "roles": self.roles, 
            "group_type": self.group_type,
            "spec_name": spec_name
        }

        self.shuffle_waiting_members = shuffle_waiting_members


    def match(self) -> Group:
        if saving_method(self.mm.exp) == "local":
            raise MatchingError("Cannot match with parallel specs in local experiments.")

        with self.mm.io as data:

            if data is None:
                self.log.debug("No groupwise match conducted. MatchMaker is busy.")
            else:    
                existing_group = self.get_group()
                if existing_group:
                    return existing_group

                waiting_members = self.mm.waiting_members
                enough_members_waiting = len(waiting_members) >= len(self.roles)
                
                if enough_members_waiting:
                    group = self.start_group(data, waiting_members)
                    return group
        
        raise NoMatch # if match is not successful    


    def start_group(self, data, waiting_members: t.List[GroupMember]) -> Group:

        with Group(self.mm, **self.data) as group:
            self.log.info(f"Starting new group {group}.")

            if self.shuffle_waiting_members:
                me = waiting_members[0]
                others = waiting_members[1:]
                random.shuffle(others)
                waiting_members = [me] + others

            candidates = (m for m in waiting_members)

            group.roles.shuffle()

            while not len(group.data.members) == len(group.data.roles):
                member = next(candidates)
                group += member

                role = next(group.roles.open())
                group.roles.assign(role, member)

                data.members[member.data.session_id] = asdict(member.data)

            group.io.save()
            self.mm.io.save(data=data)

            self.log.info(f"Group {group} filled. Returning group")
            return group

    def get_group(self) -> Group:
        member = self.mm.member
        member.io.load()
        if member.status.matched:
            group = self.group_manager.find_one(member.data.group_id)
            return group


class Spec(ABC):
    
    @abstractmethod
    def _match(self):
        pass


class ParallelSpec(Spec):
    """
    Interface for defining a parallel group.

    A parallel group is a group in which participants complete the
    experiments in parallel, i.e. they are all active simultaneously
    and can interact in real-time.

    Args:
        *roles (str): A variable number of strings, indicating which roles
            will be appointed to members of the group. The number of
            roles determines the number of group members. All roles in a
            group must be unique. Roles cannot start with numbers or
            contain spaces.
        nslots (int): Maximum number of groups that should be created
            based on this spec.
        name (str): A unique identifier for the spec.
        respect_version (bool): If True, the matchmaking will only include
            sessions that run on the same experiment version. This setting
            makes sure that there's no strange behavior if you make
            changes to an ongoing experiment.
            Defaults to True.
        inclusive (bool): If *False* (default), the quota will only assign a
            slot, if there are no pending sessions for that slot. See
            :class:`.SequentialGroupQuota` / :class:`.ParallelGroupQuota`
            for more details.
        shuffle_waiting_members (bool): If *True*, the list of waiting
            members will be shuffled before starting a new group. If
            *False*, members who have been waiting longest are 
            prioritized.

    See Also:
        See :class:`.SequentialSpec` for an interface for defining a sequential group
        and :class:`.IndividualSpec` for defining an individual session spec.
    """

    group_type = GroupType.PARALLEL
    pattern = re.compile(r"^\d|\s")
    _QUOTA_TYPE = ParallelGroupQuota

    def __init__(
        self,
        *roles,
        nslots: int,
        name: str,
        respect_version: bool = True,
        inclusive: bool = False,
        count: bool = True,
        shuffle_waiting_members: bool = True
    ):



        if len(roles) != len(set(roles)):
            raise ValueError("All roles in a group must be unique.")

        self.roles = self._validate_roles(roles)
        self.name = name
        self.nslots = nslots
        self.respect_version = respect_version
        self.count = count
        self.inclusive = inclusive
        self._quota = None

        self.ongoing_sessions_ok = False

        self._shuffle_waiting_members = shuffle_waiting_members
    
    def _init_quota(self, exp):
        if self.count:
            self._quota = self._QUOTA_TYPE(
                nslots=self.nslots, exp=exp, respect_version=self.respect_version, inclusive=self.inclusive, name=f"{self.name}_quota"
            )

    @property
    def quota(self):
        """
        Access to the spec's :class:`.SequentialGroupQuota`,
        or :class:`.ParallelGroupQuota`,
        depending on the type of spec.
        """
        return self._quota
    
    def _match(self, match_maker):
        mm = ParallelMatchMaker(
            *self.roles,
            matchmaker=match_maker,
            spec_name=self.name,
            shuffle_waiting_members=self._shuffle_waiting_members
        )

        group = mm.match()
        return group

    def _validate_roles(self, roles):
        for role in roles:

            if self.pattern.search(role):
                raise ValueError(
                    f"Error in role '{role}': Roles cannot start with numbers \
                    and must not contain spaces."
                )

        return roles
    
    def __repr__(self):
        return f"{type(self).__name__}(roles={self.roles}, name='{self.name}')"

    def full(self, match_maker):
        return self.quota.full

class SequentialSpec(ParallelSpec):
    """
    Interface for defining a sequential group.

    A sequential group is a group in which participants complete the
    experiments not in parallel, but sequentially. That means, they
    do not interact in real-time. Instead, the first participant
    completes their session, and the next participant can access data
    from the first participant.

    Args:
        *roles (str): A variable number of strings, indicating which roles
            will be appointed to members of the group. The number of
            roles determines the number of group members. All roles in a
            group must be unique. Roles cannot start with numbers or
            contain spaces.
        nslots (int): Maximum number of groups that should be created
            based on this spec.
        name (str): A unique identifier for the spec.
        respect_version (bool): If True, the matchmaking will only include
            sessions that run on the same experiment version. This setting
            makes sure that there's no strange behavior if you make
            changes to an ongoing experiment.
            Defaults to True.
        inclusive (bool): If *False* (default), the quota will only assign a
            slot, if there are no pending sessions for that slot. See
            :class:`.SequentialGroupQuota` / :class:`.ParallelGroupQuota`
            for more details.
        ongoing_sessions_ok (bool): If False (default), new members will only
            be added to a group if all previous members of that group
            have finished their experiment sessions.

    See Also:
        See :class:`.ParallelSpec` for an interface for defining a parallel group
        and :class:`.IndividualSpec` for defining an individual session spec.
    """

    group_type = GroupType.SEQUENTIAL
    _QUOTA_TYPE = SequentialGroupQuota

    def __init__(
        self,
        *roles: str,
        nslots: int,
        name: str,
        respect_version: bool = True,
        inclusive: bool = False,
        ongoing_sessions_ok: bool = False,
        count: bool = True
    ):
        super().__init__(
            *roles,
            nslots=nslots,
            name=name,
            respect_version=respect_version,
            inclusive=inclusive,
            count=count
        )
        self.ongoing_sessions_ok = ongoing_sessions_ok
    
    def _match(self, match_maker):
        mm = SequentialMatchMaker(
            *self.roles,
            matchmaker=match_maker,
            ongoing_sessions_ok=self.ongoing_sessions_ok,
            spec_name=self.name,
        )

        group = mm.match()
        return group

    def _any_group_takes_members(self, match_maker) -> bool:
        mm = SequentialMatchMaker(
            *self.roles,
            matchmaker=match_maker,
            ongoing_sessions_ok=self.ongoing_sessions_ok,
            spec_name=self.name,
        )

        return mm.any_group_takes_members
    
    def full(self, match_maker) -> bool:
        any_group_takes_members = self._any_group_takes_members(match_maker)
        quota_full = self.quota.full

        return quota_full and not any_group_takes_members


class IndividualSpec(SequentialSpec):
    """
    Interface for defining an 'individual group spec'.

    The IndividualSpec can be used to include an individual condition
    in a MatchMaker speclist. The usecase arises, if you want to
    randomize the assignment of participants to at least one group
    specification and at least one individual condition.

    Args:
        nslots (int): Maximum number of sessions that should be created
            based on this spec.
        name (str): A unique identifier for the spec.
        respect_version (bool): If True, the quota will only include
            sessions that run on the same experiment version. This setting
            makes sure that there's no strange behavior if you make
            changes to an ongoing experiment.
            Defaults to True.
        inclusive (bool): If *False* (default), the quota will only assign a
            slot, if there are no pending sessions for that slot. See
            :class:`.SequentialGroupQuota` / :class:`.ParallelGroupQuota`
            for more details.

    See Also:
        See :class:`.SequentialSpec` for an interface for defining a sequential group
        and :class:`.ParallelSpec` for defining a parallel group.

    """

    def __init__(
        self, nslots: int, name: str, respect_version: bool = True, inclusive: bool = False,
        count: bool = True
    ):
        self.roles = self._validate_roles(["individual"])
        self.name = name
        self.nslots = nslots
        self.count = count
        self.respect_version = respect_version
        self.inclusive = inclusive
        self.ongoing_sessions_ok = False
