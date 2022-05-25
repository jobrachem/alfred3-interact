import pytest
from alfred3.testutil import clear_db, get_exp_session
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def exp(tmp_path):
    script = "tests/res/script-hello_world.py"
    secrets = "tests/res/secrets-default.conf"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)

    yield exp

    clear_db(mock=False)


@pytest.fixture
def exp_factory(tmp_path):
    def expf(sid: str = None, timeout=None):
        script = "tests/res/script-hello_world.py"
        secrets = "tests/res/secrets-default.conf"
        exp = get_exp_session(
            tmp_path, script_path=script, secrets_path=secrets, sid=sid, timeout=timeout
        )
        return exp

    yield expf

    clear_db(mock=False)


@pytest.fixture
def lexp(tmp_path):
    script = "tests/res/script-hello_world.py"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=None)

    yield exp


@pytest.fixture
def lexp_factory(tmp_path):
    def lexp(sid: str = None, timeout=None):
        script = "tests/res/script-hello_world.py"
        exp = get_exp_session(
            tmp_path, script_path=script, secrets_path=None, sid=sid, timeout=timeout
        )

        return exp

    yield lexp
