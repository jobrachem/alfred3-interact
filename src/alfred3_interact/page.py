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
            font_size=10,
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
        {kwargs}

    Examples:

        The example below demonstrates how to use the waiting page for
        matchmaking. Matchmaking will start on the second page.
        Participants will be forwarded automatically once matchmaking
        is finished::

            import alfred3 as al
            import alfred3_interact as alint

            exp = al.Experiment()

            exp += al.Page(title="Landing page", name="landing")

            @exp.member
            class MatchPage(alint.WaitingPage):
                title = "Making a Match"

                def wait_for(self):
                    mm = alint.MatchMaker("a", "b", exp=self.exp)
                    self.exp.plugins.group = mm.match_groupwise()
                    return True


            @exp.member
            class Success(al.Page):
                title = "It's a Match!"

        The next example demonstrates how to use the waiting page in
        an ongoing experiment to wait until a group member has proceeded
        to a certain point in the experiment (more precisely, until a
        group member has filled a certain input element)::


            import alfred3 as al
            import alfred3_interact as alint

            exp = al.Experiment()

            @exp.member
            class MatchPage(alint.WaitingPage):
                title = "Making a Match"

                def wait_for(self):
                    mm = alint.MatchMaker("a", "b", exp=self.exp)
                    self.exp.plugins.group = mm.match_groupwise()
                    return True

            @exp.member
            class InputPage(al.Page):

                def on_exp_access(self):
                    self += al.TextEntry(leftlab="Enter text", name="el1", force_input=True)

            @exp.member
            class Sync1(alint.WaitingPage):

                def wait_for(self):
                    you = self.exp.plugins.group.you
                    el1 = you.values.get("el1", False)
                    return el1

            exp += al.Page(title="Waiting successful", name="success")


    """

    title = "Waiting"
    wait_msg: str = "Waiting for other group members."
    wait_timeout: int = 60 * 5
    wait_sleep_time: int = 1

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


class MatchingPage(WaitingPage):

    ping_interval: int = 1

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
