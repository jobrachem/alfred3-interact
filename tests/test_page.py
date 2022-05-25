import threading
import time

import pytest
from alfred3.testutil import clear_db, forward, get_app
from flask import Blueprint, request
from selenium import webdriver

import alfred3_interact as ali

testing = Blueprint("test", __name__)


@testing.route("/stop")
def stop():
    func = request.environ.get("werkzeug.server.shutdown")
    if func is None:
        raise RuntimeError("Not running with the Werkzeug Server")
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


@pytest.fixture
def admin_client(tmp_path):
    script = "tests/res/script-admin.py"
    secrets = "tests/res/secrets-default.conf"

    app = get_app(tmp_path, script_path=script, secrets_path=secrets)

    with app.test_client() as client:
        yield client

    clear_db()


@pytest.mark.skip("Should be run manually")
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

    # def test_expire_browser(self, running_app, driver):
    #     """
    #     Only valid when being run on its own. Will sometimes fail if another test that
    #     uses the selenium driver ran shortly before. Run again individually
    #     to see whether there is an actual problem with the code.
    #     """
    #     driver.get("http://localhost:5000/start")
    #     time.sleep(10)
    #     assert "Sorry, waiting took too long" in driver.page_source

    # def test_refresh_browser(self, running_app, driver):
    #     """
    #     Only valid when being run on its own. Will sometimes fail if another test that
    #     uses the selenium driver ran shortly before. Run again individually
    #     to see whether there is an actual problem with the code.
    #     """
    #     driver.get("http://localhost:5000/start")
    #     time.sleep(4)
    #     driver.refresh()
    #     time.sleep(10)
    #     assert "Sorry, waiting took too long" in driver.page_source


@pytest.mark.skip("Should be run manually")
class TestAdminPage:
    def test_monitoring(self, admin_client):
        rv = admin_client.get("/start?admin=true", follow_redirects=True)
        rv = forward(admin_client, data={"pw": "1"})
        assert b"MatchMaker Monitoring" in rv.data
        assert b"Bitte geben Sie etwas ein." not in rv.data
        assert b"Weiter" not in rv.data

        rv = forward(admin_client)
        assert b"There's nothing here" in rv.data

    def test_activation(self, admin_client):
        rv = admin_client.get("/start?admin=true", follow_redirects=True)
        rv = forward(admin_client, data={"pw": "2"})
        assert b"MatchMaker Monitoring" in rv.data

        rv = forward(admin_client)
        assert b"MatchMaker Activation" in rv.data

        rv = forward(admin_client)
        assert b"There's nothing here" in rv.data
