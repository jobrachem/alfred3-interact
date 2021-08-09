alfred3-interact: Interactive web-experiments
==============================================

Welcome to the documentation of alfred3-interact! Alfred3-interact
is a plugin for alfred3_ that offers the creation of interactive web 
experiments, predominantly in the social sciences. 
As prerequisites, you need to have **Python 3.7** or newer 
and **alfred3 v2.2** or newer installed.

.. _alfred3: https://github.com/ctreffe/alfred


Installation
--------------

Alfred3-interact can be installed via pip::

    $ pip3 install alfred3_interact


Usage
-------

The composition of groups of multiple participants for data exchange
relies on the :class:`.MatchMaker` class and its methods 
:meth:`.match_random`, :meth:`.match_chain`, and :meth:`.match_to`. 
All of these methods return :class:`.Group` objects, which allow you to 
reference individual participants and their corresponding 
:class:`.GroupMember` objects based on their role in the group. 

Within the experiment, you can define waiting points for synchronizing
multiple participants' progress through the :class:`.WaitingPage`.
We also provide a :class:`.Chat` element. This element can be comfortably 
used as a group chat through the shortcut :meth:`.Group.chat`, but also
independently of groups. 

Note that individual sessions can belong to multiple groups at once. 
You can use multiple MatchMakers in the same experiment.

Equipped with this narrative information, you can dive into the API
documentation and examples to see in more detail how to use 
alfred3_interact in your alfred3 experiments.

API Reference Overview
-----------------------

.. autosummary::
   :toctree: generated
   :caption: API Reference
   :recursive:
   :nosignatures:

   ~alfred3_interact.match.MatchMaker
   ~alfred3_interact.spec.SequentialSpec
   ~alfred3_interact.spec.ParallelSpec
   ~alfred3_interact.spec.IndividualSpec
   ~alfred3_interact.group.Group
   ~alfred3_interact.member.GroupMember
   ~alfred3_interact.page.WaitingPage
   ~alfred3_interact.element.Chat

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
