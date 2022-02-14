"""
The under-the-hood administration of the chat.
"""

import time
import bleach
from pymongo.collection import ReturnDocument


class ChatManager:
    """
    Manages a chat.

    Args:
        exp (alfred.experiment.ExperimentSession): The experiment session
            to which the chat belongs.
        chat_id (str): Unique identifier for the chat.
        room (str): Shorthand for creating individual rooms of the same
            chat.
        nickname (str): Nickname for the identification of the current
            session.
        colors (dict): Dictionary of colors for identifying participants
            with color.
        encrypt (bool): If True, the content of the messages will be
            encrypted before saving to the database. Requires encryption
            to be enabled on the experiment. Defaults to True.
        ignore_aborted_sessions (bool): If True, the ChatManager will not
            output messages of aborted or expired sessions. Can be
            necessary in experiments with asynchronous interaction to
            prevent confusing chats. Defaults to True.

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

    def __init__(
        self,
        exp,
        chat_id: str,
        nickname: str = None,
        room: str = "",
        colors: dict = None,
        encrypt: bool = True,
        ignore_aborted_sessions: bool = True,
    ):
        self.exp = exp
        room = "_room-" + room if room != "" else ""
        self.chat_id = chat_id + room
        self.colors = colors
        self.encrypt = encrypt
        self.ignore_aborted_sessions = ignore_aborted_sessions

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
        self._local_change_counter = 0
        self.color = self._find_color()

        self._inactive_sids = []
        self.exp.append_plugin_data_query(self._plugin_data_query)

    @property
    def _plugin_data_query(self):
        f = {"exp_id": self.exp.exp_id, "type": "chat_data"}

        q = {}
        q["title"] = "Chat"
        q["type"] = "chat_data"
        q["query"] = {"filter": f}
        q["encrypted"] = True

        return q

    def _find_color_index(self, n) -> int:
        n_colors = len(self.DEFAULT_COLORS)

        if not n <= n_colors:
            while n > n_colors:
                n -= n_colors

        return n

    def _find_color(self):
        if self.colors:
            color = self.colors[self.nickname]
        else:
            i = self._find_color_index(self.member_number)
            color = self.DEFAULT_COLORS[i - 1]

        return color

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
        if not msg:
            return

        msg = bleach.clean(msg)  # sanitize input

        if self.encrypt:
            msg = self.exp.encrypt(msg)

        msg_data = {}
        msg_data["sender_session_id"] = self.exp.session_id
        msg_data["timestamp"] = time.time()
        msg_data["msg"] = msg
        msg_data["nickname"] = self.nickname
        msg_data["color"] = self.color

        self.exp.db_misc.find_one_and_update(
            self._query,
            update={"$push": {"messages": msg_data}, "$inc": {"change_counter": 1}},
            upsert=True,
        )

    def load_messages(self) -> str:
        """
        Loads new messages from the database into the ChatManager instance.

        Returns:
            str: A status indicator. "pass" means that no new messages
            have been found, "update" means that the internal message
            storage has been updated.
        """
        data = self.exp.db_misc.find_one(self._query, projection={"change_counter": True})

        if data.get("change_counter", False) == self._local_change_counter:
            return "pass"

        self._local_change_counter = data["change_counter"]
        chat_data = self.exp.db_misc.find_one(self._query)

        if self.encrypt:
            for msg in chat_data.get("messages", []):
                msg["msg"] = self.exp.decrypt(msg["msg"])

        self.data = chat_data
        if self.ignore_aborted_sessions:
            self._update_session_status()

        return "update"

    def get_new_messages(self) -> tuple:
        """
        Returns:
            tuple: All new messages belonging to the chat
        """
        if self.data and self.data.get("messages", False):
            i, self._loaded_index = self._loaded_index, len(self.data["messages"])

            msgs = self.data["messages"][i : self._loaded_index]
            out_messages = [
                msg for msg in msgs if msg["sender_session_id"] not in self._inactive_sids
            ]

            return tuple(out_messages)
        else:
            return tuple()

    def get_all_messages(self) -> tuple:
        """
        Returns:
            tuple: All messages belonging to the chat
        """
        if self.data and self.data.get("messages", False):
            msgs = self.data["messages"]
            self._loaded_index = len(msgs)

            out_messages = [
                msg for msg in msgs if msg["sender_session_id"] not in self._inactive_sids
            ]

            # if self.encrypt:
            #     for msg in out_messages:
            #         msg["msg"] = self.exp.decrypt(msg["msg"])

            return tuple(out_messages)
        else:
            return tuple()

    def _update_session_status(self):
        """
        Updates the list of inactive session IDs.
        """
        if not self.data.get("messages", False):
            return
        sids = [msg["sender_session_id"] for msg in self.data["messages"]]
        sids = set(sids)

        uncertain_sids = sids - set(self._inactive_sids)

        for sid in uncertain_sids:
            query = {"type": "exp_data", "exp_session_id": sid}
            sdata = self.exp.db_main.find_one(
                query,
                projection={"exp_aborted": True, "exp_start_time": True, "exp_finished": True},
            )

            if sdata["exp_aborted"]:
                self._inactive_sids.append(sid)

            elif self.exp.session_timeout and not sdata["exp_finished"]:
                expired = time.time() - sdata["exp_start_time"] > self.exp.session_timeout
                if expired:
                    self._inactive_sids.append(sid)
