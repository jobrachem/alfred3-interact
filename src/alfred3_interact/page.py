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
            "Waiting for other group members."
        wait_timeout (int): Maximum waiting time in seconds. If *wait_for* 
            does not return a *True*-like value within waiting time, the experiment 
            session is aborted. Defaults to None, in which case the 
            timeout is ``60 * 20``, i.e. 20 minutes.
        wait_sleep_time (int): Number of seconds in between two internal
            calls to :meth:`.wait_for`. Defaults to None, in which case
            a call will be made every two seconds.
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

    def __init__(
        self,
        *args,
        wait_msg: str = None,
        wait_timeout: int = None,
        wait_sleep_time: int = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if wait_msg is not None:
            self.wait_msg = wait_msg

        if wait_timeout is not None:
            self.wait_timeout = wait_timeout

        if wait_sleep_time is not None:
            self.wait_sleep_time = wait_sleep_time

        self += Callback(self._wait_for, followup="forward")

    @abstractmethod
    def wait_for(self):
        """
        One this method returns a *True*-like value, the page automatically 
        forwards participants to the next page.

        It will be repeatedly called internally with the time between
        two calls defined by :attr:`.wait_sleep_time`.
        """
        pass

    def _wait_for(self):
        try:
            start = time.time()

            while not self.wait_for() and not self.exp.aborted:
                time.sleep(self.wait_sleep_time)

                if time.time() - start > self.wait_timeout:
                    raise MatchingTimeout

        except SessionTimeout:
            pass  # the experiment handles session timeouts

        except MatchingTimeout:
            self.log.exception("Timeout on waiting page.")
            self.exp.abort(
                reason=MatchMaker._TIMEOUT_MSG,
                title="Timeout",
                msg="Sorry, waiting took too long.",
                icon="user-clock",
            )
        except Exception:
            self.log.exception("Exception in waiting function.")
            self.exp.abort(reason="waiting error")

    def on_exp_access(self):

        self += al.VerticalSpace("100px")
        self += al.Text(al.icon("spinner", spin=True, size="90pt"), align="center")
        self += al.VerticalSpace("30px")
        self += al.CountUp(font_size=30, align="center")
        self += al.Text(self.wait_msg, align="center")

@inherit_kwargs
class MatchingPage(WaitingPage):
    """
    A page that provides a waiting screen and participant activity check 
    while waiting for a match to complete.

    Apart from the activity ping, the behavior and usage of the 
    MatchingPage is the same as in :class:`.WaitingPage`, i.e. you 
    must overload the method :meth:`.wait_for`, and as soon as *wait_for*
    returns *True*, participants are forwarded to the next page.

    Args:
        ping_interval (int): The number of seconds in between two 
            activity pings being sent to the server. If None (default),
            a ping is sent every three seconds. Can be defined as a class
            attribute.
        
        {kwargs}

    Examples:
        ::

            import alfred3 as al
            import alfred3_interact as ali

            exp = al.Experiment()

            exp += al.Page(title="Landing page", name="landing")

            @exp.member
            class MatchPage(ali.WaitingPage):
                title = "Making a Match"

                def wait_for(self):
                    mm = ali.MatchMaker("a", "b", exp=self.exp)
                    self.exp.plugins.group = mm.match_groupwise()
                    return True


            @exp.member
            class Success(al.Page):
                title = "It's a Match!"
    """
    
    #: The number of seconds in between two 
    #: activity pings being sent to the server. If None (default),
    #: a ping is sent every three seconds. Can be defined as a class
    #: attribute.
    ping_interval: int = 3

    def __init__(self, ping_interval: int = None, **kwargs):
        super().__init__(**kwargs)

        if ping_interval is not None:
            self.ping_interval = ping_interval

    def on_exp_access(self):
        super().on_exp_access()
        self += RepeatedCallback(func=self._ping, interval=self.ping_interval, submit_first=False)

    def _ping(self):
        sid = self.exp.session_id
        query = {
            "type": "match_maker",
            f"members.{sid}.session_id": sid,
        }
        update = {"members": {sid: {"ping": time.time()}}}
        self.exp.db_misc.find_one_and_update(query, update=[{"$set": update}])
