import pytest

from alfred3_interact import IndividualSpec, ParallelSpec, SequentialSpec


class TestSequentialSpec:
    def test_init(self):
        spec = SequentialSpec("a", "b", nslots=5, name="test")

        assert spec

    def test_role_validation(self):
        with pytest.raises(ValueError):
            SequentialSpec("a.b", nslots=1, name="test")


class TestParallelSpec:
    def test_init(self):
        spec = ParallelSpec("a", "b", nslots=5, name="test")

        assert spec

    def test_role_validation(self):
        with pytest.raises(ValueError):
            ParallelSpec("a.b", nslots=1, name="test")


class TestIndividualSpec:
    def test_init(self):
        spec = IndividualSpec(nslots=5, name="test")

        assert spec
