import pytest
import alfred3 as al
from alfred3_interact.chat import ChatManager

from ._util import exp, secrets

@pytest.fixture
def chat(exp):
    c = ChatManager(exp, "testing_chat")
    yield c
    exp.db_misc.delete_many(c._query)

def test_post_one_message(chat, exp):
    chat.post_message("test")
    doc = exp.db_main.find_one(chat._query)
    
    assert doc
    assert len(doc["messages"]) == 1
    assert doc["chat_id"] == "testing_chat"
    assert doc["type"] == "chat_data"
    
    msg = doc["messages"][0]
    
    assert msg["msg"] == "test"
    assert msg["sender_session_id"] == exp.session_id
    assert isinstance(msg["timestamp"], float)

def test_load_one_message(chat):
    chat.post_message("test")
    rv = chat.load_messages()

    assert len(chat.data["messages"]) == 1
    assert rv == "init"

def test_load_two_messages(chat):
    chat.post_message("test")
    chat.post_message("test")
    chat.load_messages()
    assert len(chat.data["messages"]) == 2


def test_load_stepwise(chat):
    chat.post_message("test")
    chat.load_messages()
    assert len(chat.data["messages"]) == 1
    
    chat.post_message("test")
    rv = chat.load_messages()
    assert len(chat.data["messages"]) == 2
    assert rv == "append"

def test_pass(chat):
    chat.post_message("test")
    chat.load_messages()
    rv = chat.load_messages()
    assert rv == "pass"

    