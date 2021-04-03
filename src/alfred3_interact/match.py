
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
from .group import GroupManager
from .member import GroupMember
from .member import MemberManager
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
        q["type"] = self.mm._DATA_TYPE
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
    """
    Organizes the creation and composition of groups for interactive
    experiments.

    Args:
        *roles: A variable number of strings, indicating which roles
            will be appointed to members of the group. The number of
            roles determines the number of group members. All roles in a
            group must be unique.
        exp (alfred3.experiment.ExperimentSession): The alfred3 experiment
            in which this matchmaker is used.
        id (str): Used in combination with the experiment ID as unique
            identifier for the MatchMaker.  Defaults to 'matchmaker', 
            which is usually fine, unless you are using multiple 
            matchmakers in one experiment.
        respect_version (bool): If True, the matchmaker will only match
            sessions that run on the same experiment version into the
            same group. This setting makes sure that there's no strange
            behavior if you make changes to an ongoing experiment. 
            Defaults to True.
    

    First, you initialize the MatchMaker with the roles that you
    need and the experiment session object::

        import alfred3 as al
        from alfred3_interact import MatchMaker

        exp = al.Experiment()

        @exp.setup
        def setup(exp):
            mm = MatchMaker("a", "b", exp=exp) # Initialize the MatchMaker
        
        exp += al.Page(name="demo")

    Next, you use either :meth:`.match_stepwise` or :meth:`.match_groupwise`
    to match the experiment session to a group. Both methods return
    a :class:`.Group` object, which is the gateway to the data of all
    group members. You should include this group in the "plugins"
    attribute of the experiment session::

        import alfred3 as al
        from alfred3_interact import MatchMaker

        exp = al.Experiment()

        @exp.setup
        def setup(exp):
            mm = MatchMaker("a", "b", exp=exp)
            exp.plugins.group = mm.match_stepwise() # Assign and return a group
        
        exp += al.Page(name="demo")
    
    The group object offers the attribute :attr:`.Group.me`, which always
    refers to the :class:`.GroupMember` object of the current experiment
    session - most importantly, this attribute can be used to get to know
    the role of the present session::

        import alfred3 as al
        from alfred3_interact import MatchMaker

        exp = al.Experiment()

        @exp.setup
        def setup(exp):
            mm = MatchMaker("a", "b", exp=exp)
            exp.plugins.group = mm.match_stepwise()
            print(exp.plugins.group.me.role) # Print own role
        
        exp += al.Page(name="demo")
    
    Beyond "me", the group object offers :attr:`.Group.you`, which always
    refers to the other participant *in groups of size two* (it cannot 
    be used in bigger groups). On top of that, all members of a group
    can be referenced through the group via their role::

        import alfred3 as al
        from alfred3_interact import MatchMaker

        exp = al.Experiment()

        @exp.setup
        def setup(exp):
            mm = MatchMaker("a", "b", exp=exp)
            exp.plugins.group = mm.match_stepwise()
            print(exp.plugins.group.a) # Accessing the GroupMember with role "a"
        
        exp += al.Page(name="demo")

    The :class:`.GroupMember` object then serves as a gateway to the
    data collected in a specific member's session. For example,
    :attr:`.GroupMember.values` offers access to the values of all
    input elements that have been filled by the referenced member.
    
    You can complete the matchmaking process in the 
    :meth:`alfred3.experiment.Experiment.setup`
    hook, but it is usually advisable to use the
    :meth:`.WaitingPage.wait_for` hook of a :class:`.WaitingPage`. That
    way you have two advantages. First, you have more control over the
    exact moment in which you want to allow participants into the
    matchmaking process (for example, after they read initial 
    instructions). Second, the WaitingPage offers a nice visual display
    that informs participants about the ongoing matchmaking and about
    how much time has passed.

    After successful matchmaking, you can use the :class:`.WaitingPage`
    throughout the experiment whenever you need to make sure that group
    members have progressed to a certain point in the experiment. For
    example, role "b" may need some data from role "a" on their fith page.
    So, before the fith page, you place a WaitingPage that will pause "b"'s
    session until "a" has progressed far enough through the experiment,
    so that the required data is available.
    
    Notes:
        See :meth:`.match_stepwise` and :meth:`.match_groupwise` for 
        more information and examples. Also, there is an alternative
        constructor :meth:`.from_size`.
        
    """


    _TIMEOUT_MSG = "MatchMaking timeout"
    _DATA_TYPE = "match_maker"

    def __init__(
        self,
        *roles,
        exp: ExperimentSession,
        id: str = "matchmaker",
        respect_version: bool = True,
    ):
        self.exp = exp
        self.exp_version = self.exp.version if respect_version else ""
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)

        self.member_timeout = None
        
        #: Number of seconds after which a single
        #: group-operation will be considered to have failed. In this
        #: case, the group in question will be marked as inactive and
        #: not be included in further matchmaking. Defaults to 300 seconds
        #: (5 minutes).
        self.group_timeout = 10
        
        if len(roles) != len(set(roles)):
            raise ValueError("All roles in a group must be unique.")

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
    def from_size(cls, n: int, **kwargs):
        """
        Creates a matchmaker instance on the basis of the number
        of group members.

        Args:
            n (int): The number of group members.
            **kwargs: Further keyword arguments passed on to the usual
                constructor.

        Notes:
            Group roles will be the letters of the alphabet: First small
            letters, then capitalized, then repeated small letters 
            (e.g. "aa"), and so on.
        """
        roles = []
        for i in range(n):
            letter = string.ascii_letters[i]
            while letter in roles:
                letter = letter + string.ascii_letters[i]
            roles.append(letter)
        
        return cls(*roles, **kwargs)
    
    @property
    def member_timeout(self) -> int:
        """
        int: Timeout, after which members will be marked as inactive.
        """
        return self._member_timeout
    
    @member_timeout.setter
    def member_timeout(self, value: int):
        self._member_timeout = value if value is not None else self.exp.session_timeout

    @property
    def data(self) -> MatchMakerData:
        """
        MatchMakerData: The MatchMaker's underlying data.
        """
        self._data.members[self.member.session_id] = asdict(self.member.data)
        return self._data

    def match_stepwise(self, member_timeout: int = None) -> Group:
        """
        Assigns participants to groups and roles one-by-one without 
        waiting for a group to be full.

        Args:
            member_timeout (int): Number of seconds after which an experiment
                session is considered inactive. Inactive sessions are not
                included in the matchmaking process (but can in principle
                still finish their session). The roles of inactive sessions 
                will be free for allocation to new members. If None, 
                :attr:`alfred3.experiment.ExperimentSession.session_timeout`
                will be used. Defaults to None.
        
        
        Roles are assigned to members in order.
        
        This method is the correct choice for groups that can operate
        in an asynchronous fashion. One example for such a setting is
        a "yoking" setup. 
        
        Let's take a yoking group with two members, "a" and "b", as an 
        example: The first participant starts her experiment 
        and is immediately assinged to role "a". She finishes her 
        experiment without needing access to any values from participant 
        "b". The next participant is assigned to role "b". In his version
        of the experiment, some aspects depend on the inputs of 
        participant "a".

        Examples:
            ::

                import alfred3 as al
                from alfred3_interact import MatchMaker
                
                exp = al.Experiment()

                @exp.setup
                def setup(exp):
                    mm = MatchMaker("a", "b", exp=exp)
                    exp.plugins["group"] = mm.match_stepwise()
                
                @exp.member
                class Demo(al.Page):

                    def on_first_show(self):
                        role = self.exp.plugins.group.me.role
                        self += al.Text(f"I was assigned to role '{role}'.")

        """
        self.member_timeout = member_timeout
        self.member = GroupMember(self)
        self.member._save()

        # match to existing group
        if any(self.group_manager.notfull()):
            try:
                self.group = self._match_next_group()
            except BusyGroup:
                self.group = self._wait_until_free(self.group_timeout)
            
            self.log.info(f"Session matched to role '{self.member.role}' in {self.group}.")
            self._save_infos()
            return self.group

        # start a new group
        else:
            roles = {role: None for role in self.roles}
            with Group(self, roles=roles) as group:
                self.log.info(f"Starting new group: {group}.")

                group += self.member
                group._assign_next_role(to_member=self.member)
                self.member._save()
                self.group = group
                self.log.info(f"Session matched to role '{self.member.role}' in {group}.")

            self._save_infos()
            return self.group

    def match_groupwise(self, match_timeout: int = 60 * 30, ping_timeout: int = 15, timeout_page = None, raise_exception: bool = False) -> Group:
        """
        Waits until there are enough participants for a full group, then
        matches them together.

        Args:
            timeout_page (alfred3.page.Page): A custom page to display to
                participants if matchmaking times out. This will replace the
                default timeout page.
            match_timeout (int): Number of seconds after which a matching
                procedure will be considered to have failed. In this case,
                the experiment will be aborted and the group in question will
                be marked as inactive and not included in further matchmaking.
                This timeout determines the maximum waiting time for
                a group to be complete. Defaults to 1,800 (30 minutes).
            ping_timeout (int): Number of seconds after which an experiment
                session will be excluded from groupwise matching. This makes
                sure that only currently active sessions will be allocated
                to a group. Defaults to 15 (seconds).
            raise_exception (bool): If True, the matchmaker will raise 
                a :class:`.MatchingTimeout` exception instead of aborting
                the experiment if the matchmaking times out. This is useful,
                if you want to catch the exception and customize the 
                experiment's behavior in this case. Defaults to False.
        
        This method is the correct choice, if group members exchange data
        in real time. Roles are assigned randomly.

        Examples:
            ::

                import alfred3 as al
                from alfred3_interact import MatchMaker
                
                exp = al.Experiment()

                @exp.setup
                def setup(exp):
                    mm = MatchMaker("a", "b", exp=exp)
                    exp.plugins["group"] = mm.match_groupwise()
                
                @exp.member
                class Demo(al.Page):

                    def on_first_show(self):
                        role = self.exp.plugins.group.me.role
                        self += al.Text(f"I was assigned to role '{role}'.")

        """
        if not saving_method(self.exp) == "mongo":
            raise MatchingError("Must use a database for groupwise matching.")

        self.member = GroupMember(self)
        self.member._save()

        start = time.time()
        expired = (time.time() - start) > match_timeout

        i = 0
        while not self.group:
            self.member._ping()

            self.group = self._do_match_groupwise(ping_timeout=ping_timeout)

            if not self.group:
                expired = (time.time() - start) > match_timeout
                if expired:
                    break

                if (i == 0) or (i % 10 == 0):
                    msg = f"Incomplete group in groupwise matching. Waiting. Member: {self.member}"
                    self.log.debug(msg)

                i += 1
                time.sleep(1)

        if expired:
            self.log.error("Groupwise matchmaking timed out.")
            if raise_exception:
                raise MatchingTimeout
            else:
                return self._matching_timeout(self.group, timeout_page)
        else:
            self.log.info(f"{self.group} filled in groupwise match.")
            self._save_infos()
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
            self.log.info("Waiting successful. Proceeding with group assignment.")
            return group

        elif timeout:
            msg1 = f"{group} was in waiting position for too long. "
            msg2 = f"Starting a new group for session {self.exp.session_id}."
            self.log.warning(msg1 + msg2)

            group = Group(self, roles=self.roles)
            return group

    def _match_next_group(self):
        with next(self.group_manager.notfull()) as group:
            self.log.info(f"Starting stepwise match of session to existing group: {group}.")

            group += self.member
            group._assign_next_role(to_member=self.member)
            self.member._save()

            return group

    def _do_match_groupwise(self, ping_timeout):
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

        waiting_members = list(self.member_manager.waiting(ping_timeout=ping_timeout))
        waiting_members = [m for m in waiting_members if m != self.member]
        waiting_members.insert(0, self.member)

        if len(waiting_members) >= len(self.roles):
            self.log.debug("Filling group.")
            roles = {role: None for role in self.roles}
            group = Group(matchmaker=self, roles=roles)

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

    def _matching_timeout(self, group: Group, timeout_page):
        self.log.warning("Matchmaking timeout.")
        if group:
            group.data.active = False
            group._save()
            self.log.warning(f"{group} marked as expired.")
        self.io.release()
        self._data = self.io.load()

        if timeout_page:
            self.exp.abort(reason=self._TIMEOUT_MSG, page=timeout_page)
        else:
            self.exp.abort(
                reason=self._TIMEOUT_MSG,
                title="Timeout",
                msg="Sorry, the matchmaking process timed out.",
                icon="user-clock",
            )

        return None
    
    def _save_infos(self):
        prefix = "interact"
        while prefix in self.exp.adata:
            prefix += "_"
        self.exp.adata[prefix] = {}
        self.exp.adata[prefix]["groupid"] = self.group.group_id
        self.exp.adata[prefix]["role"] = self.member.role

    def _deactivate(self, exp):
        # gets called when the experiment aborts!
        if self.member:
            self.member.data.active = False
            self.member._save()

    def __str__(self):
        return f"{type(self).__name__}(id='{self.matchmaker_id}', roles={str(self.roles)})"

    def __repr__(self):
        return self.__str__()
