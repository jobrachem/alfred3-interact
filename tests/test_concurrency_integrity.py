"""Database write regressions using private synthetic databases on local MongoDB."""

import os
from configparser import ConfigParser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pymongo
import pytest

from alfred3_interact.group import GroupData, GroupIO, SharedGroupData
from alfred3_interact.match import MatchMakerIO
from alfred3_interact.member import GroupMemberData, GroupMemberIO


@pytest.fixture
def concurrency_db():
    host = os.getenv("MONGODB_HOST", "localhost")
    if host not in ("localhost", "127.0.0.1", "mongo"):
        pytest.fail("Concurrency regressions require a local synthetic MongoDB")
    client = pymongo.MongoClient(
        host,
        int(os.getenv("MONGODB_PORT", "27017")),
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
        socketTimeoutMS=5000,
    )
    name = "test_interact_concurrency_" + uuid4().hex
    try:
        client.admin.command("ping")
        yield client[name]
    finally:
        client.drop_database(name)
        client.close()


def make_mm(tmp_path, db=None, sid="owner"):
    config = ConfigParser()
    config.read_dict({"local_saving_agent": {"use": "true"}})
    secrets = ConfigParser()
    secrets.read_dict({"mongo_saving_agent": {"use": str(db is not None)}})
    exp = SimpleNamespace(
        config=config,
        secrets=secrets,
        exp_id="synthetic-concurrency",
        version="1",
        session_id=sid,
        db_misc=None if db is None else db.misc,
        subpath=lambda path: tmp_path / path,
        log=SimpleNamespace(debug=Mock(), warning=Mock()),
    )
    mm = SimpleNamespace(
        exp=exp,
        exp_version="1",
        matchmaker_id="shared",
        _DATA_TYPE="match_maker_data",
        _active=True,
        ping_timeout=15,
    )
    mm.io = MatchMakerIO(mm)
    mm.io.load()
    return mm


def make_group(mm):
    group = SimpleNamespace(
        mm=mm,
        exp=mm.exp,
        data=GroupData(
            mm.exp.exp_id,
            "1",
            "shared",
            {"a": None, "b": None},
            "parallel_group",
            "shared",
            group_id="synthetic-group",
        ),
    )
    group.io = GroupIO(group)
    group.shared_data = SharedGroupData(group=group)
    group.data.shared_data = group.shared_data.data
    group.io.insert()
    return group


def make_member(mm, **values):
    member = SimpleNamespace(
        mm=mm,
        exp=mm.exp,
        data=GroupMemberData(mm.exp.exp_id, "member", **values),
    )
    member.io = GroupMemberIO(member)
    return member


def test_independent_shared_keys_survive_stale_views(
    tmp_path, concurrency_db, monkeypatch
):
    mm = make_mm(tmp_path, concurrency_db)
    left, right = make_group(mm), make_group(mm)
    left.shared_data._fetch()
    right.shared_data._fetch()
    # Both real fetches have completed before either final user-key write.
    monkeypatch.setattr(left.shared_data, "_fetch", lambda: None)
    monkeypatch.setattr(right.shared_data, "_fetch", lambda: None)
    left.shared_data["left"] = "first"
    right.shared_data["right"] = "second"

    data = concurrency_db.misc.find_one(left.io.query)["shared_data"]
    assert data["left"] == "first"
    assert data["right"] == "second"


def test_shared_read_does_not_rewrite_other_values(
    tmp_path, concurrency_db, monkeypatch
):
    mm = make_mm(tmp_path, concurrency_db)
    left, right = make_group(mm), make_group(mm)
    left.shared_data["existing"] = "first"
    right.shared_data._fetch_remote()
    left.shared_data["new"] = "second"
    monkeypatch.setattr(right.shared_data, "_fetch_remote", lambda: None)

    assert right.shared_data["existing"] == "first"
    assert concurrency_db.misc.find_one(left.io.query)["shared_data"]["new"] == "second"


@pytest.mark.parametrize("key", ["plain", "a.b", "$label"])
def test_literal_shared_keys_and_values(tmp_path, concurrency_db, key):
    group = make_group(make_mm(tmp_path, concurrency_db))
    group.shared_data[key] = "$literal-value"
    assert group.shared_data[key] == "$literal-value"
    assert (
        concurrency_db.misc.find_one(group.io.query)["shared_data"][key]
        == "$literal-value"
    )
    del group.shared_data[key]
    assert key not in concurrency_db.misc.find_one(group.io.query)["shared_data"]


