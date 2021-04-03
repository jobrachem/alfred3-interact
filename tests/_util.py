from uuid import uuid4
import os
import pytest
from dotenv import load_dotenv
import alfred3 as al


load_dotenv()

@pytest.fixture
def secrets(tmp_path):
    mcreds = {}
    mcreds["use"] = True
    mcreds["host"] = os.getenv("MONGODB_HOST")
    mcreds["port"] = os.getenv("MONGODB_PORT")
    mcreds["database"] = os.getenv("MONGODB_DATABASE")
    mcreds["user"] = os.getenv("MONGODB_USERNAME")
    mcreds["password"] = os.getenv("MONGODB_PASSWORD")
    mcreds["collection"] = "testcol"
    mcreds["misc_collection"] = "testcol"
    mcreds["auth_source"] = "admin"


    s = al.config.ExperimentSecrets(expdir=tmp_path)
    s.read_dict({"mongo_saving_agent": mcreds})
    yield s

@pytest.fixture
def exp(tmp_path, secrets):
    sid = uuid4().hex
    config = al.config.ExperimentConfig(tmp_path)

    yield al.experiment.ExperimentSession(sid, config, secrets)