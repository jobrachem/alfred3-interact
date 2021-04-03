import time
from abc import abstractmethod
from functools import wraps

from jinja2 import Template

import alfred3 as al
from alfred3.element.core import Element
from alfred3._helper import inherit_kwargs

from .match import MatchMaker
from ._util import MatchingTimeout

class Callback(Element):

    web_widget = None
    should_be_shown = False

    def __init__(self, func: callable):
        super().__init__()
        self.func = func
        self.url = None
    
    def prepare_web_widget(self):
        self._js_code = []
        super().prepare_web_widget()
        self.url = self.exp.ui.add_callable(self.func)
        
        js_template = Template("""
        $(document).ready(function () {
    
            $.get( "{{ url }}", function(data) {
                
                $("#alt-submit").attr("name", "move");
                $("#alt-submit").val("forward");
                $("#form").submit();
            });
            
        });
        """)
        js = js_template.render(url=self.url)
        self.add_js(js)


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
    wait_timeout: int = 60*5
    wait_sleep_time: int = 1

    def __init__(self, *args, wait_msg: str = None, wait_timeout: int = None, wait_sleep_time: int = None, **kwargs):
        super().__init__(*args, **kwargs)
        
        if wait_msg is not None:
            self.wait_msg = wait_msg
        
        if wait_timeout is not None:
            self.wait_timeout = wait_timeout
        
        if wait_sleep_time is not None:
            self.wait_sleep_time = wait_sleep_time
        
        self += Callback(self._wait_for)

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
        
        except MatchingTimeout:
            self.log.exception("Timeout on waiting page.")
            self.exp.abort(reason=MatchMaker._TIMEOUT_MSG, title="Timeout", msg="Sorry, waiting took too long.", icon="user-clock")
        except Exception:
            self.log.exception("Exception in waiting function.")
            self.exp.abort(reason="waiting error")
    
    def on_exp_access(self):
        
        self += al.VerticalSpace("100px")
        self += al.Text(al.icon("spinner", spin=True, size="90pt"), align="center")
        self += al.VerticalSpace("30px")
        self += al.CountUp(font_size=30, align="center")
        self += al.Text(self.wait_msg, align="center")
