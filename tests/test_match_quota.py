import time

import pytest

from alfred3_interact import MatchMaker, NoMatch, ParallelSpec, SequentialSpec
from alfred3_interact.testutil import get_group


def test_clear(exp):
    """
    Just for clearing the database in case a test breaks down with an error.
    """
    print(exp)


class TestQuotaSequential:
    def test_before_match(self, exp):
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        spec._init_quota(exp)

        assert spec.quota.nopen == 1
        assert spec.quota.nfinished == 0
        assert spec.quota.npending == 0

    def test_one_spec(self, exp):
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm = MatchMaker(spec, exp=exp)
        mm.match_to("test")

        assert mm.quota.nfinished == 0
        assert mm.quota.nopen == 0
        assert mm.quota.npending == 1

    def test_one_spec_inclusive(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        spec = SequentialSpec("a", "b", nslots=1, name="test", inclusive=True)
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        assert mm1.quota.nfinished == 0
        assert mm1.quota.nopen == 0
        assert mm1.quota.npending == 1

        mm2 = MatchMaker(spec, exp=exp2)
        group2 = mm2.match_to("test")

        assert group1 != group2

    def test_one_spec_inclusive_slot_order(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        exp3 = exp_factory()

        spec = SequentialSpec("a", "b", nslots=2, name="test", inclusive=True)
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        assert mm1.quota.nfinished == 0
        assert mm1.quota.nopen == 1
        assert mm1.quota.npending == 1

        mm2 = MatchMaker(spec, exp=exp2)
        group2 = mm2.match_to("test")

        assert mm2.quota.nfinished == 0
        assert mm2.quota.nopen == 0
        assert mm2.quota.npending == 2

        mm3 = MatchMaker(spec, exp=exp3)
        group3 = mm3.match_to("test")

        assert group1 != group2 != group3

    def test_one_spec_inclusive_slot_order_local(self, lexp_factory):
        exp1 = lexp_factory()
        exp2 = lexp_factory()
        exp3 = lexp_factory()

        spec = SequentialSpec("a", "b", nslots=2, name="test", inclusive=True)
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        assert mm1.quota.nfinished == 0
        assert mm1.quota.nopen == 1
        assert mm1.quota.npending == 1

        mm2 = MatchMaker(spec, exp=exp2)
        group2 = mm2.match_to("test")

        assert mm2.quota.nfinished == 0
        assert mm2.quota.nopen == 0
        assert mm2.quota.npending == 2

        mm3 = MatchMaker(spec, exp=exp3)
        group3 = mm3.match_to("test")

        assert group1 != group2 != group3

    def test_full(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        spec = SequentialSpec("a", "b", nslots=1, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        mm1.match_to("test")

        mm2 = MatchMaker(spec, exp=exp2)
        mm2.match_to("test")

        assert exp2.aborted

    def test_full2(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        mm2 = MatchMaker(spec, exp=exp2)
        mm2.match_to("test")

        assert exp2.aborted

        exp1._start()
        exp1.finish()

        exp3 = exp_factory()

        mm3 = MatchMaker(spec, exp=exp3)
        group3 = mm3.match_to("test")

        assert not exp3.aborted
        assert group1 == group3

    def test_finished(self, exp_factory):
        exp1 = exp_factory()
        group1 = get_group(exp1, nslots=2)
        exp1._start()
        exp1.finish()

        exp2 = exp_factory()
        group2 = get_group(exp2, nslots=2)
        exp2._start()
        exp2.finish()
        assert group1 == group2

        assert group1.mm.quota.nopen == 1
        assert group1.mm.quota.nfinished == 1
        assert group1.mm.quota.npending == 0

    def test_pending(self, exp_factory):
        exp1 = exp_factory()
        group1 = get_group(exp1, nslots=2)
        exp1._start()
        exp1.finish()

        exp2 = exp_factory()
        group2 = get_group(exp2, nslots=2)
        assert group1 == group2

        assert group1.mm.quota.nopen == 1
        assert group1.mm.quota.nfinished == 0
        assert group1.mm.quota.npending == 1

    def test_abort(self, exp_factory):
        exp1 = exp_factory()
        group1 = get_group(exp1, nslots=1)
        exp1.abort("test")
        exp1._save_data(sync=True)

        assert group1.mm.quota.nopen == 0
        assert group1.mm.quota.nfinished == 0
        assert group1.mm.quota.npending == 1

        exp2 = exp_factory()
        group2 = get_group(exp2, nslots=1)
        assert group1 == group2
        assert not exp2.aborted

    def test_session_timeout(self, exp_factory):
        exp1 = exp_factory("s1")
        exp2 = exp_factory("s2")
        exp3 = exp_factory("s3")

        exp1._start()
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        mm2 = MatchMaker(spec, exp=exp2)
        mm2.match_to("test")

        assert exp2.aborted

        assert group1.mm.quota.nopen == 0
        assert group1.mm.quota.npending == 1

        time.sleep(0.1)
        exp1._session_timeout = 0.1

        assert exp1.session_expired
        exp1.forward()
        exp1._save_data(sync=True)
        assert exp1.aborted

        mm3 = MatchMaker(spec, exp=exp3)
        group3 = mm3.match_to("test")

        assert group3.me.role == "a"
        assert not exp3.aborted

    def test_session_timeout_without_abort(self, exp_factory):
        """
        Here, the expired session is never aborted explicitly, only implicitly.
        """
        exp1 = exp_factory(sid="s1", timeout=1)
        exp1.start()
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        assert group1.me.role == "a"
        assert group1.mm.quota.nopen == 0
        assert group1.mm.quota.npending == 1

        time.sleep(1)
        assert exp1.session_expired
        assert not exp1.aborted

        exp2 = exp_factory(sid="s2")
        exp2.start()
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm2 = MatchMaker(spec, exp=exp2)
        group2 = mm2.match_to("test")

        assert group2.me.role == "a"
        assert not exp2.aborted

        exp3 = exp_factory(sid="s3")
        exp3.start()
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm3 = MatchMaker(spec, exp=exp3)
        mm3.match_to("test")
        assert exp3.aborted


class TestQuotaSequentialLocal:
    def test_one_spec(self, lexp):
        spec = SequentialSpec("a", "b", nslots=1, name="test", inclusive=True)
        mm = MatchMaker(spec, exp=lexp)
        mm.match_to("test")

        assert mm.quota.nfinished == 0
        assert mm.quota.nopen == 0
        assert mm.quota.npending == 1

    def test_session_timeout(self, lexp_factory):
        exp1 = lexp_factory("s1")
        exp2 = lexp_factory("s2")
        exp3 = lexp_factory("s3")

        exp1._start()
        spec = SequentialSpec("a", "b", nslots=1, name="test")
        mm1 = MatchMaker(spec, exp=exp1)
        group1 = mm1.match_to("test")

        mm2 = MatchMaker(spec, exp=exp2)
        mm2.match_to("test")

        assert exp2.aborted

        assert group1.mm.quota.nopen == 0
        assert group1.mm.quota.npending == 1

        time.sleep(0.1)
        exp1._session_timeout = 0.1

        assert exp1.session_expired
        exp1.forward()
        exp1._save_data(sync=True)
        assert exp1.aborted

        mm3 = MatchMaker(spec, exp=exp3)
        group3 = mm3.match_to("test")

        assert group3.me.role == "a"
        assert not exp3.aborted
        assert group3.group_id == group1.group_id


class TestQuotaParallel:
    def test_multiple_specs(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        exp3 = exp_factory("__exp3")

        spec1 = ParallelSpec("a", "b", nslots=5, name="test1")
        spec2 = ParallelSpec("a", "b", "c", nslots=5, name="test2")

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)
        mm3 = MatchMaker(spec1, spec2, exp=exp3)

        with pytest.raises(NoMatch):
            mm1.match_chain(test2=10, test1=None)

        with pytest.raises(NoMatch):
            mm2.match_chain(test2=10, test1=None)

        mm3.match_chain(test2=10, test1=None)
        mm2.match_chain(test2=10, test1=None)
        mm1.match_chain(test2=10, test1=None)

        assert spec2.quota.nopen == 4
        assert spec2.quota.nfinished == 0
        assert spec2.quota.npending == 1

        assert spec1.quota.nopen == 5
        assert spec1.quota.nfinished == 0
        assert spec1.quota.npending == 0

        for mm in [mm1, mm2, mm3]:
            assert mm.quota.nopen == 9
            assert mm.quota.nfinished == 0
            assert mm.quota.npending == 1

    def test_multiple_specs2(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        exp3 = exp_factory("__exp3")

        spec1 = ParallelSpec("a", nslots=1, name="test1")
        spec2 = ParallelSpec("a", "b", nslots=5, name="test2")

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)
        mm3 = MatchMaker(spec1, spec2, exp=exp3)

        group1 = mm1.match_random()
        assert group1.data.spec_name == "test1"

        with pytest.raises(NoMatch):
            group2 = mm2.match_random()

        group3 = mm3.match_random()
        group2 = mm2.match_random()

        assert group2.data.spec_name == "test2"
        assert group3.data.spec_name == "test2"

        assert spec2.quota.nopen == 4
        assert spec2.quota.nfinished == 0
        assert spec2.quota.npending == 1

        assert spec1.quota.nopen == 0
        assert spec1.quota.nfinished == 0
        assert spec1.quota.npending == 1

        for mm in [mm1, mm2, mm3]:
            assert mm.quota.nopen == 4
            assert mm.quota.nfinished == 0
            assert mm.quota.npending == 2
