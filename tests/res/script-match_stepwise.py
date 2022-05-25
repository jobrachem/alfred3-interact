import alfred3 as al

import alfred3_interact as ali

exp = al.Experiment()


@exp.setup
def setup(exp):
    mm = ali.MatchMaker("a", "b", exp=exp, admin_pw="test")
    group = mm.match_stepwise()
    exp.plugins.group = group


@exp.member
class Success(al.Page):
    def on_first_show(self):
        group = self.exp.plugins.group
        role = group.me.role
        self += al.Text(f"Matched to group: \t{group.group_id[-4:]}")
        self += al.Text(f"Matched to role: \t{role}")
