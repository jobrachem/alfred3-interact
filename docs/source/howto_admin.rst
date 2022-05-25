.. _htadmin:

How To Use the Admin Tools
=========================================

Alfred3_interact comes with some administrative utilities that can be
included in alfred3's admin mode. Currently, you can use the following
admin pages:

.. autosummary::
    :nosignatures:

    ~alfred3_interact.page.MatchMakerMonitoring
    ~alfred3_interact.page.MatchMakerActivation


.. note:: For more information and examples, please visit the API
    documentation of the admin pages linked above.

To activate the admin mode, we need to set passwords for all three
admin levels in *secrets.conf*::

    # secrets.conf
    [general]
    adminpass_lvl1 = demo
    adminpass_lvl2 = use-better-passwords
    adminpass_lvl3 = to-protect-access


How to access the admin mode
-------------------------------

You can access the admin mode by adding ``?admin=true`` to the experiment's
start link. If you are running a local experiment, this means that you
can use::

    http://127.0.0.1:5000/start?admin=true

Note that the question mark only signals the beginning of additional
url arguments. If you use multiple url arguments, they are chained via
``&``. For example, the following url would *also* start the experiment
in admin mode::

    http://127.0.0.1:5000/start?demo=this&admin=true

When you open the link to the admin mode, you face a page asking you
for a password. If you encounter an "Internal Server Error", you should
check the log - you may have forgotten to specify all necessary passwords.

If you enter a correct password, you can move on to the admin pages. Based
on your password, you may see only a subset of all possibly available pages.
With the level 1 password, you can only see level 1 pages. With the level 2
password, you can see level 1 and level 2 pages. And with the level 3
password, you have full access to pages of all three levels.
