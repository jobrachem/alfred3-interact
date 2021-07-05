import time
import pytest
import alfred3_interact as ali
from alfred3.testutil import get_exp_session, clear_db
from alfred3_interact.match import MatchMaker
from alfred3_interact.testutil import get_group

from dotenv import load_dotenv
load_dotenv()

# TODO
"""
MANY MATCHMAKERS!
    Wählt Matchmaker aus
    Gibt Condition


BIG Refactoring possibly sensible

Goals:
    1. Get Quota before MM initialization
    2. Do not require "group_type" argument for Randomizer

Status Quo:

    MatchMaker(*roles, exp)
        .match_stepwise()
        .match_groupwise()

    Quota(n, exp, group_type)
        .nopen, etc.
        .count(group)
    
    GroupRandomizer(*conditions, exp, group_type)
        .get_condition(group)

1. Take stepwise and groupwise completely apart

    individual methods match_stepwise and match_groupwise can be renamed
    to match()

    StepwiseQuota(n, exp)
        .nopen, etc.
        .count(group)
    
    StepwiseMatchMaker(*roles, exp, quota)
        .match()

    StepwiseRandomizer(*conditions, exp)
        .get_condition(group)
    

    GroupwiseMatchMaker(MatchMaker)
    GroupwiseQuota
    GroupwiseRandomizer

2. Take Stepwise and Groupwise apart, use them to inform Quota and Randomizer

    StepwiseMatchMaker(MatchMaker)
    GroupwiseMatchMaker(MatchMaker)

    Quota(n, mm)
    GroupRandomizer(("condition", 5), mm)

    PROBLEM: Quota needs mm on init, cant be passed as an argument
        SOL: Add after init as attribute
    
    mm = GroupwiseMatchMaker("a", "b", exp=exp)
    mm.quota = Quota(10, mm)

Another note: Separate Admin from MatchMaker

MatchMakerAdmin
    added to admin section
    same for stepwise and groupwise?
    connected to matchmaker via id

Admin section triggered by ?admin=true
    JumpList für Pages
    admin pw ist parameter an Experiment Klasse
    
    Exp weiß bei init, dass es im admin mode ist, added dann NUR die
    admin section

    if exp.admin:
        exp.admin += MatchMakerAdmin(id="matchmaker")

"""

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


