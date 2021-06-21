import pytest
import alfred3_interact as ali
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
    def expf():
        script = "tests/res/script-hello_world.py"
        secrets = "tests/res/secrets-default.conf"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)
        return exp
    
    yield expf

    clear_db()


def test_init(exp):
    mm = ali.MatchMaker("a", "b", exp=exp)
    g = mm.match_stepwise()

    assert g is not None


def test_match(exp_factory):
    exp1 = exp_factory()
    exp1._session_id = "exp1"
    exp2 = exp_factory()
    exp2._session_id = "exp2"

    mm1 = ali.MatchMaker("a", "b", exp=exp1)
    mm2 = ali.MatchMaker("a", "b", exp=exp2)

    exp1._start()
    exp2._start()

    exp1._save_data(sync=True)
    exp2._save_data(sync=True)

    with pytest.raises(ali._util.NoMatch):
        group1 = mm1.match_groupwise()
    
    group2 = mm2.match_groupwise()
    group1 = mm1.match_groupwise()

    assert group1.group_id == group2.group_id

