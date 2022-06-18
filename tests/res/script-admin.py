import alfred3 as al

import alfred3_interact as ali

exp = al.Experiment()

exp.admin += ali.MatchMakerMonitoring("plugins.mm", name="monitor")
exp.admin += ali.MatchMakerActivation("plugins.mm", name="activate")


@exp.setup
def setup(exp):
    spec = ali.IndividualSpec(5, name="test")
    exp.plugins.mm = ali.MatchMaker(spec, exp=exp)


exp += al.Page(title="Page 1", name="p1")
