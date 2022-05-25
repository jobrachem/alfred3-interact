import random
import time

import pytest

from alfred3_interact import MatchMaker, NoMatch, SequentialSpec
from alfred3_interact.spec import ParallelSpec


def test_clear(exp):
    """
    Just for clearing the database in case a test breaks down with an error.
    """
    print(exp)


class TestSequential:
    def test_match_random(self, exp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=exp)

        random.seed(1234)
        group = mm.match_random()

        assert group.data.spec_name == "test1"

    def test_match_random2(self, exp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=exp)

        random.seed(123)
        group = mm.match_random()

        assert group.data.spec_name == "test2"

    def test_fill_group(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        spec = SequentialSpec("a", "b", nslots=1, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_random()

        exp1._start()
        exp1.finish()

        mm2 = MatchMaker(spec, exp=exp2)
        group2 = mm2.match_random()

        assert group1 == group2

    def test_match_random_local(self, lexp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=lexp)

        random.seed(123)
        group = mm.match_random()

        assert group.data.spec_name == "test2"

    def test_match_random2_local(self, lexp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=lexp)

        random.seed(12345)
        group = mm.match_random()

        assert group.data.spec_name == "test1"

    def test_minwait_fail(self, exp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=exp)

        random.seed(123)
        with pytest.raises(NoMatch):
            mm.match_random(wait=10)

    def test_minwait_success(self, exp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=exp)

        random.seed(123)
        with pytest.raises(NoMatch):
            mm.match_random(wait=2)

        time.sleep(2)

        random.seed(123)
        group1 = mm.match_random(wait=2)

        assert group1.data.spec_name == "test2"

    def test_nmin_fail(self, exp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=exp)

        random.seed(123)
        with pytest.raises(NoMatch):
            mm.match_random(wait=10, nmin=2)


class TestParallel:
    def test_nmin_success(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        spec = ParallelSpec("a", "b", nslots=5, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)

        random.seed(123)
        with pytest.raises(NoMatch):
            mm1.match_random(wait=10, nmin=2)

        group2 = mm2.match_random(wait=10, nmin=2)

        random.seed(123)
        group1 = mm1.match_random(wait=10, nmin=2)
        assert group1.data.spec_name == "test"
        assert group2.data.spec_name == "test"

    def test_nmin_second(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()
        exp4 = exp_factory()

        spec = ParallelSpec("a", "b", nslots=5, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)
        mm3 = MatchMaker(spec, exp=exp3)
        mm4 = MatchMaker(spec, exp=exp4)

        random.seed(123)
        with pytest.raises(NoMatch):
            mm1.match_random(wait=2, nmin=4)

        with pytest.raises(NoMatch):
            mm2.match_random(wait=2, nmin=4)

        with pytest.raises(NoMatch):
            mm3.match_random(wait=2, nmin=4)

        group4 = mm4.match_random(wait=2, nmin=4)

        random.seed(123)
        group1 = mm1.match_random(nmin=4)
        group2 = mm2.match_random(nmin=4)
        group3 = mm3.match_random(nmin=4)

        assert group1.data.spec_name == "test"
        assert group2.data.spec_name == "test"
        assert group3.data.spec_name == "test"
        assert group4.data.spec_name == "test"

    def test_priority(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        spec = ParallelSpec(
            "a", "b", nslots=5, name="test", shuffle_waiting_members=False
        )

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)
        mm3 = MatchMaker(spec, exp=exp3)

        with pytest.raises(NoMatch):
            mm1.match_random(wait=2)

        with pytest.raises(NoMatch):
            mm2.match_random(wait=2)

        with pytest.raises(NoMatch):
            mm3.match_random(wait=2)

        time.sleep(2)

        group1 = mm1.match_random()

        with pytest.raises(NoMatch):
            mm3.match_random(wait=2)

        group2 = mm2.match_random(wait=2)

        assert group1.data.spec_name == "test"
        assert group2.data.spec_name == "test"

    def test_shuffle(self, exp_factory):
        exp1 = exp_factory("s1")
        exp2 = exp_factory("s2")
        exp3 = exp_factory("s3")

        spec = ParallelSpec(
            "a", "b", nslots=5, name="test", shuffle_waiting_members=True
        )

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)
        mm3 = MatchMaker(spec, exp=exp3)

        random.seed(112342)
        with pytest.raises(NoMatch):
            mm1.match_random(wait=2)

        with pytest.raises(NoMatch):
            mm2.match_random(wait=2)

        with pytest.raises(NoMatch):
            mm3.match_random(wait=2)

        time.sleep(2)

        group1 = mm1.match_random(wait=2)
        group3 = mm3.match_random(wait=2)

        with pytest.raises(NoMatch):
            mm2.match_random(wait=2)

        assert group1.data.spec_name == "test"
        assert group3.data.spec_name == "test"

    def test_three(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        spec = ParallelSpec("a", "b", "c", nslots=5, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)
        mm3 = MatchMaker(spec, exp=exp3)

        with pytest.raises(NoMatch):
            mm1.match_random()

        with pytest.raises(NoMatch):
            mm2.match_random()

        group3 = mm3.match_random()
        group1 = mm1.match_random()
        group2 = mm2.match_random()

        assert group1.spec_name == "test"
        assert group2.spec_name == "test"
        assert group3.spec_name == "test"

        assert not exp1.aborted
        assert not exp2.aborted
        assert not exp3.aborted

    def test_roles(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        spec = ParallelSpec("a", "b", "c", nslots=5, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)
        mm3 = MatchMaker(spec, exp=exp3)

        with pytest.raises(NoMatch):
            mm1.match_random()

        with pytest.raises(NoMatch):
            mm2.match_random()

        group3 = mm3.match_random()
        group1 = mm1.match_random()
        group2 = mm2.match_random()

        assert group1.roles.roles["a"] is not None
        assert group1.roles.roles["b"] is not None
        assert group1.roles.roles["c"] is not None

        assert group1.me.role == next(group3.roles.roles_of([exp1.session_id]))
        assert group2.me.role == next(group3.roles.roles_of([exp2.session_id]))
        assert group3.me.role == next(group3.roles.roles_of([exp3.session_id]))

        assert len({group1.me.role, group2.me.role, group3.me.role}) == 3
