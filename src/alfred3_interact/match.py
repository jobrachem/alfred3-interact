import time
import json
import copy
import typing as t
import random
from traceback import format_exception
from dataclasses import asdict, dataclass, field

from pymongo.collection import ReturnDocument
from packaging import version
from alfred3.alfredlog import QueuedLoggingInterface
from alfred3.exceptions import AllSlotsFull
from alfred3 import __version__ as alfred_version

from alfred3_interact.group import GroupManager

from .quota import MetaQuota
from .member import GroupMember
from .member import MemberManager
from .group import Group
from ._util import saving_method
from ._util import MatchingError
from ._util import NoMatch

ALFRED_VERSION = version.parse(alfred_version)


@dataclass
class MatchMakerData:
    exp_id: str
    exp_version: str
    matchmaker_id: str
    type: str
    members: dict = field(default_factory=dict)
    busy: bool = False
    active: bool = False
    ping_timeout: int = None


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
            type=self.mm._DATA_TYPE,
            ping_timeout=self.mm.ping_timeout
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
                type=self.mm._DATA_TYPE,
            )

            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(asdict(data), f, sort_keys=True, indent=4)
            return data

    def _load_markbusy_local(self):
        data = self._load_local()
        if not data.busy:
            data.busy = True
            self._save_local(data)
            return data
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
            self.mm.member.io.save()
            self.mm.exp.abort(reason="matchmaker_error")

            tb = "".join(format_exception(exc_type, exc_value, traceback))
            self.mm.exp.log.error(
                (
                    f"There was an error in a locked MatchMaker operation."
                    f"I deactivated the responsible member {self.mm.member} and released the lock.\n"
                    f"{tb}"
                )
            )
        self.release()
        self.mm._data = self.load()


