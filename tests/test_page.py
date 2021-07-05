import time
import pytest
import alfred3_interact as ali
from alfred3.testutil import get_exp_session, clear_db
from alfred3_interact.match import MatchMaker
from alfred3_interact.testutil import get_group

from dotenv import load_dotenv
load_dotenv()

@pytest.fixture
def exp(tmp_path):
    script = "tests/res/script-hello_world.py"
    secrets = "tests/res/secrets-default.conf"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)
    
    yield exp

    clear_db()


def test_waiting_page(exp):
    
    class Wait(ali.WaitingPage):

        def wait_for(self):
            return True

    page = Wait(name="waiting_test")
    exp += page

    result = page._wait_for()
    assert result

def test_match_groupwise(exp):
    class Wait(ali.WaitingPage):

        def wait_for(self):
            self.exp.plugins.mm.match_groupwise()
            return True
    
    page = Wait(name="waiting_test")
    
    mm = ali.MatchMaker("a", "b", exp=exp)
    exp.plugins.mm = mm

    exp += page

    result = page._wait_for()
    assert not result

def test_admin_page(exp):
    mm = ali.MatchMaker("a", "b", exp=exp)
    page = ali.page.AdminPage(mm, name="admin")
    exp += page

    assert exp.admin

def test_password_page(exp):
    mm = ali.MatchMaker("a", "b", exp=exp)
    page = ali.page.PasswordPage("pw", mm, name="pwpage")
    exp += page

    assert exp.pwpage


    