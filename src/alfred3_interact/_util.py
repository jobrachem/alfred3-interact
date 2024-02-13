"""
Soome basic utilities.
"""


def saving_method(exp) -> str:
    if not exp.secrets.getboolean("mongo_saving_agent", "use"):
        if exp.config.getboolean("local_saving_agent", "use"):
            return "local"
    elif exp.secrets.getboolean("mongo_saving_agent", "use"):
        return "mongo"
    else:
        return None


class AlfredInteractError(Exception):
    pass


class MatchingTimeout(AlfredInteractError):
    pass


class MatchingError(AlfredInteractError):
    pass


class BusyGroup(AlfredInteractError):
    pass


class NoMatch(AlfredInteractError):
    pass


class MatchMakerBusy(AlfredInteractError):
    pass
