import pytest
import alfred3_interact as ali
from alfred3.testutil import get_exp_session, clear_db
from alfred3_interact.testutil import get_group, get_group_groupwise, get_multiple_groups
from alfred3.randomizer import ListRandomizer

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


# class TestSwitch:

#     def test_init_stepwise(self, exp):
#         group = get_group(exp)
#         rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp)

#         assert isinstance(rd, ali.randomizer.StepwiseRandomizer)
    
#     def test_init_groupwise(self, exp_factory):
#         group = get_group_groupwise(exp_factory)
#         rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp)

#         assert isinstance(rd, ListRandomizer)

class TestStepwiseRandomizer:

    def test_get_condition(self, exp):
        group = get_group(exp)
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp, group_type="stepwise")
        condition = rd.get_condition(group)
        assert condition
    
    def test_get_group_condition(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1)
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise")
        c1 = rd.get_condition(group1)
        
        exp1._start()
        exp1.finish()

        group2 = get_group(exp2)

        assert group1 == group2
        
        c2 = rd.get_condition(group2)

        assert c1 == c2
    
    def test_new_condition(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2)

        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise")

        c1 = rd.get_condition(group1)
        c2 = rd.get_condition(group2)

        assert group1 != group2
        assert c1 != c2
    
    def test_full(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, group_type="stepwise")

        c1 = rd1.get_condition(group1)
        
        assert rd1.nopen == 1
        assert rd1.npending == 1
        
        assert rd2.nopen == 1
        assert rd2.npending == 1

        c2 = rd2.get_condition(group2)

        assert rd1.nopen == 0
        assert rd2.nopen == 0

        assert rd1.npending == 2
        assert rd2.npending == 2

    def test_abort(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2)
        group3 = get_group(exp3)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, group_type="stepwise")
        rd3 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp3, group_type="stepwise")

        rd1.get_condition(group1)
        rd2.get_condition(group2)
        rd3.get_condition(group3)

        assert exp3.aborted
    
    def test_inclusive(self, exp_factory):
        """
        3 Different groups, the third groups gets assigned to the same
        condition slot as the first group.
        """
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2)
        group3 = get_group(exp3)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, inclusive=True, group_type="stepwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, inclusive=True, group_type="stepwise")
        rd3 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp3, inclusive=True, group_type="stepwise")

        c1 = rd1.get_condition(group1)
        c2 = rd2.get_condition(group2)
        c3 = rd3.get_condition(group3)

        with rd3.io as data:
            assert rd3._accepts_sessions(data)
        assert c1 != c2 
        assert c1 == c3
        assert not exp3.aborted
    
    def test_inclusive_ten_sessions(self, exp_factory):
        """
        Same as before, but with more members.
        """
        for _ in range(10):
            exp = exp_factory()
            group = get_group(exp)
            rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp, inclusive=True, group_type="stepwise")
            rd.get_condition(group)
        
        with rd.io as data:
            assert rd._accepts_sessions(data)
    
    def test_full_inclusive(self, exp_factory):
        """
        If there are enough finished groups, the inclusive GroupRandomizer
        will not assign any more slots.
        """
        for i in range(5):
            exp = exp_factory()
            group = get_group(exp, ongoing_sessions_ok=True)
            rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp, inclusive=True, group_type="stepwise")
            if i < 4:
                rd.get_condition(group)
                exp._start()
                exp.finish()
            else:
                with rd.io as data:
                    assert not rd._accepts_sessions(data)
                rd.get_condition(group)
                assert exp.aborted

    def test_multiple_finished_in_same_slot(self, exp_factory):
        """
        When there are multiple sessions finished in the same slot,
        this slot should be counted only once.
        """
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        group1 = get_group(exp1)
        group2 = get_group(exp2) 
        group3 = get_group(exp3)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, inclusive=True, group_type="stepwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, inclusive=True, group_type="stepwise")
        rd3 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp3, inclusive=True, group_type="stepwise")

        c1 = rd1.get_condition(group1)
        c2 = rd2.get_condition(group2)
        c3 = rd3.get_condition(group3)

        for exp in (exp1, exp3):
            exp._start()
            exp.finish()
        
        exp4 = exp_factory()
        exp5 = exp_factory()

        group4 = get_group(exp4)
        group5 = get_group(exp5)

        rd4 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp4, inclusive=True, group_type="stepwise")
        rd5 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp5, inclusive=True, group_type="stepwise")

        c4 = rd4.get_condition(group4)
        c5 = rd5.get_condition(group5)

        assert c4 == c5

        for exp in (exp4, exp5):
            exp._start()
            exp.finish()
        
        for rd in (rd1, rd2, rd3, rd4, rd5):
            assert rd.nopen == 0
            assert rd.nfinished == 1
            assert rd.npending == 1
            assert not rd.allfinished 

        exp6 = exp_factory()
        group6 = get_group(exp6)
        rd6 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp6, inclusive=True, group_type="stepwise")
        c6 = rd6.get_condition(group6)

        assert c2 == c6

    def test_group_finished_inclusive(self, exp_factory):
        """
        First group is finished, second group is correctly assigned to
        the next slot.
        """
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()
        exp4 = exp_factory()

        group1 = get_group(exp1)
        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, inclusive=True, group_type="stepwise")
        c1 = rd1.get_condition(group1)
        exp1._start()
        exp1.finish()

        group2 = get_group(exp2)
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, inclusive=True, group_type="stepwise")
        c2 = rd2.get_condition(group2)
        exp2._start()
        exp2.finish()

        assert c1 == c2

        group3 = get_group(exp3)
        group4 = get_group(exp4)
        
        rd3 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp3, inclusive=True, group_type="stepwise")
        rd4 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp4, inclusive=True, group_type="stepwise")

        c3 = rd3.get_condition(group3)
        c4 = rd4.get_condition(group4)

        assert c3 == c4 != c1
    
    def test_session_finished_inclusive(self, exp_factory):
        """
        Only one session of the first group is finished. Thus, the group
        itself is not finished. The next new group will be assigned
        to the same slot.
        """
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()
        exp4 = exp_factory()

        group1 = get_group(exp1)
        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, inclusive=True, group_type="stepwise")
        c1 = rd1.get_condition(group1)
        exp1._start()
        exp1.finish()

        group2 = get_group(exp2)
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, inclusive=True, group_type="stepwise")
        c2 = rd2.get_condition(group2)

        assert c1 == c2

        exp2._start()
        exp2.abort("test")
        exp2._save_data(sync=True)

        group3 = get_group(exp3)
        group4 = get_group(exp4)
        
        rd3 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp3, inclusive=True, group_type="stepwise")
        rd4 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp4, inclusive=True, group_type="stepwise")

        c3 = rd3.get_condition(group3)
        c4 = rd4.get_condition(group4)

        assert group1 == group2 == group3 != group4
        assert c3 == c1 != c4

    def test_inclusive_next_pending_sparsest(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()
        exp4 = exp_factory()
        
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise", inclusive=True)

        group1 = get_group(exp1)
        c1 = rd.get_condition(group1)

        group2 = get_group(exp2)
        c2 = rd.get_condition(group2)

        assert c1 != c2

        group3 = get_group(exp3)
        c3 = rd.get_condition(group3)

        assert c1 == c3
        assert rd.npending == 2

        group4 = get_group(exp4)
        c4 = rd.get_condition(group4)

        assert c4 == c2
    
    def test_inclusive_next_pending_oldest(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()
        
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise", inclusive=True)

        group1 = get_group(exp1)
        c1 = rd.get_condition(group1)

        group2 = get_group(exp2)
        c2 = rd.get_condition(group2)

        assert c1 != c2

        exp1._save_data(sync=True)

        group3 = get_group(exp3)
        c3 = rd.get_condition(group3)

        assert c2 == c3
        assert rd.npending == 2

    def test_different_matchmakers(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        mm1 = ali.MatchMaker("r1", "r2", exp=exp1, id="mm1")
        mm2 = ali.MatchMaker("p1", "p2", "p3", exp=exp2, id="mm2")

        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise")

        group1 = mm1.match_stepwise()
        group2 = mm2.match_stepwise()

        c1 = rd.get_condition(group1)
        c2 = rd.get_condition(group2)

        assert c1 != c2
        assert group1.data.roles != group2.data.roles
        assert rd.npending == 2


class TestStepwiseRandomizerLocal:

    def test_inclusive_next_pending_sparsest(self, lexp_factory):
        exp1 = lexp_factory()
        exp2 = lexp_factory()
        exp3 = lexp_factory()
        exp4 = lexp_factory()
        
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise", inclusive=True)

        group1 = get_group(exp1)
        c1 = rd.get_condition(group1)

        group2 = get_group(exp2)
        c2 = rd.get_condition(group2)

        assert c1 != c2

        group3 = get_group(exp3)
        c3 = rd.get_condition(group3)

        assert c1 == c3
        assert rd.npending == 2

        group4 = get_group(exp4)
        c4 = rd.get_condition(group4)

        assert c4 == c2
    
    def test_inclusive_next_pending_oldest(self, lexp_factory):
        exp1 = lexp_factory()
        exp2 = lexp_factory()
        exp3 = lexp_factory()
        
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="stepwise", inclusive=True)

        group1 = get_group(exp1)
        c1 = rd.get_condition(group1)

        group2 = get_group(exp2)
        c2 = rd.get_condition(group2)

        assert c1 != c2

        exp1._save_data(sync=True)

        group3 = get_group(exp3)
        c3 = rd.get_condition(group3)

        assert c2 == c3
        assert rd.npending == 2








class TestGroupwiseRandomizer:

    def test_get_condition(self, exp_factory):
        group = get_group_groupwise(exp_factory)
        rd = ali.GroupRandomizer.balanced("a", "b", n=1, exp=group.exp, group_type="groupwise")
        condition = rd.get_condition(group)
        assert condition
    
    def test_active_session(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="groupwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, group_type="groupwise")

        c1 = rd1.get_condition(group1)
        c2 = rd2.get_condition(group2)

        assert c1 == c2

        assert rd2.next().condition != c1
    
    def test_aborted_session(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="groupwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, group_type="groupwise")

        c1 = rd1.get_condition(group1)
        c2 = rd2.get_condition(group2)

        assert c1 == c2

        exp1._start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        assert exp1.aborted

        assert rd2.next().condition == c1
    
    def test_finished_group(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="groupwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, group_type="groupwise")

        c1 = rd1.get_condition(group1)
        c2 = rd2.get_condition(group2)

        assert c1 == c2

        exp1._start()
        exp1.finish()
        exp2._start()
        exp2.finish()

        assert rd2.next().condition != c1
    
    def test_expired_session(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        roles = ["a", "b"]

        mm1 = ali.MatchMaker(*roles, exp=exp1)
        mm2 = ali.MatchMaker(*roles, exp=exp2)

        group1, group2 = get_multiple_groups(mm1, mm2)

        rd1 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp1, group_type="groupwise")
        rd2 = ali.GroupRandomizer.balanced("a", "b", n=1, exp=exp2, group_type="groupwise")

        c1 = rd1.get_condition(group1)
        c2 = rd2.get_condition(group2)

        assert c1 == c2

        exp1._start()
        exp1._start_time = exp1._start_time - exp1.session_timeout - 1
        exp1._save_data(sync=True)
        assert exp1.session_expired

        assert rd2.next().condition == c1
