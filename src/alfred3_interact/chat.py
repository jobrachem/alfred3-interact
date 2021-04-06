import time
from pymongo.collection import ReturnDocument

class ChatManager:
    """
    Manages a chat.

    Args:
        exp (alfred.experiment.ExperimentSession): The experiment session
            to which the chat belongs.
        chat_id (str): Unique identifier for the chat.
        nickname (str): Nickname for the identification of the current 
            session.
        colors (dict): Dictionary of colors for identifying participants
            with color.
    """

    # colors from https://colorbrewer2.org/#type=qualitative&scheme=Paired&n=12
    DEFAULT_COLORS = [
        "#1f78b4",
        "#33a02c",
        "#e31a1c",
        "#ff7f00",
        "#6a3d9a",
        "#b15928",
        "#a6cee3",
        "#b2df8a",
        "#fb9a99",
        "#fdbf6f",
        "#cab2d6",
    ]

    def __init__(self, exp, chat_id: str, nickname: str = None, colors: dict = None):
        self.exp = exp
        self.chat_id = chat_id
        self.colors = colors

        self._query = {}
        self._query["exp_id"] = self.exp.exp_id
        self._query["type"] = "chat_data"
        self._query["chat_id"] = self.chat_id

        self.nickname = nickname
        self.member_number = self._register_session()
        if self.nickname is None:
            self.nickname = "Anonymous " + str(self.member_number)

        self.data = None
        self._loaded_index = 0
        self.color = self._find_color()

    def _find_color_index(self, n) -> int:
        n_colors = len(self.DEFAULT_COLORS)
        if n <= n_colors:
            return n

        else:
            while n > n_colors:
                n -= n_colors
            return n

    def _find_color(self):
        if self.colors:
            return self.colors[self.nickname]
        else:
            i = self._find_color_index(self.member_number)
            return self.DEFAULT_COLORS[i - 1]

    def _register_session(self) -> int:
        """Returns chat member number (a simple count)"""
        doc = self.exp.db_misc.find_one_and_update(
            self._query,
            update=[{"$set": {"sessions": {self.exp.session_id: "registered"}}}],
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return len(doc["sessions"])

    def post_message(self, msg: str):
        """
        Posts a new message to the database.
        """
        msg_data = {}
        msg_data["sender_session_id"] = self.exp.session_id
        msg_data["timestamp"] = time.time()
        msg_data["msg"] = msg
        msg_data["nickname"] = self.nickname
        msg_data["color"] = self.color

        self.exp.db_misc.find_one_and_update(
            self._query, update={"$push": {"messages": msg_data}}, upsert=True
        )

    def load_messages(self) -> str:
        """
        Loads new messages from the database. 
        
        Returns:
            str: A status indicator. "init" means that the method has
            been called for the first time in the current session, 
            "append" means that new messages have been loaded and 
            appended, "pass" means that no new messages have been found.
        """
        chat_data = self.exp.db_misc.find_one(self._query)

        if not self.data or not self.data.get("messages", False):
            self.data = chat_data
            return "init"
        else:
            msgs_db = chat_data["messages"]
            n_local = len(self.data["messages"])
            self.data["sessions"] = chat_data["sessions"]

            if len(msgs_db) > n_local:
                msgs_db.sort(key=lambda msg: msg["timestamp"])
                self.data["messages"] += msgs_db[n_local:]
                return "append"

            else:
                return "pass"

    def get_new_messages(self) -> tuple:
        """
        Returns:
            tuple: All new messages belonging to the chat
        """
        if self.data and self.data.get("messages", False):
            i, self._loaded_index = self._loaded_index, len(self.data["messages"])
            return tuple(self.data["messages"][i:])
        else:
            return None

    def get_all_messages(self) -> tuple:
        """
        Returns:
            tuple: All messages belonging to the chat
        """
        if self.data and self.data.get("messages", False):
            self._loaded_index = len(self.data["messages"])
            return tuple(self.data["messages"])
        else:
            return None
