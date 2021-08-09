from . import MatchMaker, NoMatch, ParallelSpec, SequentialSpec

def get_group(exp, roles: list = None, ongoing_sessions_ok: bool = False, nslots: int = 5):
    roles = ["a", "b"] if roles is None else roles
    spec = SequentialSpec(*roles, nslots=nslots, name="test", ongoing_sessions_ok=ongoing_sessions_ok)
    mm = MatchMaker(spec, exp=exp)
    group = mm.match_to("test")
    return group
    
def get_group_groupwise(exp_factory: callable, roles: list = None, nslots: int = 5):
    roles = roles if roles is not None else ["a", "b"]
    exp1 = exp_factory()
    exp2 = exp_factory()

    spec1 = ParallelSpec(*roles, nslots=nslots, name="test")
    spec2 = ParallelSpec(*roles, nslots=nslots, name="test")

    mm1 = MatchMaker(spec1, exp=exp1)
    mm2 = MatchMaker(spec2, exp=exp2)

    try:
        group1 = mm1.match_to("test")
    except NoMatch:
        pass

    mm2.match_to("tes")
    group1 = mm1.match_to("test")

    return group1

def get_multiple_groups(*mm, specname: str = "test"):

    try:
        mm[0].match_to(specname)
    except NoMatch:
        pass
    
    groups = [m.match_to(specname) for m in reversed(mm)]

    return tuple(reversed(groups))