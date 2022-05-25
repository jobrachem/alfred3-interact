.. _htmatch:

How To Create an Interactive Experiment
=========================================

Step 1: Preparations
----------------------

To create an interactive experiment, you start by defining group specs.
These are like blueprints that organize some important information about
groups like the number of members and the names of the roles to allocate.
Let's define a :class:`.ParallelSpec` that lets us create groups of
participants who interact in real-time with each other. Because we will
need access to an initialized :class:`.alfred3.experiment.ExperimentSession`
object later, we use the :meth:`.alfred3.Experiment.setup` decorator::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")

Here, we define a spec that will be used to create groups with three
members, which will be assigned to the roles "role1", "role2", and "role3".
By setting ``nslots=5``, we allocate five group slots to this spec.
That means, we determine that our spec will stop being used
for new groups as soon as we have five fully finished groups. The argument
``name="myspec"`` is a mandatory identifier that will allow us to associate
each group with the spec that was used to create it. Spec names have to
be unique within one MatchMaker and are your go-to solution if you want
to place groups in different experimental conditions. There are some
optional arguments that
can be used to finetune the spec's behavior with regard to managing group
slots. These are explained in the API documentation of the individual
classes.

The currently available specs are:

.. autosummary::
    :nosignatures:

    ~alfred3_interact.spec.SequentialSpec
    ~alfred3_interact.spec.ParallelSpec
    ~alfred3_interact.spec.IndividualSpec

The spec alone does not make the experiment interactive - for this, we
need an instance of :class:`.MatchMaker`. The MatchMaker takes any number
of specs and uses them to create groups. We need access to our spec object
(or objects – you can use more than one spec, but more on that later),
which is why we initialize the MatchMaker in the setup function aswell.
We bind our matchmaker instance to the ExperimentSession instance ``exp``
in its dedicated place for "plugin stuff",
:attr:`alfred3.ExperimentSession.plugins`, because we want to have easy
access to the MatchMaker later on::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)


Step 2: Make a Match
------------------------

We are now ready to implement the actual matchmaking process. This
process required a :class:`.WaitingPage`. This page allows us to
repeatedly check whether we have enough active participants to form a
group while greeting waiting participants with a pleasant (and customizable)
waiting screen. Because we are creating a minimal demo experiment in this
tutorial, our first page is a waiting page.

We define it much like we would define any ordinary page, but we use
the special hook :meth:`.WaitingPage.wait_for` to define behavior that
should be executed repeatedly until we reach a state of success. Inside
the function, we signal success simply by returning *True* – once a return
value of *True* is observed, the WaitingPage will automatically forward
participants to the next page. The WaitingPage can be used not only for
matchmaking, but also to implement points of synchronization in an
experiment – but more on that later.

To make a match, we will use the MatchMaker's :meth:`.MatchMaker.match`
method, which returns a :class:`.Group` instance upon successful matching
and raises a :class:`.NoMatch` exception otherwise. The NoMatch exception
is a signal that gets handled by the WaitingPage.

We use a :class:`alfred3.ForwardOnlySection` to limit movements to forward
moves, because moing back to a WaitingPage does not make much sense here.
Let's see the code::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)

    exp += al.ForwardOnlySection(name="main")


    @exp.member(of_section="main")
    class Match(ali.WaitingPage):

        def wait_for(self):
            group = self.exp.plugins.mm.match()
            self.exp.plugins.group = group

            return True

Like the MatchMaker instance, we bind the group instance to our ExperimentSession's
plugin attribute for future reference.
Because :meth:`.MatchMaker.match` raises an exception if there are not
enough participants active, the function returns *True* only if a match
was successful. By default, a WaitingPage will try to reach a successful
call to its :meth:`.WaitingPage.wait_for` method for 20 minutes. If it
does not reach a successful call, the experiment will be aborted. Let us
use a shorter timeout of 10 minutes by overriding the page's
:attr:`.WaitingPage.wait_timeout` attribute::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)

    exp += al.ForwardOnlySection(name="main")


    @exp.member(of_section="main")
    class Match(ali.WaitingPage):
        wait_timeout = 60 * 10 # timeout in seconds

        def wait_for(self):
            group = self.exp.plugins.mm.match()
            self.exp.plugins.group = group

            return True

To customize the content of your WaitingPage, you can override its default
:meth:`.WaitingPage.on_exp_access` hook specification. If you simply want
to display a different message but keep the overall design, you can
also just override the :attr:`.WaitingPage.wait_msg`. For more finetuning,
take a look at the API documentation at :class:`.WaitingPage`.

We used :meth:`.MatchMaker.match` here to conduct the actual match, but
you have more options that may be useful in pratice:

.. autosummary::
    :nosignatures:

    ~alfred3_interact.MatchMaker.match_to
    ~alfred3_interact.MatchMaker.match_random
    ~alfred3_interact.MatchMaker.match_chain

Step 3: Work with the Group
--------------------------------

The group object is your gateway to connecting data from multiple sessions.
We will look at a few ways it can be used. First, let us add a page with
a simple text input element for demonstration purposes. We add it before
the WaitingPage to make sure that each member of our group has completed
this element when matching::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)

    exp += al.ForwardOnlySection(name="main")


    @exp.member(of_section="main")
    class DemoInput(al.Page):
        title = "Match Successful"

        def on_exp_access(self):
            self += al.TextEntry(
                toplab="What is your favourite meal?", force_input=True, name="meal"
            )

            choices = ["not at all", "okay", "very much"]
            self += al.SingleChoiceButtons(
                *choices,
                toplab="How much do you think other people like this food?",
                name="rating"
            )


    @exp.member(of_section="main")
    class Match(ali.WaitingPage):
        wait_timeout = 60 * 10 # timeout in seconds

        def wait_for(self):
            group = self.exp.plugins.mm.match()
            self.exp.plugins.group = group

            return True

