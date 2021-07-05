# import pytest
# from alfred3.testutil import get_misc_collection, clear_db
# from dotenv import load_dotenv

# load_dotenv()

# @pytest.fixture
# def col():
#     col = get_misc_collection()
#     yield col
#     clear_db()


# def test_collection(col):
    
#     col.insert_one({"members": {"sid1": {"sid": "test", "data": "other data"}, "sid2": {"sid": "sid2", "data": "other data 2"}}})

#     res = col.find_one({"members.sid1.sid": "test"}, projection={"members.sid1": 1, "members.sid12": 1})


#     assert 0