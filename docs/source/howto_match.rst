First, you initialize the MatchMaker with the roles that you
need and the experiment session object::

    import alfred3 as al
    from alfred3_interact import MatchMaker

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        mm = MatchMaker("a", "b", exp=exp) # Initialize the MatchMaker

    exp += al.Page(name="demo")

Next, you use either :meth:`.match_stepwise` or :meth:`.match_groupwise`
to match the experiment session to a group. Both methods return
a :class:`.Group` object, which is the gateway to the data of all
group members. You should include this group in the "plugins"
attribute of the experiment session::

    import alfred3 as al
    from alfred3_interact import MatchMaker

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        mm = MatchMaker("a", "b", exp=exp)
        exp.plugins.group = mm.match_stepwise() # Assign and return a group

    exp += al.Page(name="demo")

The group object offers the attribute :attr:`.Group.me`, which always
refers to the :class:`.GroupMember` object of the current experiment
session - most importantly, this attribute can be used to get to know
the role of the present session::

    import alfred3 as al
    from alfred3_interact import MatchMaker

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        mm = MatchMaker("a", "b", exp=exp)
        exp.plugins.group = mm.match_stepwise()
        print(exp.plugins.group.me.role) # Print own role

    exp += al.Page(name="demo")

Beyond "me", the group object offers :attr:`.Group.you`, which always
refers to the other participant *in groups of size two* (it cannot
be used in bigger groups). On top of that, all members of a group
can be referenced through the group via their role::

    import alfred3 as al
    from alfred3_interact import MatchMaker

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        mm = MatchMaker("a", "b", exp=exp)
        exp.plugins.group = mm.match_stepwise()
        print(exp.plugins.group.a) # Accessing the GroupMember with role "a"

    exp += al.Page(name="demo")

The :class:`.GroupMember` object then serves as a gateway to the
data collected in a specific member's session. For example,
:attr:`.GroupMember.values` offers access to the values of all
input elements that have been filled by the referenced member.

You can complete the matchmaking process in the
:meth:`alfred3.experiment.Experiment.setup`
hook, but it is usually advisable to use the
:meth:`.WaitingPage.wait_for` hook of a :class:`.WaitingPage`. That
way you have two advantages. First, you have more control over the
exact moment in which you want to allow participants into the
matchmaking process (for example, after they read initial
instructions). Second, the WaitingPage offers a nice visual display
that informs participants about the ongoing matchmaking and about
how much time has passed.

After successful matchmaking, you can use the :class:`.WaitingPage`
throughout the experiment whenever you need to make sure that group
members have progressed to a certain point in the experiment. For
example, role "b" may need some data from role "a" on their fith page.
So, before the fith page, you place a WaitingPage that will pause "b"'s
session until "a" has progressed far enough through the experiment,
so that the required data is available.