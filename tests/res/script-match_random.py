import random

import alfred3 as al

import alfred3_interact as ali

exp = al.Experiment()


@exp.setup
def setup(exp):
    counter1 = ali.GroupCounter(5, exp)
    counter2 = ali.GroupCounter(10, exp)

    mm1 = ali.MatchMaker(
        "a", "b", "c", "d", exp=exp, admin_pw="test", id="large_match", counter=counter1
    )
    mm2 = ali.MatchMaker(
        "a", "b", exp=exp, admin_pw="test", id="small_match", counter=counter2
    )

    exp.plugins.mm = {"large": mm1, "small": mm2}


@exp.member
class Match(ali.MatchingPage):
    def wait_for(self):
        matchmakers = list(self.exp.plugins.mm.values())
        mm = ali.random_matchmaker(*matchmakers)

        if self.passed_time < 2 * 60:
            mm = exp.plugins.mm["large"]
        else:
            # TODO: Member aus large deaktivieren
            mm = exp.plugins.mm["small"]

        if mm.matchmaker_id == "large_match":
            group = mm.match_groupwise()

            condition = group.a.adata.get("matchmaker_condition", False)

            if condition == "1x4":
                group2 = group  # noqa: F841

            elif condition == "2x2":
                mm = exp.plugings.mm["small"]
                group2 = mm.match_groupwise()  # noqa: F841

            elif group.me.role == "a":
                condition = random.choose(["1x4", "2x2"])
                self.exp.adata["matchmaker_condition"] = condition
                self._save_data(sync=True)

        self.exp.plugins.group = group
        self.exp.condition = mm.matchmaker_id
        return True


@exp.member
class Success(al.Page):
    def on_first_show(self):
        role = self.exp.plugins.group.me.role
        self += al.Text(f"Matched to role: \t{role}")
