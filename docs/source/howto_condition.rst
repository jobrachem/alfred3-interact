.. _htcondition:

How to create groups of different conditions
===============================================

This how to covers the allocation of groups to different experiment
conditions. If you want to take your first steps with interactive
experiments, you should start with :ref:`htmatch`.

In an interactive experiment, the allocation to conditions works in a
different way than in a single-participant experiment. This is necessary,
because we are assigning groups to conditions, not single sessions.
Instead of using a randomizer, you create a new group spec for each
condition. You then use :meth:`.MatchMaker.match_random` for real
pseudorandom allocation, or :meth:`.MatchMaker.match_chain` if you need
to be efficient about managing groups of different sizes. For this tutorial,
we will stick to :meth:`.MatchMaker.match_random`.

We will create an experiment with two conditions. The group structure
is identical in this experiment - both groups are parallel and consist
of two members. We will collect a maximum of ten groups in each condition.
The conditions differ only in the information
that we present to participants. We start by defining two specs, one for
each group::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        roles = ["role1", "role2"]
        control = ali.ParallelSpec(*roles, nslots=10, name="control")
        intervention = ali.ParallelSpec(*roles, nslots=10, name="intervention")


Next, we add the MatchMaker::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        roles = ["role1", "role2"]
        control = ali.ParallelSpec(*roles, nslots=10, name="control")
        intervention = ali.ParallelSpec(*roles, nslots=10, name="intervention")

        exp.plugins.mm = ali.MatchMaker(control, intervention, exp=exp)


Because this is a tutorial and we want to keep things concise, we add
a WaitingPage that does the matching right at the beginning of the
experiment. We do so in an :class:`alfred3.ForwardOnlySection` to prevent
participants from returning to the matchmaking page.
We use :meth:`.MatchMaker.match_random` to create a group from a randomly
chosen spec. Additionally, we extract the name of the used spec and
set it as the experiment condition::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        roles = ["role1", "role2"]
        control = ali.ParallelSpec(*roles, nslots=10, name="control")
        intervention = ali.ParallelSpec(*roles, nslots=10, name="intervention")

        exp.plugins.mm = ali.MatchMaker(control, intervention, exp=exp)

    exp += al.ForwardOnlySection(name="main")

    @exp.member(of_section="main")
    class Match(ali.WaitingPage):

        def wait_for(self):
            group = self.exp.plugins.mm.match_random()

            self.exp.plugins.group = group
            self.exp.condition = group.spec_name

            return True

With this setup, our randomization mechanism is established. But we are
currently not doing anything with it, so let us change that. On the following
page, we will display different tasks, based on the experiment condition::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        roles = ["role1", "role2"]
        control = ali.ParallelSpec(*roles, nslots=10, name="control")
        intervention = ali.ParallelSpec(*roles, nslots=10, name="intervention")

        exp.plugins.mm = ali.MatchMaker(control, intervention, exp=exp)

    exp += al.ForwardOnlySection(name="main")

    @exp.member(of_section="main")
    class Match(ali.WaitingPage):

        def wait_for(self):
            group = self.exp.plugins.mm.match_random()

            self.exp.plugins.group = group
            self.exp.condition = group.spec_name

            return True

    @exp.member(of_section="main")
    class Task(al.Page):

        def on_first_show(self):

            if self.exp.condition == "control":
                task = "Please calculate: 4 + 4"

            elif self.exp.condition == "intervention":
                task = "Please calculate: (4.235 + 7.432) / 2.13

            self += al.NumberEntry(toplab=task, force_entry=True, name="task")


Granted, that task is not the pinnacle of science. But it serves to
demonstrate how to work with experimental conditions.
