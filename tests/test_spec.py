import pytest
from alfred3_interact import ParallelSpec, SequentialSpec, IndividualSpec

class TestSequentialSpec:

    def test_init(self):
        spec = SequentialSpec("a", "b", nslots=5, name="test")

        assert spec


class TestParallelSpec:

    def test_init(self):
        spec = ParallelSpec("a", "b", nslots=5, name="test")

        assert spec

class TestIndividualSpec:

    def test_init(self):
        spec = IndividualSpec(nslots=5, name="test")

        assert spec



