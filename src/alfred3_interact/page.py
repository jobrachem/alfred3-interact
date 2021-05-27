"""
Specialized pages for interactive experiments.
"""

import time
from abc import abstractmethod
from functools import wraps

from jinja2 import Template

import alfred3 as al
from alfred3.element.core import Element
from alfred3.element.misc import Callback, RepeatedCallback
from alfred3._helper import inherit_kwargs
from alfred3.exceptions import SessionTimeout

from .match import MatchMaker
from ._util import MatchingTimeout
from ._util import NoMatch
from .element import ViewMembers, ToggleMatchMakerActivation


class PasswordPage(al.WidePage):
    def __init__(self, password: str, match_maker_id: str, **kwargs):
        super().__init__(**kwargs)
        self.password = password
        self.match_maker_id = match_maker_id

    def on_exp_access(self):
        self += al.HideNavigation()
        self += al.Text(f"Matchmaker ID: {self.match_maker_id}", align="center")
        self += al.VerticalSpace("50px")
        self += al.PasswordEntry(
            toplab="Password", password=self.password, width="narrow", name="pw", align="center"
        )

        self += al.SubmittingButtons(
            "Submit", align="center", name="pw_submit", width="narrow", button_style="btn-primary"
        )

        # enables submit via enter-press for password field
        self += al.JavaScript(
            code="""$('#pw').on("keydown", function(event) {
        if (event.key == "Enter") {
            $("#alt-submit").attr("name", "move");
            $("#alt-submit").val("forward");
            $("#form").submit();
            }});"""
        )


class AdminPage(al.WidePage):
    def __init__(self, match_maker, **kwargs):
        super().__init__(**kwargs)
        self.match_maker = match_maker

    def on_exp_access(self):
        self += al.Text(f"Matchmaker ID: {self.match_maker.matchmaker_id}", align="center")
        self += ToggleMatchMakerActivation(match_maker=self.match_maker, align="center")
        self += al.VerticalSpace("30px")
        self += ViewMembers(match_maker=self.match_maker, name="view_mm")
        self += al.VerticalSpace("30px")
        self += al.Text(
            "Note: The MatchMaker Admin displays only sessions for which the matchmaking process has been started.",
            font_size="small",
            width="full",
        )

        self += al.HideNavigation()
        self += al.WebExitEnabler()
        self += al.Style(code=f"#view_mm {{font-size: 85%;}}")

        # datatables javascript package
        # self += al.Style(url="//cdn.datatables.net/1.10.24/css/jquery.dataTables.min.css")
        self += al.Style(
            url="https://cdn.datatables.net/1.10.24/css/dataTables.bootstrap4.min.css"
        )
        self += al.JavaScript(url="//cdn.datatables.net/1.10.24/js/jquery.dataTables.min.js")
        self += al.JavaScript(
            url="https://cdn.datatables.net/1.10.24/js/dataTables.bootstrap4.min.js"
        )


class DefaultWaitingTimeoutPage(al.Page):
    """
    Default page to be displayed upon waiting timeouts.
    """

    title = "Timeout"
    name = "default_waiting_timeout_page"

    def on_exp_access(self):
        self += al.VerticalSpace("50px")
        self += al.Html(al.icon("user-clock", size="80pt"), align="center")
        self += al.VerticalSpace("100px")
        self += al.Text("Sorry, waiting took too long.", align="center")


class DefaultWaitingExceptionPage(al.Page):
    """
    Default page to be displayed upon waiting exceptions.
    """
    title = "Experiment aborted"
    name = "default_waiting_exception_page"

    def on_exp_access(self):
        self += al.VerticalSpace("50px")
        self += al.Html(al.icon("user-clock", size="80pt"), align="center")
        self += al.VerticalSpace("100px")
        self += al.Text("Sorry, the experiment was aborted while waiting.", align="center")


