import time
import pytest
import threading

from flask import request, Blueprint
from selenium import webdriver
import alfred3_interact as ali
from alfred3.testutil import get_app


testing = Blueprint("test", __name__)

@testing.route("/stop")
def stop():
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return "Shutting down server..."

@pytest.fixture
def driver():
    chrome = webdriver.Chrome()
    yield chrome
    chrome.get("http://localhost:5000/stop")
    chrome.close()

@pytest.fixture
def running_app(tmp_path):
    script = "tests/res/script-wait.py"
    secrets = "tests/res/secrets-default.conf"

    app = get_app(tmp_path, script_path=script, secrets_path=secrets)
    app.register_blueprint(testing)
    t = threading.Thread(target=app.run, kwargs={"port": 5000, "use_reloader": False})
    t.start()
    yield app

class TestWaitingPage:

    def test_waiting_page(self, exp):
        
        class Wait(ali.WaitingPage):

            def wait_for(self):
                return True

        page = Wait(name="waiting_test")
        exp += page

        result = page._wait_for()
        assert result
    
    def test_expire(self, exp):

        class Wait(ali.WaitingPage):
            wait_timeout = 1

            def wait_for(self):
                return False
        
        page = Wait(name="waiting_test")
        exp += page

        page._wait_for()
        time.sleep(1)
        page._wait_for()
        assert exp.aborted
    
    def test_expire_browser(self, running_app, driver):
        driver.get("http://localhost:5000/start")
        time.sleep(10)
        assert "Sorry, waiting took too long" in driver.page_source
    
    def test_refresh_browser(self, running_app, driver):
        driver.get("http://localhost:5000/start")
        time.sleep(4)
        driver.refresh()
        time.sleep(10)
        assert "Sorry, waiting took too long" in driver.page_source


class TestAdminPage:

    def test_page_works(self, exp):
        spec = ali.ParallelSpec("a", "b", name="test", nslots=3)
        mm = ali.MatchMaker(spec, exp=exp)
        page = ali.page.AdminPage(mm, name="admin")
        exp += page
        exp._start()
        exp.jump("admin")

        p = exp.ui.render("token")

        assert "Matchmaker ID" in p
    
    def test_member_table(self, exp):
        spec = ali.SequentialSpec("a", "b", name="test", nslots=3)
        mm = ali.MatchMaker(spec, exp=exp)

        group = mm.match_to("test")
        page = ali.page.AdminPage(mm, name="admin")
        exp += page
        exp.condition = "test"
        exp._start()
        exp.jump("admin")
        exp._save_data(sync=True)

        body = page.view_mm.render_table_body()
        data = body["data"][0]

        assert data["Session"]
        assert data["Condition"] == "test"
        assert data["Start Day"]
        assert data["Start Time"]
        assert data["Last Move"]
        assert data["Group"]
        assert data["Role"] == group.me.role
        assert data["Status"] == "active"
        assert data["Last ping"] == "(already matched)"





def test_password_page(exp):
    spec = ali.ParallelSpec("a", "b", name="test", nslots=3)
    mm = ali.MatchMaker(spec, exp=exp)

    page = ali.page.PasswordPage("pw", mm, name="pwpage")
    exp += page

    assert exp.pwpage


    