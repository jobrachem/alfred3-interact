import alfred3 as al

import alfred3_interact as ali

exp = al.Experiment()


@exp.setup
def setup(exp):
    mm1 = ali.MatchMaker("a", "b", "c", "d", exp=exp, admin_pw="test", id="large_match")
    mm2 = ali.MatchMaker("a", "b", exp=exp, admin_pw="test", id="small_match")

    exp.plugins.mm = {"large": mm1, "small": mm2}


@exp.member
class Match(ali.MatchingPage):
    def wait_for(self):
        if self.passed_time < 2 * 60:
            mm = exp.plugins.mm["large"]
        else:
            # TODO: Member aus large deaktivieren
            mm = exp.plugins.mm["small"]

        group = mm.match_groupwise()
        self.exp.plugins.group = group
        self.exp.condition = mm.matchmaker_id
        return True


@exp.member
class Success(al.Page):
    def on_first_show(self):
        role = self.exp.plugins.group.me.role
        self += al.Text(f"Matched to role: \t{role}")
