from . import MatchMaker, NoMatch

def get_group(exp, roles: list = None, ongoing_sessions_ok: bool = False):
    roles = roles if roles is not None else ["a", "b"]
    mm = MatchMaker(*roles, exp=exp)
    return mm.match_stepwise(ongoing_sessions_ok=ongoing_sessions_ok)

def get_group_groupwise(exp_factory: callable, roles: list = None):
    roles = roles if roles is not None else ["a", "b"]
    exp1 = exp_factory()
    exp2 = exp_factory()

    mm1 = MatchMaker(*roles, exp=exp1)
    mm2 = MatchMaker(*roles, exp=exp2)

    try:
        group1 = mm1.match_groupwise()
    except NoMatch:
        pass

    group2 = mm2.match_groupwise()
    group1 = mm1.match_groupwise()

    return group1

def get_multiple_groups(*mm):

    try:
        mm[0].match_groupwise()
    except NoMatch:
        pass
    
    groups = [m.match_groupwise() for m in reversed(mm)]

    return tuple(reversed(groups))