Now, we will add a third page on which we use the group instance to
display some information about our group. We use :attr:`.Group.spec_name`
to identify the group's spec. This can allow us to distinguish groups
in different conditions. Apart from that, we will mainly access the group
members' :class:`.GroupMember` instances through the group. These objects
in turn offer access to each member's experiment data. We can always refer
to the current session's member object via :attr:`.Group.me`. In a dyad
(i.e. a group with exactly two members), we can refer to the other member
via :attr:`.Group.you`. Additionally, we can always refer to each group
member by using its role name like an attribute with the group. For example,
to reference the group member of role "role1", we refer to ``group.role1``,
if ``group`` is our group instance. We can iterate over all members of the
group with the generator :meth:`.Group.members` and over all members
*except* :attr:`.Group.me` via :meth:`Group.other_members`.

Now let us see these referencing steps in practice. Because the group
object does not exist before the matchmaking on the WaitingPage has
been completed, we cannot use a :meth:`alfred3.Page.on_exp_access` hook.
Instead, we use :meth:`alfred3.Page.on_first_show`, which runs when
a page is first shown::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)

    exp += al.ForwardOnlySection(name="main")


    @exp.member(of_section="main")
    class DemoInput(al.Page):
        title = "Match Successful"

        def on_exp_access(self):
            self += al.TextEntry(
                toplab="What is your favourite meal?", force_input=True, name="meal"
            )

            choices = ["not at all", "okay", "very much"]
            self += al.SingleChoiceButtons(
                *choices,
                toplab="How much do you think other people like this food?",
                name="rating"
            )


    @exp.member(of_section="main")
    class Match(ali.WaitingPage):
        wait_timeout = 60 * 10 # timeout in seconds

        def wait_for(self):
            group = self.exp.plugins.mm.match()
            self.exp.plugins.group = group

            return True


    @exp.member(of_section="main")
    class DemoAccess(al.Page):
        title = "Demo Page for Group Access"

        def on_first_show(self):
            g = self.exp.plugins.group # get group object

            self += al.Text(f"This group way created based on: {g.spec_name}")

            # access current session
            self += al.Text(f"My own role in this group is: {g.me.role}")

            self += al.VerticalSpace("20px")

            # iterate over other members
            for member in g.other_members():
                fav_meal = member.values.get("meal")
                self += al.Text(f"Member with role '{member.role}' entered '{fav_meal}' as their favourite meal.")

            self += al.VerticalSpace("20px")

            # access member via role
            r1_rating = g.role1.values("rating")
            self += al.Text(f"Role1's rating was: {r1_rating}")


Step 4: Use a WaitingPage for Syncing
-----------------------------------------

When programming an interactive experiment, you will repeatedly find
yourself wanting to include a kind of check point where the experiment
pauses for all participants until they have reached similar progress.
This can be achieved by WaitingPages. We start with an earlier, smaller
version of our demo experiment::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)

    exp += al.ForwardOnlySection(name="main")


    @exp.member(of_section="main")
    class Match(ali.WaitingPage):

        def wait_for(self):
            group = self.exp.plugins.mm.match()
            self.exp.plugins.group = group

            return True

To this experiment, we add a page with an input element *after* the
waiting page and another page that accesses the inputs made by all
group members. If we do not synchronize the experiment between the
former and the latter page, we may encounter the following situation:
Participants of "role1" and "role2" are still thinking about their input.
Meanwhile, the participant of "role3" is quick and moves on to the next
page. Because "role1" and "role2" have not commited their inputs, the
display for "role3" cannot display their values, even though that is
necessary for an orderly experiment session. The page may even crash,
because we cannot access the values that we seek. To prevent these issues,
we add a waiting page in between the input and the accessing calls. This
will pause the experiment for faster participants until all required values
are present::

    import alfred3 as al
    import alfred3_interact as ali

    exp = al.Experiment()

    @exp.setup
    def setup(exp):
        spec = ali.ParallelSpec("role1", "role2", "role3", nslots=5, name="myspec")
        exp.plugins.mm = ali.MatchMaker(spec, exp=exp)

    exp += al.ForwardOnlySection(name="main")


    @exp.member(of_section="main")
    class Match(ali.WaitingPage):

        def wait_for(self):
            group = self.exp.plugins.mm.match()
            self.exp.plugins.group = group

            return True


    @exp.member(of_section="main")
    class InputPage(al.Page):
        title = "Input Page"

        def on_exp_access(self):
            self += al.TextEntry("What's your favourite drink?", force_input=True, name="drink")


    @exp.member(of_section="main")
    class Sync(ali.WaitingPage):

        def wait_for(self):
            """
            Returns True, if a value for 'drink' is present for each
            group member.
            """
            g = self.exp.plugins.group
            drinks = [m.values.get("drink") for m in g.members()]
            return all(drinks)


    @exp.member(of_section="main")
    class View(al.Page):
        title = "View Inputs"

        def on_first_show(self):
            g = self.exp.plugins.group

            for m in g.members():
                self += al.Text(f"Member of role '{m.role}' entered '{m.values.get('drink')}' as their favourite drink.")


You are now ready to create your first interactive experiments. Make
sure to check out the API documentation for the relevant classes, especially
:class:`.MatchMaker`, :class:`.Group`, and :class:`.GroupMember` for more
detailed information.
