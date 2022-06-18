from alfred3.data_manager import DataManager as dm

from alfred3_interact.testutil import get_group


class TestMember:
    def test_values(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        assert isinstance(group.me.values, dict)

    def test_session_data(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        assert "exp_session_id" in group.me.session_data

    def test_metadata(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        metadata = group.me.metadata

        for entry in dm._metadata_keys:
            assert entry in metadata
            assert metadata.pop(entry, "not present") != "not present"

        assert not metadata

    def test_client_data(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        client_data = group.me.client_data

        for entry in dm._client_data_keys:
            assert entry in client_data
            assert client_data.pop(entry, "not present") != "not present"

        assert not client_data

    def test_move_history(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        move_history = group.me.move_history

        assert isinstance(move_history, list)

    def test_adata(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        adata1 = group.me.adata
        adata2 = group.me.additional_data

        assert isinstance(adata1, dict)
        assert isinstance(adata2, dict)

    def test_matched(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        assert group.me.matched

    def test_group_id(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        assert group.me.group_id == group.group_id

    def test_role(self, exp_factory):
        exp = exp_factory()
        group = get_group(exp)

        assert group.me == group[group.me.role]