@inherit_kwargs
class WaitingPage(al.NoNavigationPage):
    """
    A page that provides a waiting screen for synchronization in
    interactive experiments.

    This page is must be derived. You define the condition by defining
    the :meth:`.wait_for` method. The page has a default design, set in
    :meth:`.on_exp_access` - you can safely redefine this method to use
    your own design.

    Once the :meth:`.wait_for` method returns a *True*-like value (i.e.,
    a value for which ``bool(value) == True)`` holds, the
    WaitingPage will proceed to the next page automatically.

    .. important:: The :meth:`.wait_for` method *must* return a value,
        otherwise you will wait indefinitely.

    Args:
        wait_msg (str): Text to be displayed in the default layout.
            Defaults to None, in which case the text is
            "Waiting for other group members." Can be defined as a 
            class attribute.
        wait_timeout (int): Maximum waiting time in seconds. If *wait_for*
            does not return a *True*-like value within waiting time, the experiment
            session is aborted. Defaults to None, in which case the
            timeout is ``60 * 20``, i.e. 20 minutes.
            Can be defined as a class attribute.
        wait_sleep_time (int): Number of seconds in between two internal
            calls to :meth:`.wait_for`. Defaults to None, in which case
            a call will be made every two seconds.
            Can be defined as a class attribute.
        wait_timeout_page (alfred3.Page): A custom page to be displayed
            in case of a waiting timeout. Defaults to an instance of
            :class:`.DefaultWaitingTimeoutPage`.
            Can be defined as a class attribute.
        wait_exception_page (alfred3.Page): A custom page to be displayed
            in case of an exception during waiting. Defaults to an
            instance of :class:`.DefaultWaitingExceptionPage`.
            Can be defined as a class attribute.

        {kwargs}

    Examples:

        The example demonstrates how to use the waiting page in
        an ongoing experiment to wait until a group member has proceeded
        to a certain point in the experiment (more precisely, until a
        group member has filled a certain input element in this case)::


            import alfred3 as al
            import alfred3_interact as ali

            exp = al.Experiment()

            @exp.setup
            def setup(exp):
                mm = ali.MatchMaker("a", "b", exp=exp)
                exp.plugins.group = mm.match_stepwise()


            @exp.member
            class InputPage(al.Page):

                def on_exp_access(self):
                    self += al.TextEntry(leftlab="Enter text", name="el1", force_input=True)


            @exp.member
            class Sync1(ali.WaitingPage):

                def wait_for(self):
                    you = self.exp.plugins.group.you
                    return you.values.get("el1", False)

            exp += al.Page(title="Waiting successful", name="success")


    """

    #: str: Page title
    title = "Waiting"

    #: Text to be displayed in the default layout.
    #: Defaults to None, in which case the text is
    #: "Waiting for other group members."
    wait_msg: str = "Waiting for other group members."

    #: Maximum waiting time in seconds. If *wait_for*
    #: does not return a *True*-like value within waiting time, the experiment
    #: session is aborted. Defaults to None, in which case the
    #: timeout is ``60 * 20``, i.e. 20 minutes.
    wait_timeout: int = 60 * 20

    #: Number of seconds in between two internal
    #: calls to :meth:`.wait_for`. Defaults to None, in which case
    #: a call will be made every two seconds.
    wait_sleep_time: int = 2

    #: Abort page to be displayed on timeout
    wait_timeout_page = None

    #: Abort page to be displayed on other exceptions during waiting
    wait_exception_page = None

    #: If *True*, the page will save signals of activity in the database
    #: for this experiment session. Important for MatchMaking, but usually
    #: not for ordinary waiting. Defaults to *False*
    ping = False

    def __init__(
        self,
        *args,
        wait_msg: str = None,
        wait_timeout: int = None,
        wait_sleep_time: int = None,
        wait_timeout_page: al.Page = None,
        wait_exception_page: al.Page = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if wait_msg is not None:
            self.wait_msg = wait_msg

        if wait_timeout is not None:
            self.wait_timeout = wait_timeout

        if wait_sleep_time is not None:
            self.wait_sleep_time = wait_sleep_time

        if wait_timeout_page is not None:
            self.wait_timeout_page = wait_timeout_page
        else:
            self.wait_timeout_page = DefaultWaitingTimeoutPage()

        if wait_exception_page is not None:
            self.wait_exception_page = wait_exception_page
        else:
            self.wait_exception_page = DefaultWaitingExceptionPage()
        
        self += RepeatedCallback(
            func=self._wait_for, 
            interval=self.wait_sleep_time, 
            followup="custom", 
            custom_js="if (data) {move('forward')};"
        )

        #: Time of waiting start in seconds since epoch
        #: We are not using the first show time here, because we want
        #: to try to synchronize the waiting timeout with the displayed
        #: Counter as best as possible. If we used the first show time,
        #: that may be an earlier time point.
        self.waiting_start: float = None
        self.countup = al.CountUp(font_size=30, align="center")

    
    @property
    def expiration_time(self) -> float:
        """
        float: Point in time at which the waiting page expires in 
        seconds since epoch.
        """
        if not self.waiting_start:
            return None
        
        return self.waiting_start + self.wait_timeout
    

    @property
    def expired(self) -> bool:
        """
        bool: *True* if the page has exceeded its maximum waiting time.
        """
        if self.expiration_time:
            now = time.time()
            return now > self.expiration_time
        else:
            return False
    
    
    @abstractmethod
    def wait_for(self):
        """
        Once this method returns *True*, the page automatically
        forwards participants to the next page.

        It will be repeatedly called internally with the time between
        two calls defined by :attr:`.wait_sleep_time`.
        """
        pass

    def _wait_for(self):
        """
        This method gets called repeatedly via ajax callback from the
        waiting page client-side. If it returns *True*, the experiment will move
        on to the next page. Otherwise, the callback will try again
        until the timeout is reached.
        """
        
        if self.ping:
            self._call_ping()
        
        if not self.waiting_start:
            self.waiting_start = time.time()
            self.countup.start_time = self.waiting_start
        
        if self.expired:
            self.log.exception("Timeout on waiting page. Aborting experiment.")
            self.exp.abort(reason=MatchMaker._TIMEOUT_MSG, page=self.wait_timeout_page)
            return True
        
        try:
            wait_status = self.wait_for()
        
        except NoMatch:
            return False # return False so that the repeated callback will try again
        
        except Exception:
            self.log.exception("Exception in waiting function. Aborting experiment.")
            self.exp.abort(reason="waiting error", page=self.wait_exception_page)
            return True
        
        return wait_status

    def on_exp_access(self):
        spinning_icon = al.icon("spinner", spin=True, size="90pt")

        self += al.VerticalSpace("100px")
        self += al.Text(spinning_icon, align="center")
        self += al.VerticalSpace("30px")
        self += self.countup
        self += al.Text(self.wait_msg, align="center")
    
    def _call_ping(self):
        sid = self.exp.session_id
        query = {
            "type": "match_maker",
            f"members.{sid}.session_id": sid,
        }
        update = {"members": {sid: {"ping": time.time()}}}
        self.exp.db_misc.find_one_and_update(query, update=[{"$set": update}])


@inherit_kwargs
class MatchingPage(WaitingPage):
    """
    A waiting page for matchmaking.

    Args:
        {kwargs}
    
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
                    self += al.Text(f"I was assigned to role '{{role}}'.")
    """
    #: If *True*, the page will save signals of activity in the database
    #: for this experiment session. Important for MatchMaking, but usually
    #: not for ordinary waiting. Defaults to *True*
    ping = True

    