class MatchMaker:
    """
    Creates groups of multiple experiment sessions.

    Args:
        *groupspecs: Variable number of group specifications. Each spec
            defines one blueprint for a group. Currently, 
            :class:`.ParallelSpec`, :class:`.SequentialSpec`, and 
            :class:`.IndividualSpec` are supported.
        exp (alfred3.ExperimentSession): Associated experiment session.
        name (str): An identifier for the matchmaker. Must be unique
            within one experiment. Can (and must) be set to a custom value, if
            you wish to use multiple matchmakers in a single experiment. 
            Defaults to 'matchmaker'. 
        inactive_page (alfred3.Page): Page to be displayed to participants
            if the matchmaker is inactive. If *None* (default) a default
            page will be used.
        full_page (alfred3.Page): Page to be displayed to participants
            if all specs have reached their quota of groups. If *None* 
            (default) a default page will be used.
        raise_exception_if_full (bool): As an alternative to using a
            *full_page*, you can let the MatchMaker raise the 
            :class:`.AllSlotsFull` exception if all specs have reached 
            their quota of groups. Defaults to *False*.
        respect_version (bool): If True, the MatchMaker will only match
            sessions that run on the same experiment version into the
            same group. This setting makes sure that there's no strange
            behavior if you make changes to an ongoing experiment.
            Defaults to True.
        ping_timeout (float, int): When matching parallel groups 
            (i.e. groups based on :class:`.ParallelSpec`), only active
            sessions are included in the matchmaking process. Sessions
            therefore send a signal of activity to the server on a 
            regular schedule. The argument *ping_timeout* determines the 
            number of seconds of inactivity before a session is 
            considered to be inactive. Defaults to 15 seconds.
    
    The workhorse methods of the MatchMaker are :meth:`.match_random`,
    :meth:`.match_chain`, and :meth:`.match_to`. Call one of these 
    methods in the :meth:`.WaitingPage.wait_for` hook to start the
    matchmaking process.

    To initialize the MatchMaker, you must first create a group 
    specification, which is a sort of blueprint for building a group. 
    The spec defines the size of the group, the roles that can be 
    assigned to participants, and the number of groups that should be
    created based on that spec. If you supply multiple specs, you
    can randomize group creation with :meth:`.match_random` or create
    an order of priority with :meth:`.match_chain`.
    
    See Also:

        See :class:`.SequentialSpec` and :class:`.ParallelSpec` for more 
        information on specs.

    Examples:
        A minimal example with a single spec::

            import alfred3 as al
            import alfred3_interact as ali

            exp = al.Experiment()

            @exp.setup
            def setup(exp):
                spec = ali.SequentialSpec("a", "b", nslots=10, name="spec1")
                exp.plugins.mm = ali.MatchMaker(spec, exp=exp)
            
            @exp.member
            class Match(ali.WaitingPage):

                def wait_for(self):
                    group = self.exp.plugins.mm.match_to("spec1")
                    self.exp.plugins.group = group
                    return True
            
            @exp.member
            class Success(al.Page):

                def on_first_show(self):
                    group = self.exp.plugins.group
                    role = group.me.role
                    
                    self += al.Text(f"Successfully matched to role: {role}")


    """
    _DATA_TYPE = "match_maker_data"

    def __init__(
        self,
        *groupspecs,
        exp,
        name: str = "matchmaker",
        inactive_page=None,
        full_page=None,
        raise_exception_if_full: bool = False,
        respect_version: bool = True,
        ping_timeout: t.Union[float, int] = 15
    ):
        # init values
        self.exp = exp
        self.groupspecs = list(self._validate_specs(groupspecs))
        self.respect_version = respect_version
        self.exp_version = exp.version if respect_version else ""
        self.matchmaker_id = name
        self.name = name
        self.inactive_page = inactive_page
        self.full_page = full_page
        self.raise_exception_if_full = raise_exception_if_full

        # auto values
        self.spec_dict = {spec.name: spec for spec in groupspecs}
        self.log = QueuedLoggingInterface(base_logger="alfred3")
        self.log.add_queue_logger(self, __name__)
        self._active = True
        self.io = MatchMakerIO(self)
        self.member_manager = MemberManager(self)
        self.group = None
        self.member = None
        self._match_start_save = None
        self.ping_timeout = ping_timeout
        self._data = self.io.load()
        quotas = [spec.quota for spec in self.groupspecs]
        self.quota = MetaQuota(*quotas)

    @property
    def active(self) -> bool:
        """
        Returns *True* if the MatchMaker is active.
        """
        d = self.io.load()
        self._active = d.active
        return self._active
    

    @property
    def _match_start(self) -> float:
        """
        float: Start time of the matchmaking process. Should only be
        called from inside a matching function.
        """
        if self._match_start_save is None:
            self._match_start_save = time.time()

        return self._match_start_save

    @property
    def waiting_members(self) -> t.List[GroupMember]:
        """
        list: List of experiment sessions currently active and waiting
        to be matched. The sessions are represented by their 
        :class:`.GroupMember` objects.
        """
        members = list(self.member_manager.waiting(self.ping_timeout))
        members = [m for m in members if not m.data.session_id == self.exp.session_id]
        if not self.member.matched:
            members = [self.member] + members
        return members

    def match(self) -> Group:
        """
        Shorthand method for conducting a match if there is only a single
        spec.

        Raises:
            ValueError: If there is more than one spec.
            NoMatch: If a single matching effort was unsuccesful. This
                exception gets handled by :class:`.WaitingPage` and is
                part of a normal matching process.
        
        Returns:
            Group: The group object.
        
        Examples:
            
            Matching based on a single spec::

                import alfred3 as al
                import alfred3_interact as ali

                exp = al.Experiment()

                @exp.setup
                def setup(exp):
                    spec = ali.SequentialSpec("a", "b", nslots=10, name="spec1")
                    exp.plugins.mm = ali.MatchMaker(spec, exp=exp)
                
                @exp.member
                class Match(ali.WaitingPage):

                    def wait_for(self):
                        group = self.exp.plugins.mm.match()
                        self.exp.plugins.group = group
                        return True
                
                @exp.member
                class Success(al.Page):

                    def on_first_show(self):
                        group = self.exp.plugins.group
                        role = group.me.role
                        
                        self += al.Text(f"Successfully matched to role: {role}")

        """
        if len(self.groupspecs) > 1:
            msg = (
                "Cannot use the method 'MatchMaker.match()', if there is more than one spec. "
                f"You have {len(self.groupspecs)} specs."
            )
            raise ValueError(msg)
        
        name = self.groupspecs[0].name
        return self.match_to(name)


    def match_random(self, wait: int = None, nmin: int = None):
        """
        Conducts a match to a random feasible group specification.

        Args:
            wait (int): Number of seconds to wait before actually starting
                a matching effort. Defaults to None, which means
                that there is no waiting time.
            nmin (int): Minimum number of waiting participants that must 
                be active before actually starting a matching effort. 
                If there are *nmin* participants waiting, matching will
                start even if the waiting time specified in *wait* is
                not over yet. Thus, *nmin* can be used to cut the waiting
                time short. Defaults to None, which means that waiting
                time alone determines when matching will start.
                **Note**: The parameter *nmin* will only take effect, if
                *wait* is not *None*.
        
        This is the right method, if you wish to randomize participants
        into groups of different sizes. 

        .. important::
            :meth:`.match_random` matches randomly among all *feasible*
            specs at the time of matching. A spec is feasible if there
            are enough participants waiting for a group based on that
            spec. 

            For instance, let's say you have an :class:`.IndividualSpec` 
            and a :class:`.ParallelSpec` with two roles, forming a dyad. 
            Four participants
            are scheduled for a session. Participant 1 logs in one minute
            early, Participant 2 is on time, Participant 3 logs in 30 
            seconds late, and Participant 4 logs in 2 minutes late. All of
            them will be matched immediately to the :class:`.IndividualSpec`,
            because this spec is always feasible. The :class:`.ParallelSpec`
            on the other hand requires at least two participants to be
            waiting simultaneously.
            
            This behavior can be adjusted through the arguments *wait*
            and *nmin*. In this example case, you may, for instance,
            specify ``nmin=3`` and ``wait=2*60`` to ensure that there
            is some time for participants to register. Participants 1, 
            2, and 3 will be matched to a random spec once Participant 3
            logs in, because *nmin* has been reached. Participant 4 will
            wait for two minutes before being assigned to the individual
            spec. The possible outcomes are: (1) Four individual specs
            (if the randomization does not lead to the formation of a
            dyad), (2) two individual specs and one parallel spec (if a
            dyad is formed in the randomization).

            The method :meth:`.match_chain` may be an even more suitable
            option.
        
        .. note::
            Randomization into groups of different sizes can be a little
            tricky because large groups may have an unequal (lower) 
            chance of being filled at the same rate as smaller groups
            due to participant dropout. We provide the arguments *wait* 
            and *nmin* to improve the feasibility of such designs. However,
            the method :meth:`.match_chain` may be an even more suitable
            option.
        
        Raises:
            NoMatch: If a single matching effort was unsuccesful. This
                exception gets handled by :class:`.WaitingPage` and is
                part of a normal matching process.
        
        Returns:
            Group: The group object.
        
        See Also:
            :meth:`.match_chain`
        
        Examples:
            ::

                import alfred3 as al
                import alfred3_interact as ali

                exp = al.Experiment()

                @exp.setup
                def setup(exp):
                    spec1 = ali.SequentialSpec("a", "b", nslots=10, name="spec1")
                    spec2 = ali.SequentialSpec("a", "b", nslots=10, name="spec2")
                    exp.plugins.mm = ali.MatchMaker(spec1, spec2, exp=exp)
                
                @exp.member
                class Match(ali.WaitingPage):

                    def wait_for(self):
                        group = self.exp.plugins.mm.match_random()
                        self.exp.plugins.group = group
                        self.exp.condition = group.data.spec_name
                        return True
                
                @exp.member
                class Success(al.Page):

                    def on_first_show(self):
                        group = self.exp.plugins.group
                        role = group.me.role
                        cond = self.exp.condition
                        
                        self += al.Text(f"Successfully matched to role '{role}' in condition '{cond}'")

        """
        self.member = self._init_member()

        if self.member.matched:
            return self._get_group(self.member)

        self.member.io.ping()

        start = self._match_start

        if wait is None:
            waited_enough = True
        else:
            waited_enough = time.time() - start >= wait

        if nmin is None:
            enough_members = False
        else:
            enough_members = len(self.waiting_members) >= nmin

        if enough_members or waited_enough:
            random.shuffle(self.groupspecs)
            return self._match_quota(self.groupspecs)

        raise NoMatch


    def match_chain(self, include_previous: bool = True, **spectimes) -> Group:
        """
        Offers prioritized matchmaking based on multiple specs.

        Imagine that you have two :class:`.ParallelSpec` group specifications. 
        Spec 1 requires five participants to be active, while Spec 2 only 
        requires two.
        You may wish to first try matching based on Spec 1 for some time
        and move on to Spec 2 only when it becomes incresingly clear that
        there are not enough participants present to fill the bigger spec.
        This is what this method is for. You specify a schedule of time
        boxes that are reserved for specific specs.
        
        Args:
            include_previous (bool): If *True*, earlier specs will still be 
                available for matching in later time boxes. If there are
                enough participants waiting for two specs, the MatchMaker
                selects a random spec for matching. Defaults to *True*.
            **spectimes: Specifications of spec timeboxes. Specified by
                ``specname=time``, where *time* is the length of the spec's 
                time box in seconds and
                *specname* is the spec's name. 
                For the last spec, the value for ``time`` is irrelevant, 
                as it will be included until the MatchMaking process 
                times out. It should be set to *None*. You can select 
                any number of specs, but only specs that are available to
                the MatchMaker.
        
        Raises:
            NoMatch: If a single matching effort was unsuccesful. This
                exception gets handled by :class:`.WaitingPage` and is
                part of a normal matching process.
        
        Returns:
            Group: The group object.
        
        Examples:

            In this example, the MatchMaker will try to form a group
            based on ``spec2`` for the first three minutes of the 
            matchmaking process. Once the first active participant 
            has waited for more than three minutes without a successfull
            match, ``spec1`` will be included::

                import alfred3 as al
                import alfred3_interact as ali

                exp = al.Experiment()

                @exp.setup
                def setup(exp):
                    spec1 = ali.ParallelSpec("a", "b", nslots=10, name="spec1")
                    spec2 = ali.ParallelSpec("a", "b", "c", nslots=10, name="spec2")
                    exp.plugins.mm = ali.MatchMaker(spec1, spec2, exp=exp)
                
                @exp.member
                class Match(ali.WaitingPage):

                    def wait_for(self):
                        group = self.exp.plugins.mm.match_chain(spec2=3*60, spec2=None)
                        self.exp.plugins.group = group
                        self.exp.condition = group.data.spec_name
                        return True
                
                @exp.member
                class Success(al.Page):

                    def on_first_show(self):
                        group = self.exp.plugins.group
                        role = group.me.role
                        cond = self.exp.condition
                        
                        self += al.Text(f"Successfully matched to role '{role}' in condition '{cond}'")


        """
        # member setip
        self.member = self._init_member()
        if self.member.matched:
            return self._get_group(self.member)
        self.member.io.ping()

        # data setup
        start = self._match_start
        passed_time = time.time() - start

        # remove full specs
        feasible_specs = [spec.name for spec in self.groupspecs if not spec.full(self)]
        spectimes = {spec: time for spec, time in spectimes.items() if spec in feasible_specs}

        # spec selection setup
        specs = []
        candidate_specs = list(spectimes)
        delays = list(spectimes.values())
        delays = [0, *delays[:-1]]
        previous_delay = 0

        # spec selection
        for i, spec in enumerate(candidate_specs):
            delay = delays[i] + previous_delay
            ready = passed_time >= delay
            
            try:
                next_delay = delays[i + 1] + delay
                next_spec_ready = passed_time >= next_delay
                over = not include_previous and next_spec_ready
            except IndexError: # for last spec
                over = False

            if ready and not over:
                specs.append(self.spec_dict[spec])

            previous_delay = delay

        if not specs:
            raise NoMatch

        random.shuffle(specs)
        return self._match_quota(specs)

        # return self._match_quota(specs)

    def match_to(self, name: str) -> Group:
        """
        Matches participants to a group based on a specific spec.

        Args:
            name (str): Name of the spec that should be used.

        Raises:
            NoMatch: If a single matching effort was unsuccesful. This
                exception gets handled by :class:`.WaitingPage` and is
                part of a normal matching process.
        
        Returns:
            Group: If matching was successful.
        """
        self.member = self._init_member()

        if self.member.matched:
            group = self._get_group(self.member)
            if group.data.spec_name != name:
                msg = (
                    "Member was already matched to a group of spec"
                    f"'{group.data.spec_name}' != '{name}'"
                )
                raise MatchingError(msg)
            return group
            
        self.member.io.ping()

        return self._match_to(name=name)

    def _get_group(self, member):
        manager = GroupManager(self)
        group = manager.find_one(member.group_id)
        spec = group.data.spec_name
        return self._match_to(spec)

    def _match_to(self, name: str):
        spec = self.spec_dict[name]

        if not self.check_activation() or self.exp.admin_mode:
            return

        self.group = spec._match(self)
        if spec.count:
            try:
                spec.quota.count(self.group, raise_exception=True)
            except AllSlotsFull:
                self.group.deactivate()
                self._full()
        
        if not self.group:
            return

        self._update_additional_data()
        return self.group

    def toggle_activation(self) -> str:
        """
        Toggles MatchMaker activation.

        An inactive MatchMaker will not conduct any matching. 
        Sessions that call a matching method will be aborted.

        Returns:
            str: Returns the new status (active/inactive).
        """
        data = self.io.load()
        data.active = not data.active
        self.io.save(data=data)
        self._data = data

        return "active" if data.active else "inactive"
    
    def check_quota(self) -> bool:
        """
        Verifies that the MatchMaker has available slots for new 
        groups. Aborts the experiment if there are no available slots
        left.

        Raises:
            AllSlotsFull: If the MatchMaker was initialized with 
                ``raise_exception_if_full = True`` (default is *False*)
                and the MatchMaker has no available slots.
        """
        if self.exp.admin_mode:
            return True
        
        if self.quota.full:
            self._full()
            return False
        else:
            return True

    def check_activation(self) -> bool:
        """
        Verifies that the MatchMaker is active and aborts the experiment
        if necessary.

        If the MatchMaker not active, the current experiment session is
        aborted, and the *abort_page* specified on initialization of
        the MatchMaker will be shown to participants.

        The matching methods will check for activation themselves,
        when called. But this may happen at a point in the experiment where
        participants have made considerable progress. So it may be
        useful to manually check for activation at an earlier stage.

        As a general rule of thumb, it may be sensible to check activation
        on first hiding of the landing page of an experiment. This way,
        participants still get a nice welcome screen, but do not invest
        too much time before the experiment is cancelled.

        """
        if self.exp.admin_mode:
            return True

        if self.active:
            return True

        self.log.info("MatchMaking session aborted (MatchMaker inactive).")
        self._abort_exp("matchmaker_inactive", self.inactive_page)

        return False

    def _match_quota(self, specs):
        no_match = False

        for spec in specs:
            if not spec.full(self):
                try:
                    return self._match_to(spec.name)
                except NoMatch:
                    no_match = True

        if no_match: # only reached if *no* spec lead to successful match
            raise NoMatch

        self._full()

    def _full(self):
        if self.raise_exception_if_full:
            raise AllSlotsFull
        else:
            self._abort_exp("matchmaker_full", self.full_page)

    def _abort_exp(self, reason: str, page):
        full_page_title = "Experiment closed"
        full_page_text = "Sorry, the experiment currently does not accept participants."
        self.exp.abort(
            reason=reason,
            title=full_page_title,
            msg=full_page_text,
            icon="user-check",
            page=page,
        )

    def _validate_specs(self, specs):
        names = set([spec.name for spec in specs])
        if len(names) < len(specs):
            raise ValueError("Group specs must have unique names.")
        
        for spec in specs:
            spec._init_quota(self.exp)

        return specs

    def _init_member(self) -> GroupMember:
        if self.member:
            self.member.io.load()
            return self.member

        member = GroupMember(self)
        member.io.save()
        return member


    def _update_additional_data(self):
        prefix = "interact"
        while prefix in self.exp.adata:
            prefix = "_" + prefix
        self.exp.adata[prefix] = {}
        self.exp.adata[prefix]["groupid"] = self.group.data.group_id
        self.exp.adata[prefix]["role"] = self.member.data.role
