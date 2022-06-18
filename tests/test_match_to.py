import time

import pytest
from alfred3.quota import SessionGroup

from alfred3_interact import MatchMaker, NoMatch, ParallelSpec, SequentialSpec
from alfred3_interact.testutil import get_group


def test_clear(exp):
    """
    Just for clearing the database in case a test breaks down with an error.
    """
    print(exp)


class TestSequential:
    def test_match(self, exp):
        spec = SequentialSpec("a", "b", nslots=5, name="test")
        mm = MatchMaker(spec, exp=exp)
        group = mm.match_to("test")

        assert group.me.role == "a"

    def test_match_local(self, lexp):
        spec = SequentialSpec("a", "b", nslots=5, name="test")
        mm = MatchMaker(spec, exp=lexp)
        group = mm.match_to("test")

        assert group.me.role == "a"

    def test_new_groups(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()
        roles = ["a", "b"]
        group1 = get_group(exp1, roles)
        group2 = get_group(exp2, roles)

        assert group1 != group2

    def test_fill_group(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1)

        exp1._start()
        exp1.finish()

        group2 = get_group(exp2)

        assert group1 == group2
        assert group1.me.data.role != group2.me.data.role

        group1.data = group1.io.load()
        assert group1.full and group2.full

        exp3 = exp_factory()
        group3 = get_group(exp3)

        assert group3 != group2

    def test_fill_aborted_role(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        group1 = get_group(exp1)

        exp1.start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        group2 = get_group(exp2)
        assert group1 == group2
        assert group1.me.data.role == group2.me.data.role
        assert group2.a.data.session_id == exp2.session_id

        assert not group2.full
        assert group2.groupmember_manager.nactive == 1

    def test_fill_expired_role(self, exp_factory):
        exp1 = exp_factory("s1", 0.1)
        exp2 = exp_factory("s2")

        group1 = get_group(exp1)

        exp1.start()
        time.sleep(0.2)
        assert not SessionGroup(["s1"]).pending(exp1)

        group2 = get_group(exp2, nslots=1)
        assert group1 == group2
        assert group1.me.data.role == group2.me.data.role
        assert group2.a.data.session_id == exp2.session_id

        assert not group2.full
        assert group2.groupmember_manager.nactive == 1

    def test_you(self, exp_factory):
        exp1 = exp_factory()
        group1 = get_group(exp1)

        assert group1.you is None


class TestSequentialLocal:
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

        group1.data = group1.io.load()
        assert group1.full and group2.full

        exp3 = lexp_factory()
        group3 = get_group(exp3)

        assert group3 != group2

    def test_fill_aborted_role(self, lexp_factory):
        exp1 = lexp_factory("s1")
        exp2 = lexp_factory("s2")

        group1 = get_group(exp1)

        exp1.start()
        exp1.abort("test")
        exp1._save_data(sync=True)

        group2 = get_group(exp2)
        assert group1 == group2
        assert group1.me.data.role == group2.me.data.role
        assert group2.a.data.session_id == exp2.session_id

        assert not group2.full
        assert group2.groupmember_manager.nactive == 1

    def test_fill_expired_role(self, lexp_factory):
        exp1 = lexp_factory("s1", 0.1)
        exp2 = lexp_factory("s2")

        group1 = get_group(exp1)

        exp1.start()
        time.sleep(0.2)
        assert not SessionGroup(["s1"]).pending(exp1)

        group2 = get_group(exp2, nslots=1)
        assert group1 == group2
        assert group1.me.data.role == group2.me.data.role
        assert group2.a.data.session_id == exp2.session_id

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
        exp1 = lexp_factory()
        exp2 = lexp_factory()

        group1 = get_group(exp1, ["b", "a"])
        group2 = get_group(exp2, ["b", "a"])

        assert group1.me.role == "b"
        assert group2.me.role == "b"


class TestSequentialOngoingOk:
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
        get_group(exp2, ongoing_sessions_ok=True)

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
        get_group(exp2, ongoing_sessions_ok=True)

        exp1._start()
        exp1._start_time -= 10
        exp1._save_data(sync=True)
        assert exp1.session_expired

        group1.data = group1.io.load()
        assert group1.groupmember_manager.nactive == 1

        exp3 = exp_factory()
        exp3._session_timeout = 0.1
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group1 == group3
        assert group1.me.data.role == group3.me.data.role

    def test_second_role_aborted(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        get_group(exp1, ongoing_sessions_ok=True)
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

        get_group(exp1, ongoing_sessions_ok=True)
        group2 = get_group(exp2, ongoing_sessions_ok=True)

        exp2._start()
        exp2._start_time -= 10
        exp2._save_data(sync=True)
        assert exp2.session_expired

        group2.data = group2.io.load()
        assert group2.groupmember_manager.nactive == 1

        exp3 = exp_factory()
        exp3._session_timeout = 0.1
        group3 = get_group(exp3, ongoing_sessions_ok=True)

        assert group2 == group3
        assert group2.me.data.role == group3.me.data.role


class TestParallel:
    def test_match_raise(self, exp):
        spec = ParallelSpec("a", "b", nslots=5, name="test")
        mm = MatchMaker(spec, exp=exp)
        with pytest.raises(NoMatch):
            mm.match_to("test")

    def test_match_success(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        spec = ParallelSpec("a", "b", nslots=5, name="test")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)

        with pytest.raises(NoMatch):
            mm1.match_to("test")

        group2 = mm2.match_to("test")
        group1 = mm1.match_to("test")

        assert group1.data.group_id == group2.data.group_id

    def test_ping_expired(self, exp_factory):
        exp1 = exp_factory()
        exp2 = exp_factory()

        spec = ParallelSpec("a", "b", nslots=5, name="test")

        mm1 = MatchMaker(spec, exp=exp1, ping_timeout=1)
        mm2 = MatchMaker(spec, exp=exp2, ping_timeout=1)

        with pytest.raises(NoMatch):
            mm1.match_to("test")

        time.sleep(1)

        with pytest.raises(NoMatch):
            mm2.match_to("test")


class TestParallelQuota:
    def test_full(self, exp_factory):
        """
        Fill the matchmaker and verify that subsequent sessions
        get aborted.
        """
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")

        spec = ParallelSpec("a", "b", nslots=1, name="test1")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)

        with pytest.raises(NoMatch):
            mm1.match_to("test1")

        mm2.match_to("test1")
        mm1.match_to("test1")

        assert mm1.quota.nopen == 0
        assert mm2.quota.nopen == 0

        exp3 = exp_factory("__exp3")
        exp4 = exp_factory("__exp4")

        mm3 = MatchMaker(spec, exp=exp3)
        mm4 = MatchMaker(spec, exp=exp4)

        with pytest.raises(NoMatch):
            mm3.match_to("test1")

        mm4.match_to("test1")
        mm3.match_to("test1")

        assert exp3.aborted and exp3._aborted_because == "matchmaker_full"
        assert exp4.aborted and exp4._aborted_because == "matchmaker_full"

    def test_reopen_slots(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")

        spec = ParallelSpec("a", "b", nslots=1, name="test1")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)

        with pytest.raises(NoMatch):
            mm1.match_to("test1")

        mm2.match_to("test1")
        mm1.match_to("test1")

        assert mm1.quota.nopen == 0
        assert mm2.quota.nopen == 0

        exp1.abort("test")
        exp2.abort("test")
        exp1._save_data()
        exp2._save_data(sync=True)

        assert mm1.quota.nopen == 1
        assert mm2.quota.nopen == 1

    def test_one_member_aborts(self, exp_factory):
        exp1 = exp_factory("__exp1")
        exp2 = exp_factory("__exp2")

        spec = ParallelSpec("a", "b", nslots=1, name="test1")

        mm1 = MatchMaker(spec, exp=exp1)
        mm2 = MatchMaker(spec, exp=exp2)

        with pytest.raises(NoMatch):
            mm1.match_to("test1")

        mm2.match_to("test1")
        mm1.match_to("test1")

        assert mm1.quota.nopen == 0
        assert mm2.quota.nopen == 0

        exp2.abort("test")
        exp2._save_data(sync=True)

        assert mm1.quota.nopen == 1
        assert mm2.quota.nopen == 1
