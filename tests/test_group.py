import pytest
import alfred3_interact as ali
from alfred3.testutil import get_exp_session, clear_db, get_json
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

@pytest.fixture
def exp_factory(tmp_path):
    def expf():
        script = "tests/res/script-hello_world.py"
        secrets = "tests/res/secrets-default.conf"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)
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
    def lexp():
        script = "tests/res/script-hello_world.py"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=None)
        
        return exp
    yield lexp

@pytest.fixture
def group(exp):
    yield get_group(exp, ["a", "b"], ongoing_sessions_ok=False)

@pytest.fixture
def lgroup(lexp):
    yield get_group(lexp, ["a", "b"], ongoing_sessions_ok=False)

def test_clear(exp):
    """
    Just for clearing the database in case a test breaks down with an error.
    """
    print(exp)


class TestGroupMemberAccess:

    def test_role_attribute_access(self, group):
        assert group.a.data.type == "match_member"
    
    def test_role_bracket_access(self, group):
        assert group["a"].data.type == "match_member"
    
    def test_me_you(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)

        group1.load()
        assert group1.me.data.role == "a"
        assert group1.you.data.role == "b"

        assert group2.me.data.role == "b"
        assert group2.you.data.role == "a"
    
    def test_members(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        group3 = get_group(exp3, ["a", "b"], ongoing_sessions_ok=True)

        members = list(group3.members())
        active = list(group3.active_members())
        others = list(group3.other_members())
        active_others = list(group3.active_other_members())

        assert len(members) == 3
        assert len(active) == 2

        assert len(others) == 2
        assert len(active_others) == 1

        assert group3.me not in [*others, *active_others]
    
    def test_finished_active(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)

        assert group1.nactive == group2.nactive == 2

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        assert group1.nactive == group2.nactive == 1

        exp2.finish()

        assert group1.nfinished == group2.nfinished == 1
        assert group1.nactive == group2.nactive == 0

class TestTakesMembers:
    def test_new_group(self, exp_factory):

        exp = exp_factory()
        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)
        
        assert not group.takes_members(ongoing_sessions_ok=False)

    def test_finished_exp(self, exp_factory):
        exp = exp_factory()
        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)

        exp._start()
        exp.finish()

        assert group.takes_members(ongoing_sessions_ok=False)

    def test_aborted_exp(self, exp_factory):
        exp = exp_factory()
        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)

        exp._start()
        exp.abort("test")
        exp._save_data(sync=True)

        assert group.takes_members(ongoing_sessions_ok=False)
    
    def test_expired_exp(self, exp_factory):
        exp = exp_factory()
        exp._session_timeout = 0.1

        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)

        exp._start()
        exp.abort("test")
        exp._save_data(sync=True)

        assert exp.session_expired
        assert group.takes_members(ongoing_sessions_ok=False)
    
    def test_group_full(self, exp_factory):
        exp1 = exp_factory()
        mm1 = ali.MatchMaker("a", "b", exp=exp1)
        group1 = mm1.match_stepwise(ongoing_sessions_ok=False)

        exp1._start()
        exp1.finish()

        assert group1.takes_members(ongoing_sessions_ok=False)

        exp2 = exp_factory()
        mm2 = ali.MatchMaker("a", "b", exp=exp2)
        group2 = mm2.match_stepwise(ongoing_sessions_ok=False)

        assert group1 == group2

        group1.load()
        assert not group1.takes_members(ongoing_sessions_ok=False)
        assert not group2.takes_members(ongoing_sessions_ok=False)


class TestTakesMembersLocal:
    
    def test_new_group(self, lexp_factory):

        exp = lexp_factory()
        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)
        
        assert not group.takes_members(ongoing_sessions_ok=False)
    
    def test_finished_exp(self, lexp_factory, tmp_path):
        exp = lexp_factory()
        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)

        exp._start()
        exp.finish()

        assert group.takes_members(ongoing_sessions_ok=False)
    
    def test_aborted_exp(self, lexp_factory):
        exp = lexp_factory()
        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)

        exp._start()
        exp.abort("test")
        exp._save_data(sync=True)

        assert group.takes_members(ongoing_sessions_ok=False)
    

    def test_expired_exp(self, lexp_factory):
        exp = lexp_factory()
        exp._session_timeout = 0.1

        mm = ali.MatchMaker("a", "b", exp=exp)
        group = mm.match_stepwise(ongoing_sessions_ok=False)

        exp._start()
        exp.abort("test")
        exp._save_data(sync=True)

        assert exp.session_expired
        assert group.takes_members(ongoing_sessions_ok=False)

    def test_group_full(self, lexp_factory):
        exp1 = lexp_factory()
        mm1 = ali.MatchMaker("a", "b", exp=exp1)
        group1 = mm1.match_stepwise(ongoing_sessions_ok=False)

        exp1._start()
        exp1.finish()

        assert group1.takes_members(ongoing_sessions_ok=False)

        exp2 = lexp_factory()
        mm2 = ali.MatchMaker("a", "b", exp=exp2)
        group2 = mm2.match_stepwise(ongoing_sessions_ok=False)

        assert group1 == group2

        assert group1.me.data.role != group2.me.data.role

        group1.load()
        assert not group1.takes_members(ongoing_sessions_ok=False)
        assert not group2.takes_members(ongoing_sessions_ok=False)


class TestSharedData:

    def test_sync(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)

        group1.shared_data["test"] = "test"

        assert group2.shared_data["test"] == "test"
    
    def test_start(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        assert "__group_id" in group1.shared_data
        
        group1.shared_data["test"] = "test"
        
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)
        assert group2.shared_data["test"] == "test"
    
    def test_mutable(self, exp_factory):
        """
        Changing mutables directly DOES NOT trigger sync!
        """
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)

        group1.shared_data["test"] = []
        group1.shared_data["test"].append("test")

        # assert group2.shared_data["test"] == ["test"]
    
    def test_inherited_data(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        group1 = get_group(exp1, ["a", "b"], ongoing_sessions_ok=True)
        group2 = get_group(exp2, ["a", "b"], ongoing_sessions_ok=True)

        group1.shared_data["test"] = "test"

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        group3 = get_group(exp3, ["a", "b"], ongoing_sessions_ok=True)

        assert group3.shared_data["test"] == "test"