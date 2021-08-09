import time
import pytest
import random
from alfred3_interact import SequentialSpec, MatchMaker, NoMatch
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

        random.seed(123)
        group = mm.match_random()

        assert group.data.spec_name == "test1"
    
    def test_match_random2(self, exp):
        spec1 = SequentialSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec("a2", "b2", nslots=5, name="test2")

        mm = MatchMaker(spec1, spec2, exp=exp)

        random.seed(1234)
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
            mm.match_random(wait= 10, nmin=2)
    
    
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

