import alfred3 as al
import alfred3_interact as ali

exp = al.Experiment()

@exp.setup
def setup(exp):

    exp.plugins.mm = ali.MatchMaker("a", "b", exp=exp, admin_pw="test")

@exp.member
class Match(ali.MatchingPage):

    def wait_for(self):
        group = self.exp.plugins.mm.match_groupwise()
        self.exp.plugins.group = group
        return True

@exp.member
class Success(al.Page):
    
    def on_first_show(self):
        role = self.exp.plugins.group.me.role
        self += al.Text(f"Matched to role: \t{role}")