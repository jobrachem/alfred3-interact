
def saving_method(exp) -> bool:
    if not exp.secrets.getboolean("mongo_saving_agent", "use"):
        if exp.config.getboolean("local_saving_agent", "use"):
            return "local"
    elif exp.secrets.getboolean("mongo_saving_agent", "use"):
        return "mongo"
    else:
        return None


class MatchingTimeout(Exception):
    pass


class MatchingError(Exception):
    pass

class BusyGroup(Exception):
    pass