"""
Specialized elements for interactive experiments.
"""

import time
from typing import Union

from pymongo.collection import ReturnDocument
from jinja2 import Environment, PackageLoader, Template
from alfred3.element.core import Element
from alfred3 import icon
from alfred3._helper import inherit_kwargs
from alfred3.data_manager import DataManager as dm

from .chat import ChatManager

jenv = Environment(loader=PackageLoader(__name__, "templates"))

@inherit_kwargs(exclude=["height"])
class Chat(Element):
    """
    Provides a chat window.

    This chat window can be used for real-time chat as well as for
    a kind of message-board.

    Args:
        chat_id (str): Unique identifier for the chat. Participants will
            be grouped together based on the chat id. For a group chat,
            it is sensible to use the group id here.
        
        nickname (str): Every chat participant gets a nickname that
            will be used to identify participant's messages. You can
            choose a custom nickname for the current session here. Although
            advisable, it is not strictly necessary to use unique nicknames.
            By default, chat participants will be identified by 
            'Anonymous x', where x is generated by counting through chat
            participants.
        
        room (str): Shorthand for creating individual rooms of the same
            chat. Defaults to an empty string: ``""``.
        
        placeholder (str): Text to display as a placeholder in the input
            field. Defaults to '...'

        disabled (bool): If *True*, the input field and send button will
            be disabled. Participants will be able to read the chat, but
            not to post messages. Defaults to *False*.
        
        readonly (bool): If *True*, the input field and send button will
            be completely hidden. Participants will be able to read the 
            chat, but not to post messages. Defaults to *False*.

        button_text (str): Text to display on the send-button. Defaults
            to a 'paper-plane' icon.

        msg_width (str): Width of chat messages in percent of the total
            width of the chat window. Don't forget to use the '%' sign. 
            Defaults to '70%'.
        
        height (str): Element height. Supply a string with unit 
            understood by CSS. Defaults to '350px'.

        colors (dict): Dictionary of colors to use for identification
            of chat participants. The dict should have nicknames as keys
            and color values that can be understood by CSS as values.
            By default, the chat element will go through a predefined
            list of 11 colors.
        
        color_target (str): Defines, how colors are used to identify
            participants. Can be 'nickname', 'border', or 'none'.
            Defaults to 'nickname'.
        
        button_style (str): Can be used for quick color-styling, using
            Bootstraps default color keywords: btn-primary, btn-secondary,
            btn-success, btn-info, btn-warning, btn-danger, btn-light,
            btn-dark. You can also use the "outline" variant to get
            outlined buttons (eg. "btn-outline-secondary"). 
        
        background_color (str): Background color for the chat windows.
            Can be any color understood by CSS. Defaults to 'WhiteSmoke',
            a kind of light grey.
        
        allow_resize (bool): If *True*, participants can adjust the 
            height of the text input field. Defaults to True.
        
        refresh_interval (int, float): Time in seconds, determines how
            often the chat elements looks for new messages. Defaults to
            1.

        {kwargs}
    
    Examples:

        A minimal message-board style chat::

            import alfred3 as al
            import alfred3_interact as ali
            
            exp = al.Experiment()

            exp += al.Page(title="Chat Demo", name="chat_demo")
            exp.chat_demo += ali.Chat("test_chat")
        
        A group chat in an interactive experiment::

            import alfred3 as al
            import alfred3_interact as ali

            exp = al.Experiment()

            @exp.setup
            def setup(exp):
                exp.plugins.mm = ali.MatchMaker("a", "b", exp=exp)
            
            @exp.member
            class Match(ali.MatchingPage):

                def wait_for(self):
                    self.exp.plugins.group = self.exp.plugins.mm.match_groupwise()
                    return True
            
            @exp.member
            class Success(al.Page):
                title = "Match Successful!"

                def on_first_show(self):
                    self += self.exp.plugins.group.chat()

    """

    element_template = jenv.get_template("html/ChatElement.html.j2")
    js_template = jenv.get_template("js/chat_element.js.j2")

    def __init__(
        self,
        chat_id: str,
        nickname: str = None,
        room: str = "",
        placeholder: str = "Press enter to send your message, shift+enter for a linebreak",
        disabled: bool = False,
        readonly: bool = False,
        button_text: str = icon("paper-plane"),
        msg_width: str = "70%",
        height: str = "350px",
        colors: dict = None,
        color_target: str = "nickname",
        you_label: str = " (you)",
        button_style: str = "btn-dark",
        background_color: str = "WhiteSmoke",
        allow_resize: bool = True,
        refresh_interval: Union[int, float] = 1,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.chat_id = chat_id
        self.room = room
        self.chat_manager = None
        self.nickname = nickname
        self.you_label = you_label

        self.msg_width = msg_width

        self.post_url = None
        self.load_url = None
        self.get_new_url = None
        self.get_all_url = None

        self.colors = colors
        self.color_target = color_target
        self.placeholder = placeholder
        self.button_text = button_text
        self.button_style = button_style
        self.height = height
        self.background_color = background_color
        self.disabled = True if readonly else disabled
        self.readonly = readonly
        self.allow_resize = allow_resize

        self._interval = refresh_interval

    @property
    def _js_data(self):
        d = {}
        d["post_url"] = self.post_url
        d["load_url"] = self.load_url
        d["get_new_url"] = self.get_new_url
        d["get_all_url"] = self.get_all_url
        d["interval"] = self._interval
        d["name"] = self.name
        d["own_nickname"] = self.chat_manager.nickname
        d["msg_width"] = self.msg_width
        d["color_target"] = self.color_target
        d["you_label"] = self.you_label
        return d

    def added_to_experiment(self, exp):
        super().added_to_experiment(exp)
        self.chat_manager = ChatManager(self.exp, self.chat_id, self.nickname, self.room, self.colors)

        self.post_url = self.exp.ui.add_callable(self.chat_manager.post_message)
        self.load_url = self.exp.ui.add_callable(self.chat_manager.load_messages)
        self.get_new_url = self.exp.ui.add_callable(self.chat_manager.get_new_messages)
        self.get_all_url = self.exp.ui.add_callable(self.chat_manager.get_all_messages)

        js = self.js_template.render(self._js_data)
        self.add_js(js)

        if self.readonly:
            css = f"#{self.name}-input-group {{display: none;}}"
            self.add_css(css)

    @property
    def template_data(self) -> dict:
        d = super().template_data
        d["placeholder"] = self.placeholder
        d["button_text"] = self.button_text
        d["button_style"] = self.button_style
        d["height"] = self.height
        d["background_color"] = self.background_color
        d["disabled"] = self.disabled
        d["allow_resize"] = self.allow_resize
        return d

class ViewMembers(Element):
    element_template = jenv.get_template("html/ViewMembersElement.html.j2")
    view_js = jenv.get_template("js/view_members.js.j2")
    
    def __init__(self, match_maker, refresh_interval: int = 10, **kwargs):
        super().__init__(**kwargs)
        self.match_maker = match_maker
        self.render_url = None
        self.refresh_interval = refresh_interval
    
    def added_to_experiment(self, exp):
        super().added_to_experiment(exp)
        
        self.render_url = self.exp.ui.add_callable(self.render_table_body)
        cols = ["Session", "Status", "Condition", "Last Page", "Start Day", "Start Time", "Last Move", "Group", "Role"]
        js = self.view_js.render(name=self.name, render_url=self.render_url, refresh_interval=self.refresh_interval, cols=cols)
        self.add_js(js)

    
    @property
    def template_data(self):
        d = super().template_data
        d["members"] = self.match_maker.member_manager.members()
        return d
    
    def render_table_body(self):

        members = self.match_maker.member_manager.members()
        tbody = []
        for m in members:
            last_page = m.last_page if len(m.last_page) < 20 else m.last_page[:17] + "..."

            d = {}
            d["Session"] = m.session_id[-4:]
            d["Status"] = m.status
            d["Condition"] = self._condition_of(m.session_id)
            d["Last Page"] = last_page
            d["Start Day"] = m.start_day
            d["Start Time"] = m.start_time
            d["Last Move"] = m.last_move
            d["Group"] = m.group_id[-4:] if m.group_id else "-"
            d["Role"] = m.role
            tbody.append(d)

        return {"data": tbody}
    
    def _condition_of(self, sid: str) -> str:
        q = {}
        q["exp_id"] = self.exp.exp_id
        q["type"] = dm.EXP_DATA
        q["exp_session_id"] = sid

        pro = {"exp_condition": True}
        doc = self.exp.db_main.find_one(q, projection=pro)
        return doc["exp_condition"]

class ToggleMatchMakerActivation(Element):
    element_template = jenv.get_template("html/ToggleMatchMakerActivation.html.j2")
    js_template = jenv.get_template("js/toggle_match_maker.js.j2")

    def __init__(self, match_maker, **kwargs):
        super().__init__(**kwargs)
        self.match_maker = match_maker
        self.toggle_url = None

    def added_to_experiment(self, exp):
        super().added_to_experiment(exp)
        self.toggle_url = self.exp.ui.add_callable(self.match_maker.toggle_activation)
        js = self.js_template.render(name=self.name, toggle_url=self.toggle_url)
        self.add_js(js)

    @property
    def template_data(self):
        d = super().template_data
        if self.match_maker.active:
            d["text"] = '<i class="fas fa-circle-notch fa-spin mr-2"></i>MatchMaker is ACTIVE'
            d["button_style"] = "btn-success"
        else:
            d["text"] = '<i class="fas fa-circle-notch mr-2"></i>MatchMaker is INACTIVE'
            d["button_style"] = "btn-secondary"
        return d

    