def test_shared_delete_preserves_a_concurrent_key(
    tmp_path, concurrency_db, monkeypatch
):
    mm = make_mm(tmp_path, concurrency_db)
    left, right = make_group(mm), make_group(mm)
    left.shared_data["delete"] = "old"
    right.shared_data._fetch()
    left.shared_data["keep"] = "new"
    monkeypatch.setattr(right.shared_data, "_fetch", lambda: None)
    del right.shared_data["delete"]

    data = concurrency_db.misc.find_one(left.io.query)["shared_data"]
    assert "delete" not in data
    assert data["keep"] == "new"


def test_stale_group_save_preserves_shared_values_and_lock(tmp_path, concurrency_db):
    mm = make_mm(tmp_path, concurrency_db)
    writer, stale = make_group(mm), make_group(mm)
    writer.shared_data["new"] = "value"
    assert writer.io.load_markbusy() is not None
    stale.data.active = False
    stale.io.save()

    doc = concurrency_db.misc.find_one(writer.io.query)
    assert doc["shared_data"]["new"] == "value"
    assert doc["busy"] == "owner"
    assert not doc["active"]


def test_group_release_requires_its_owner(tmp_path, concurrency_db):
    owner = make_group(make_mm(tmp_path, concurrency_db, "owner"))
    other = make_group(make_mm(tmp_path, concurrency_db, "other"))
    assert owner.io.load_markbusy() is not None
    assert other.io.release() is None
    assert concurrency_db.misc.find_one(owner.io.query)["busy"] == "owner"
    assert owner.io.release()["busy"] == "false"
    assert owner.data.busy == "false"


def test_local_group_release_requires_its_owner(tmp_path):
    owner = make_group(make_mm(tmp_path, sid="owner"))
    other = make_group(make_mm(tmp_path, sid="other"))
    assert owner.io.load_markbusy() is not None
    assert other.io.release() is None
    assert owner.io.load().busy == "owner"
    assert owner.io.release()["busy"] == "false"
    assert owner.io.load().busy == "false"


def test_stale_matchmaker_save_preserves_new_member_state(tmp_path, concurrency_db):
    mm = make_mm(tmp_path, concurrency_db)
    member = make_member(mm, ping=1)
    member.io.save()
    stale = mm.io.load()
    member.data.role = "a"
    member.data.group_id = "new-group"
    member.data.ping = 500
    member.io.save()
    stale.ping_timeout = 30
    mm.io.save(stale)

    current = mm.io.load()
    assert current.ping_timeout == 30
    assert current.members["member"] == asdict(member.data)


def test_matchmaker_role_change_preserves_a_newer_ping(tmp_path, concurrency_db):
    mm = make_mm(tmp_path, concurrency_db)
    member = make_member(mm, ping=1)
    member.io.save()
    stale = mm.io.load()
    member.data.ping = 500
    member.io.save()
    stale.members["member"]["role"] = "a"
    stale.members["member"]["ping"] = 100
    mm.io.save(stale)

    current = mm.io.load().members["member"]
    assert current["role"] == "a"
    assert current["ping"] == 500


def test_member_save_does_not_rewind_heartbeat(tmp_path, concurrency_db):
    mm = make_mm(tmp_path, concurrency_db)
    member = make_member(mm, ping=500)
    member.io.save()
    member.data.ping = 1
    member.data.role = "a"
    member.io.save()
    current = mm.io.load().members["member"]
    assert current["ping"] == 500
    assert current["role"] == "a"


def test_atomic_activation_preserves_members_and_foreign_lock(tmp_path, concurrency_db):
    mm = make_mm(tmp_path, concurrency_db)
    member = make_member(mm, role="a", group_id="new-group")
    member.io.save()
    concurrency_db.misc.update_one(mm.io.query, {"$set": {"busy": "other"}})

    result = mm.io.toggle_activation()
    assert not result.active
    assert result.members["member"] == asdict(member.data)
    assert result.busy == "other"


def test_two_concurrent_activation_toggles_preserve_parity(tmp_path, concurrency_db):
    mm = make_mm(tmp_path, concurrency_db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: mm.io.toggle_activation().active, range(2)))
    assert sorted(values) == [False, True]
    assert mm.io.load().active
