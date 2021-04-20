# alfred3-interact: Interactive web-experiments in alfred3

Alfred3-interact is a plugin for [alfred3](https://github.com/ctreffe/alfred).
It allows for the creation of interactive web experiments, predominantly 
in the social sciences. As prerequisites,
you need to have **Python 3.7** or newer and **alfred3 v2.0** or newer installed.

## Installation

```
$ pip3 install alfred3_interact
```

## Documentation

Documentation for alfred3_interact is avaialable here: [Link to docs](https://jobrachem.github.io/alfred3-interact/build/html/index.html)

## Quick example

Below is an example `script.py` for creating an experiment with an
asynchronous exchange of data between participants via *stepwise* matching:

1. Initialize the `MatchMaker` during experiment setup
2. Find a group via `MatchMaker.match_stepwise` and bind it to the
   experiment plugins object.
3. Now the group object is available in sections, pages, and elements
   through the experiment session object. You can use it to access data
   from other participants in the same group.

Note: While `match_stepwise` has its main purpose in asynchronous interactive
experiments, you can still include `WaitingPage`s to synchronize group
members. Refer to the documentation for the WaitingPage class for more
guidance.

```python
# script.py
import alfred3 as al
import alfred3_interact as ali

exp = al.Experiment()

@exp.setup
def setup(exp):
    mm = ali.MatchMaker("role1", "role2", exp=exp)
    exp.plugins.group = mm.match_stepwise()


@exp.member
class Success(al.Page):
    title = "Match successful"

    def on_exp_access(self):
        group = self.exp.plugins.group
        
        txt = f"You have successfully matched to role: {group.me.role}"
        self += al.Text(txt, align="center")

if __name__ == "__main__":
    exp.run()
```

The demo experiment can be started by executing the following command
from the experiment directory (i.e. the directory in which you placed
the `script.py`):

```
$ alfred3 run
```