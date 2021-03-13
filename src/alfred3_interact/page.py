import time
from abc import abstractmethod
from functools import wraps

from jinja2 import Template

import alfred3 as al
from alfred3.element.core import Element

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

class WaitingPage(al.NoNavigationPage):
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
            self.exp.abort(reason=MatchMaker.TIMEOUT_MSG, title="Timeout", msg="Sorry, waiting took too long.", icon="user-clock")
        except Exception:
            self.log.exception("Exception in waiting function.")
            self.exp.abort(reason="waiting error")
    
    def on_exp_access(self):
        
        self += al.VerticalSpace("100px")
        self += al.Text(al.icon("spinner", spin=True, size="90pt"), align="center")
        self += al.VerticalSpace("30px")
        self += al.CountUp(font_size=30, align="center")
        self += al.Text(self.wait_msg, align="center")