class TestStepwiseStrict:

    def test_new_groups(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2)

        assert group1 != group2
    
    def test_quota(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        mm1 = MatchMaker("a", "b", exp=exp1)
        mm2 = MatchMaker("a", "b", exp=exp2)

        mm1.match_stepwise()
        mm1.count_group(max_groups=1)

        mm2.match_stepwise()
        mm2.count_group(max_groups=1)

        assert exp2.aborted
    
    def test_quota_strict(self, exp_factory):
        # TODO
        """
        Quota darf ihre ID nach init nicht mehr verändern.
        Wie ordne ich eine Quota am besten einem MatchMaker zu?
        """
        exp1 = exp_factory()
        exp2 = exp_factory()

        quota1 = ali.GroupQuota(n=1, exp=exp1, group_type="stepwise")
        quota2 = ali.GroupQuota(n=1, exp=exp2, group_type="stepwise")

        mm1 = MatchMaker("a", "b", exp=exp1, quota=quota1)
        mm2 = MatchMaker("a", "b", exp=exp2, quota=quota2)

        mm1.match_stepwise()
        mm2.match_stepwise()

        assert exp2.aborted
    
    def test_quota_ongoing_sessions_ok_group_finished(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        mm1 = MatchMaker("a", "b", exp=exp1)
        mm2 = MatchMaker("a", "b", exp=exp2)
        mm3 = MatchMaker("a", "b", exp=exp3)

        group1 = mm1.match_stepwise()
        mm1.count_group(max_groups=1, ongoing_sessions_ok=True)

        exp1._start()
        exp1.finish()

        group2 = mm2.match_stepwise()

        exp2._start()
        exp2.finish()

        assert group1 == group2

        mm3.match_stepwise()
        mm3.count_group(max_groups=1, ongoing_sessions_ok=True)

        assert exp3.aborted

    def test_fill_group(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        
        group1 = get_group(exp1)

        exp1._start()
        exp1.finish()

        group2 = get_group(exp2)

        assert group1 == group2
        assert group1.me.data.role != group2.me.data.role
        
        group1.load()
        assert group1.full and group2.full

        exp3 = exp_factory()
        group3 = get_group(exp3)

        assert group3 != group2
    
    def test_fill_aborted_role(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        
        group1 = get_group(exp1)

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        group2 = get_group(exp2)
        assert group1 == group2
        assert group1.me.data.role == group2.me.data.role

        assert not group2.full
        assert group2.groupmember_manager.nactive == 1
    
    def test_you(self, exp_factory):
        exp1 = exp_factory()
        group1 = get_group(exp1)

        assert group1.you is None


class TestStepwiseOngoingSessionsOk:
    
    def test_new_groups(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ongoing_sessions_ok=True)
        group2 = get_group(exp2, ongoing_sessions_ok=True)

        assert group1 == group2
        assert group1.me.data.role != group2.me.data.role

        exp3 = exp_factory()
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group3 != group2
    
    def test_first_role_aborted(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ongoing_sessions_ok=True)
        group2 = get_group(exp2, ongoing_sessions_ok=True)

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        exp3 = exp_factory()
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group1 == group3
        assert group1.me.data.role == group3.me.data.role

    def test_first_role_expired(self, exp_factory):
        exp1 = exp_factory()
        exp1._session_timeout = 0.1
        exp2 = exp_factory()

        group1 = get_group(exp1, ongoing_sessions_ok=True)
        group2 = get_group(exp2, ongoing_sessions_ok=True)

        exp1._start()
        exp1._start_time -= 10
        exp1._save_data(sync=True)
        assert exp1.session_expired
        
        group1.load()
        assert group1.groupmember_manager.nactive == 1

        exp3 = exp_factory()
        exp3._session_timeout = 0.1
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group1 == group3
        assert group1.me.data.role == group3.me.data.role
    
    def test_second_role_aborted(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1, ongoing_sessions_ok=True)
        group2 = get_group(exp2, ongoing_sessions_ok=True)

        exp2._start()
        exp2.abort("test")
        exp2._save_data(sync=True)

        exp3 = exp_factory()
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group2 == group3
        assert group2.me.data.role == group3.me.data.role

    def test_second_role_expired(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp2._session_timeout = 0.1

        group1 = get_group(exp1, ongoing_sessions_ok=True)
        group2 = get_group(exp2, ongoing_sessions_ok=True)

        exp2._start()
        exp2._start_time -= 10
        exp2._save_data(sync=True)
        assert exp2.session_expired
        
        group2.load()
        assert group2.groupmember_manager.nactive == 1

        exp3 = exp_factory()
        exp3._session_timeout = 0.1
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group2 == group3
        assert group2.me.data.role == group3.me.data.role

    def test_three_roles(self, exp_factory):
        # TODO: Fill
        pass

class TestStepwiseLocal:
    
    def test_new_groups(self, lexp_factory):
        exp1 = lexp_factory()
        exp2 = lexp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2)

        assert group1 != group2

    def test_fill_group(self, lexp_factory):
        exp1 = lexp_factory()
        exp2 = lexp_factory()
        
        group1 = get_group(exp1)

        exp1._start()
        exp1.finish()

        group2 = get_group(exp2)

        assert group1 == group2
        assert group1.me.data.role != group2.me.data.role
        
        group1.load()
        assert group1.full and group2.full

        exp3 = lexp_factory()
        group3 = get_group(exp3)

        assert group3 != group2    

    def test_fill_aborted_role(self, lexp_factory):
        exp1 = lexp_factory()
        exp2 = lexp_factory()
        
        group1 = get_group(exp1)

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        group2 = get_group(exp2)
        assert group1 == group2
        assert group1.me.data.role == group2.me.data.role

        assert not group2.full
        assert group2.groupmember_manager.nactive == 1
    
    def test_you(self, lexp_factory):
        exp1 = lexp_factory()
        group1 = get_group(exp1)

        assert group1.you is None
    
    def test_ongoing_sessions_ok(self, lexp):
        with pytest.raises(ValueError):
            get_group(lexp, ongoing_sessions_ok=True)
        
    
    def test_role_order(self, lexp_factory):
        pass


class TestGrouwise:

    def test_match(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        mm1 = ali.MatchMaker("a", "b", exp=exp1)
        mm2 = ali.MatchMaker("a", "b", exp=exp2)

        with pytest.raises(ali.NoMatch):
            group1 = mm1.match_groupwise()
        
        group2 = mm2.match_groupwise()
        assert group2 is not None

        group1 = mm1.match_groupwise()

        assert group1 == group2
        assert group1.me.data.role != group2.me.data.role
        assert group1.full
        assert group2.full
    
    def test_ping_expired(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        mm1 = ali.MatchMaker("a", "b", exp=exp1)
        mm2 = ali.MatchMaker("a", "b", exp=exp2)

        with pytest.raises(ali.NoMatch):
            group1 = mm1.match_groupwise()
        
        time.sleep(1)

        with pytest.raises(ali.NoMatch):
            group2 = mm2.match_groupwise(0.5)


class TestCompatibility:

    def test_ongoing_sessions_ok(self):
        pass