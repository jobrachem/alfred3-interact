import pytest
import alfred3_interact as ali
from alfred3.testutil import get_exp_session, clear_db
from alfred3_interact.testutil import get_group, get_group_groupwise, get_multiple_groups
from alfred3.randomizer import ListRandomizer
from alfred3_interact.quota import GroupQuota

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
def exp_factory(tmp_path):
    def expf():
        script = "tests/res/script-hello_world.py"
        secrets = "tests/res/secrets-default.conf"
        exp = get_exp_session(tmp_path, script_path=script, secrets_path=secrets)
        return exp
    
    yield expf

    clear_db()

def test_clear(exp):
    """
    Just for clearing the database in case a test breaks down with an error.
    """
    print(exp)


class TestCountStepwise:

    def test_before_matching(self, exp):
        quota = GroupQuota(n=10, exp=exp, group_type="stepwise")

        assert quota.nopen == 10
        assert quota.nfinished == 0
        assert quota.npending == 0
        assert quota.nslots == 10
    

    def test_count(self, exp):
        group = get_group(exp)
        quota = GroupQuota(n=10, exp=exp, group_type="stepwise")
        quota.count(group)

        assert quota.nopen == 9
        assert quota.nfinished == 0
        assert quota.npending == 1
        assert quota.nslots == 10
    
    def test_finished(self, exp_factory):
        
        exp1 = exp_factory()
        group1 = get_group(exp1)
        exp1._start()
        exp1.finish()
        quota1 = GroupQuota(n=10, exp=exp1, group_type="stepwise")
        quota1.count(group1)

        exp2 = exp_factory()
        group2 = get_group(exp2)
        exp2._start()
        exp2.finish()

        assert group1 == group2

        quota2 = GroupQuota(n=10, exp=exp2, group_type="stepwise")
        quota2.count(group2)
        
        for quota in (quota1, quota2):
            assert quota.nopen == 9
            assert quota.nfinished == 1
            assert quota.npending == 0
            assert quota.nslots == 10


class TestCountGroupwise:

    def test_count(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        assert group1 == group2
        
        quota1 = GroupQuota(n=10, exp=exp1, group_type="groupwise")
        quota1.count(group1)

        quota2 = GroupQuota(n=10, exp=exp2, group_type="groupwise")
        quota2.count(group2)

        for quota in (quota1, quota2):
            assert quota.nopen == 9
            assert quota.nfinished == 0
            assert quota.npending == 1
            assert quota.nslots == 10
    
    def test_finished(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        assert group1 == group2
        
        quota1 = GroupQuota(n=10, exp=exp1, group_type="groupwise")
        quota1.count(group1)

        quota2 = GroupQuota(n=10, exp=exp2, group_type="groupwise")
        quota2.count(group2)

        for exp in (exp1, exp2):
            exp._start()
            exp.finish()

        for quota in (quota1, quota2):
            assert quota.nopen == 9
            assert quota.nfinished == 1
            assert quota.npending == 0
            assert quota.nslots == 10
    
    def test_pending(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        assert group1 == group2
        
        quota1 = GroupQuota(n=10, exp=exp1, group_type="groupwise")
        quota1.count(group1)

        quota2 = GroupQuota(n=10, exp=exp2, group_type="groupwise")
        quota2.count(group2)

        exp1._start()
        exp1.finish()

        for quota in (quota1, quota2):
            assert quota.nopen == 9
            assert quota.nfinished == 0
            assert quota.npending == 1
            assert quota.nslots == 10