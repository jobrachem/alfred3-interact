import pytest
from alfred3_interact.chat import ChatManager
from alfred3.testutil import get_exp_session, clear_db

from dotenv import load_dotenv
load_dotenv()

@pytest.fixture
def exp(tmp_path):
    script = "tests/res/script-hello_world.py"
    secrets = "tests/res/secrets-default.conf"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)
    
    yield exp

    clear_db()

@pytest.fixture
def chat(exp):
    exp._start()
    exp._save_data(sync=True)
    c = ChatManager(exp, "testing_chat", encrypt=False)
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
    chat.load_messages()

    assert len(chat.data["messages"]) == 1

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

def test_pass(chat):
    chat.post_message("test")
    chat.load_messages()
    chat.load_messages()
    assert len(chat.data["messages"]) == 1

    