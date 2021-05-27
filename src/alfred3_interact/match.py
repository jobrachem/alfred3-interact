"""
Provides the main MatchMaker functionality.
"""

import time
import json
import copy
import string
import re
from dataclasses import asdict

from pymongo.collection import ReturnDocument
from alfred3.alfredlog import QueuedLoggingInterface
from alfred3.experiment import ExperimentSession
from alfred3.exceptions import SessionTimeout

from .group import Group
from .group import GroupManager
from .member import GroupMember
from .member import MemberManager
from .data import MatchMakerData
from ._util import saving_method
from ._util import MatchingError
from ._util import BusyGroup
from ._util import NoMatch

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
            active=self.mm._active,
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
                active=self.mm._active,
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
    

    def __enter__(self):
        return self.load_markbusy()

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.mm.member.data.active = False
            self.mm.member._save()
            self.exp.abort(reason="matchmaker_error")
            self.exp.log.error(f"There was an error in a locked MatchMaker operation. \
                I deactivated the responsible member {self.mm.member} and released the lock.")
        self.release()
        self.mm._data = self.load()



class MatchMaker:
    """
    Organizes the creation and composition of groups for interactive
    experiments.

    Args:
        *roles: A variable number of strings, indicating which roles
            will be appointed to members of the group. The number of
            roles determines the number of group members. All roles in a
            group must be unique. Roles cannot start with numbers or 
            contain spaces.
        exp (alfred3.experiment.ExperimentSession): The alfred3 experiment
            in which this matchmaker is used.
        admin_pw (str): Password for the MatchMaker admin view. If no
            admin password is supplied, the admin view is deactivated.
        id (str): Used in combination with the experiment ID as unique
            identifier for the MatchMaker.  Defaults to 'matchmaker',
            which is usually fine, unless you are using multiple
            matchmakers in one experiment.
        respect_version (bool): If True, the matchmaker will only match
            sessions that run on the same experiment version into the
            same group. This setting makes sure that there's no strange
            behavior if you make changes to an ongoing experiment.
            Defaults to True.
        active (bool): If True, the matchmaker will start in active mode.
            Defaults to *True*.
        inactive_page (Page): Page to be displayed to new participants
            if the MatchMaker is inactive. If None, a default page is
            used.
        admin_param (str): Name of the URL parameter used to start the
            admin mode. Defaults to the matchmaker id.


    Notes:
        See :meth:`.match_stepwise` and :meth:`.match_groupwise` for
        more information and examples. Also, there is an alternative
        constructor :meth:`.from_size`.

        .. note:: Note that the automatic MatchMaker admin mode is only
            available if the matchmaker is initialized in the experiment
            setup hook!

    See Also:
            - See :class:`.MatchingPage` for a special page class that
              offers a nice waiting screen and automatic forwarding upon
              achieving a match.
            
            - See :class:`.WaitingPage` for a special page class that
              offers a nice waiting screen for synchronization in an 
              ongoing experiment. This is useful to pause at some points
              in the experiment and wait for all group members to arrive
              at a specified point in the experiment.

    Examples:
        The example below illustrates the creation of an *asynchronous*
        group via :meth:`.match_stepwise`. For a synchronous group,
        refer to :meth:`.match_groupwise`::

            import alfred3 as al
            import alfred3_interact as ali

            exp = al.Experiment()

            @exp.setup
            def setup(exp):
                mm = ali.MatchMaker("role1", "role2", exp=exp)
                exp.plugins.group = mm.match_stepwise()
            
            
            @exp.member
            class Success(al.Page):
                title = "Match successful"

                def on_exp_access(self):
                    group = self.exp.plugins.group
                    
                    txt = f"You have successfully matched to role: {group.me.role}"
                    self += al.Text(txt, align="center")



    """

    _TIMEOUT_MSG = "MatchMaking timeout"
    _DATA_TYPE = "match_maker"

    def __init__(
        self,
        *roles,
        exp: ExperimentSession,
        id: str = "matchmaker",
        respect_version: bool = True,
        active: bool = True,
        inactive_page=None,
        admin_pw: str = None,
        admin_param: str = None,
    ):
        self.exp = exp
        
        if exp.start_time:
            raise MatchingError("MatchMaker must be initialized during experiment setup.")
        
        self.exp_version = self.exp.version if respect_version else ""
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)
        self._active = active
        self.inactive_page = inactive_page
        self.admin_param = admin_param if admin_param is not None else id
        self.admin_pw = admin_pw
        self.admin_mode = False

        self.member_timeout = None

        #: Number of seconds after which a single
        #: group-operation will be considered to have failed. In this
        #: case, the group in question will be marked as inactive and
        #: not be included in further matchmaking. Defaults to 300 seconds
        #: (5 minutes).
        self.group_timeout = 10

        if len(roles) != len(set(roles)):
            raise ValueError("All roles in a group must be unique.")

        self.roles = self._validate_roles(roles)
        self.matchmaker_id = id
        self.io = MatchMakerIO(self)

        self._data = self.io.load()

        self.member_manager = MemberManager(self)
        self.group_manager = GroupManager(self)
        self.group = None
        self.member = None

        self.exp.abort_functions.append(self._deactivate_session)
        
        if self.admin_pw:
            self.admin_mode = self._enable_admin_mode(self.exp)
        
        
            

    @classmethod
    def from_size(cls, n: int, **kwargs):
        """
        Creates a matchmaker instance from the number of group members.

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
    def active(self) -> bool:
        """
        Returns *True*, if the MatchMaker is active.
        """
        d = self.io.load()
        self._active = d.active
        return self._active

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

    def match_stepwise(self, member_timeout: int = None, ongoing_sessions_ok: bool = False) -> Group:
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
            ongoing_sessions_ok (bool): If False, new members will only
                be added to a group if all previous members of that group
                have finished their experiment sessions. This can prevent
                session losses in case 


        Roles are assigned to members in the order in which they
        are matched (first come, first serve).

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
                    exp.plugins.group = mm.match_stepwise()

                @exp.member
                class Demo(al.Page):

                    def on_exp_access(self):
                        role = self.exp.plugins.group.me.role
                        self += al.Text(f"I was assigned to role '{role}'.")

        """
        if not self._check_activation():
            return

        self.member_timeout = member_timeout
        self.member = GroupMember(self)
        self.member._save()

        # match to existing group
        if any(self.group_manager.notfull(ongoing_sessions_ok=ongoing_sessions_ok)):
            try:
                self.group = self._match_next_group(ongoing_sessions_ok=ongoing_sessions_ok)
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

    def match_groupwise(
        self,
        ping_timeout: int = 15
    ) -> Group:
        """
        Waits until there are enough participants for a full group, then
        matches them together.

        Args:
            ping_timeout (int): Number of seconds after which an experiment
                session will be excluded from groupwise matching. This makes
                sure that only currently active sessions will be allocated
                to a group. Defaults to 15 (seconds).

        This method is the correct choice if group members exchange data
        in real time. Roles are assigned randomly.

        Notes:
            .. important:: Note that you must use a :class:`.MatchingPage` for 
                groupwise matching. Outside of a MatchingPage, groupwise
                matching will not work.

        See Also:
            - See :class:`.MatchingPage` for a special page class that
              offers a nice waiting screen and automatic forwarding upon
              achieving a match.
            
            - See :class:`.WaitingPage` for a special page class that
              offers a nice waiting screen for synchronization in an 
              ongoing experiment. This is useful to pause at some points
              in the experiment and wait for all group members to arrive
              at a specified point in the experiment.

        Examples:
            ::

                import alfred3 as al
                import alfred3_interact as ali

                exp = al.Experiment()

                @exp.setup
                def setup(exp):
                    exp.plugins.mm = ali.MatchMaker("a", "b", exp=exp)
                
                @exp.member
                class Match(ali.MatchingPage):

                    def wait_for(self):
                        self.exp.plugins.group = self.plugins.mm.match_groupwise()
                        return True

                @exp.member
                class Demo(al.Page):

                    def on_first_show(self):
                        role = self.exp.plugins.group.me.role
                        self += al.Text(f"I was assigned to role '{role}'.")

        """
        if not self._check_activation():
            return

        if not saving_method(self.exp) == "mongo":
            raise MatchingError("Must use a database for groupwise matching.")

        if self.member and self.group:
            self.log.info(f"match_groupwise was called, but {self.member} was already matched to \
                {self.group}. Returning group.")
            return self.group

        self._set_ping_timeout(ping_timeout)

        self.member = self._init_member()
        
        self.group = self._do_match_groupwise(ping_timeout=ping_timeout)

        if not self.group:
            raise NoMatch

        
        self.log.info(f"{self.group} filled in groupwise match.")
        self._save_infos()
        return self.group
    
    def _init_member(self):
        if self.member:
            return self.member
        
        member = GroupMember(self)
        member._save()
        if member.expired:
            raise SessionTimeout
        else:
            return member

    def toggle_activation(self) -> str:
        """
        Toggles MatchMaker activation.

        Returns:
            str: Returns the new status (active/inactive).
        """
        data = self.io.load()
        data.active = not data.active
        self.io.save(data=data)
        self._data = data

        return "active" if data.active else "inactive"

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

            roles = {role: None for role in self.roles}
            group = Group(self, roles=roles)
            return group

    def _match_next_group(self, ongoing_sessions_ok: bool):
        with next(self.group_manager.notfull(ongoing_sessions_ok=ongoing_sessions_ok)) as group:
            self.log.info(f"Starting stepwise match of session to existing group: {group}.")
            group += self.member
            group._assign_next_role(to_member=self.member)
            self.member._save()

            return group

    def _do_match_groupwise(self, ping_timeout):
        member = self.member._load_if_notbusy()
        if member is None:
            self.log.debug("Returning. Member not found, MM is busy.")
            return None

        elif member.matched:
            self.log.debug("Returning. Found group.")
            return self.group_manager.find(member.data.group_id)

        with self.io as data:
            if data is None:
                self.log.debug("Returning. Data marked, MM is busy.")
                return None

            waiting_members = self._get_waiting_members(ping_timeout)

            if len(waiting_members) >= len(self.roles):
                group = self._fill_group(data, waiting_members)
                return group
            
            return None
    
    def _get_waiting_members(self, ping_timeout):
        waiting_members = list(self.member_manager.waiting(ping_timeout=ping_timeout))
        waiting_members = [m for m in waiting_members if m != self.member]
        waiting_members.insert(0, self.member)
        return waiting_members
    
    def _fill_group(self, data, waiting_members):
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

        self.log.debug("Returning filled group.")
        return group

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

    def _check_activation(self):
        if self.admin_mode:
            return True
        
        if self.active:
            return True

        self.log.info("MatchMaking session aborted (MatchMaker inactive).")
        self.exp._allow_append = True
        if self.inactive_page:
            self.exp.abort(reason="matchmaker_inactive", page=self.inactive_page)
        else:
            self.exp.abort(
                reason="matchmaker_inactive",
                title="MatchMaking inactive",
                msg="Sorry, the matchmaking process is currently inactive. Please try again later.",
                icon="user-times"
            )
        self.exp._allow_append = False

        return False

    def _save_infos(self):
        prefix = "interact"
        while prefix in self.exp.adata:
            prefix += "_"
        self.exp.adata[prefix] = {}
        self.exp.adata[prefix]["groupid"] = self.group.group_id
        self.exp.adata[prefix]["role"] = self.member.role

    def _deactivate_session(self, exp):
        # gets called when the experiment aborts!
        if self.member:
            self.member.data.active = False
            self.member._save()

    def _enable_admin_mode(self, exp) -> bool:
        """
        Returns *True* if admin mode is called, *False* otherwise.
        """
        from alfred3_interact.page import PasswordPage, AdminPage

        if exp.urlargs.get(self.admin_param, False) == "admin" and not exp.session_status == "admin":
            exp.session_timeout = None
            exp.config.read_dict({"data": {"save_data": False}})
            exp.config.read_dict({"layout": {"show_progress": False}})
            exp.session_status = "admin"

            exp._allow_append = True
            exp += PasswordPage(
                password=self.admin_pw,
                match_maker_id=self.matchmaker_id,
                title="MatchMaker Admin",
                name="_pw_admin_page",
            )
            exp += AdminPage(match_maker=self, title="MatchMaker Admin", name="_admin_page")
            exp._allow_append = False

            return True
        
        else:
            return False

    def _set_ping_timeout(self, ping_timeout):
        if not self._data.ping_timeout == ping_timeout:
            q = {"type": "match_maker", "exp_id": self.exp.exp_id}
            q["exp_version"] = self.exp_version
            q["matchmaker_id"] = self.matchmaker_id
            self.exp.db_misc.find_one_and_update(q, update={"$set": {"ping_timeout": ping_timeout}})
    
    def _validate_roles(self, roles):
        p = re.compile(r"^\d|\s")
        for role in roles:
            if p.search(role):
                raise ValueError(f"Error in role '{role}': Roles must not start with numbers \
                    and must not contain spaces.")
        
        return roles


    def __str__(self):
        return f"{type(self).__name__}(id='{self.matchmaker_id}', roles={str(self.roles)})"

    def __repr__(self):
        return self.__str__()
