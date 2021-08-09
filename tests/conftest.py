import pytest
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
def exp_factory(tmp_path):
    def expf(sid: str=None):
        script = "tests/res/script-hello_world.py"
        secrets = "tests/res/secrets-default.conf"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets, sid=sid)
        return exp
    
    yield expf

    clear_db()

@pytest.fixture
def lexp(tmp_path):
    script = "tests/res/script-hello_world.py"
    exp = get_exp_session(tmp_path, script_path=script, secrets_path=None)
    
    yield exp

@pytest.fixture
def lexp_factory(tmp_path):
    def lexp(sid: str = None):
        script = "tests/res/script-hello_world.py"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=None, sid=sid)
        
        return exp
    yield lexp