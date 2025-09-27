import time

import pytest

from alfred3_interact import MatchMaker, NoMatch, ParallelSpec, SequentialSpec


class TestChainMatch:
    def test_chain_first(self, exp_factory):
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

        group3 = mm3.match_chain(test2=10, test1=None)
        group2 = mm2.match_chain(test2=10, test1=None)
        group1 = mm1.match_chain(test2=10, test1=None)

        assert group3.data.spec_name == "test2"
        assert group2.data.spec_name == "test2"
        assert group1.data.spec_name == "test2"

    def test_chain_second(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")

        spec1 = ParallelSpec("a", "b", nslots=5, name="test1")
        spec2 = ParallelSpec("a", "b", "c", nslots=5, name="test2")

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)

        with pytest.raises(NoMatch):
            mm1.match_chain(test2=3, test1=0)

        with pytest.raises(NoMatch):
            mm2.match_chain(test2=3, test1=0)

        time.sleep(3)

        group2 = mm2.match_chain(test2=3, test1=0)
        group1 = mm1.match_chain(test2=3, test1=0)

        assert group2.data.spec_name == "test1"
        assert group1.data.spec_name == "test1"

    def test_chain_first_full(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        exp3 = exp_factory("__exp3")
        exp4 = exp_factory("__exp4")

        spec1 = ParallelSpec("a", "b", nslots=5, name="test1")
        spec2 = ParallelSpec("a", "b", nslots=1, name="test2")

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)
        mm3 = MatchMaker(spec1, spec2, exp=exp3)
        mm4 = MatchMaker(spec1, spec2, exp=exp4)

        with pytest.raises(NoMatch):
            mm1.match_chain(test2=20, test1=0)

        group2 = mm2.match_chain(test2=20, test1=0)
        group1 = mm1.match_chain(test2=20, test1=0)

        assert group2.data.spec_name == "test2"
        assert group1.data.spec_name == "test2"

        with pytest.raises(NoMatch):
            mm3.match_chain(test2=20, test1=0)

        group4 = mm4.match_chain(test2=20, test1=0)
        group3 = mm3.match_chain(test2=20, test1=0)

        assert group3.data.spec_name == "test1"
        assert group4.data.spec_name == "test1"

    def test_chain_first_full_sequential(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        exp3 = exp_factory("__exp3")
        exp4 = exp_factory("__exp4")

        spec1 = ParallelSpec("a", "b", nslots=5, name="test1")
        spec2 = SequentialSpec(
            "a", "b", nslots=1, name="test2", ongoing_sessions_ok=True
        )

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)
        mm3 = MatchMaker(spec1, spec2, exp=exp3)
        mm4 = MatchMaker(spec1, spec2, exp=exp4)

        group1 = mm1.match_chain(test2=20, test1=0)
        group2 = mm2.match_chain(test2=20, test1=0)

        assert group2.data.spec_name == "test2"
        assert group1.data.spec_name == "test2"

        with pytest.raises(NoMatch):
            mm3.match_chain(test2=20, test1=0)

        group4 = mm4.match_chain(test2=20, test1=0)
        group3 = mm3.match_chain(test2=20, test1=0)

        assert group3.data.spec_name == "test1"
        assert group4.data.spec_name == "test1"

    def test_exclude_previous(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        exp3 = exp_factory("__exp3")

        spec1 = ParallelSpec("a", "b", nslots=5, name="test1")
        spec2 = ParallelSpec("a", "b", "c", nslots=5, name="test2")

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)
        mm3 = MatchMaker(spec1, spec2, exp=exp3)

        with pytest.raises(NoMatch):
            mm1.match_chain(test2=3, test1=0)

        with pytest.raises(NoMatch):
            mm2.match_chain(test2=3, test1=0)

        time.sleep(3)

        group2 = mm2.match_chain(test2=3, test1=0, include_previous=False)
        group1 = mm1.match_chain(test2=3, test1=0, include_previous=False)

        assert group1.data.spec_name == "test1"
        assert group2.data.spec_name == "test1"

        with pytest.raises(NoMatch):
            mm3.match_chain(test2=3, test1=0, include_previous=False)

    def test_roles(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")
        exp3 = exp_factory("__exp3")

        spec1 = ParallelSpec("a", "b", nslots=5, name="test1")
        spec2 = ParallelSpec("a", "b", "c", nslots=5, name="test2")

        mm1 = MatchMaker(spec1, spec2, exp=exp1)
        mm2 = MatchMaker(spec1, spec2, exp=exp2)
        mm3 = MatchMaker(spec1, spec2, exp=exp3)

        with pytest.raises(NoMatch):
            mm1.match_chain(test2=10, test1=0)

        with pytest.raises(NoMatch):
            mm2.match_chain(test2=10, test1=0)

        group3 = mm3.match_chain(test2=10, test1=0)
        group2 = mm2.match_chain(test2=10, test1=0)
        group1 = mm1.match_chain(test2=10, test1=0)

        assert group1.data.spec_name == "test2"
        assert group2.data.spec_name == "test2"
        assert group3.data.spec_name == "test2"

        assert group1.roles.roles["a"] is not None
        assert group1.roles.roles["b"] is not None
        assert group1.roles.roles["c"] is not None

        assert group1.me.role == next(group3.roles.roles_of([exp1.session_id]))
        assert group2.me.role == next(group3.roles.roles_of([exp2.session_id]))
        assert group3.me.role == next(group3.roles.roles_of([exp3.session_id]))

        assert len({group1.me.role, group2.me.role, group3.me.role}) == 3
