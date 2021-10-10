# alfred3-interact: Interactive web-experiments in alfred3 [![DOI](https://zenodo.org/badge/340368707.svg)](https://zenodo.org/badge/latestdoi/340368707)

Alfred3-interact is a plugin for [alfred3](https://github.com/ctreffe/alfred).
It allows for the creation of interactive web experiments, predominantly 
in the social sciences. As prerequisites,
you need to have **Python 3.7** or newer and **alfred3 v2.2.0** or newer installed.

## Installation

```
$ pip3 install alfred3_interact
```

## Documentation

Documentation for alfred3_interact is avaialable here: [Link to docs](https://jobrachem.github.io/alfred3-interact/build/html/index.html)

## Quick example

Below is an example `script.py` for creating an experiment with an
asynchronous exchange of data between participants matching:

1. Initialize a group spec and the `alfred3_interact.MatchMaker` during experiment setup
2. Use a `alfred3_interact.WaitingPage` for matchmaking inside its `wait_for` hook method.
3. Find a group via `MatchMaker.match` and bind it to the
   experiment plugins object.
4. Now the group object is available in sections, pages, and elements
   through the experiment session object. You can use it to access data
   from other participants in the same group.

```python
# script.py
import alfred3 as al
import alfred3_interact as ali

exp = al.Experiment()

@exp.setup
def setup(exp):
    spec = ali.SequentialSpec("role1", "role2", nslots = 10, name="mygroup")
    exp.plugins.mm = ali.MatchMaker(spec, exp=exp)


@exp.member
class Match(ali.WaitingPage):
    
    def wait_for(self):
        group = self.exp.plugins.mm.match()
        self.exp.plugins.group = group
        return True


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

## Citation

Alfred3-interact was developed for research at the department for 
economic and social psychology, Georg-August-University Göttingen. 
**If you are publishing research conducted using alfred3, the 
following citation is required:**

>Brachem, J. & Treffenstädt, C. (2021). Alfred3-interact - Interactive web experiments in alfred3. (Version x.x.x). Göttingen, 
Germany: https://doi.org/10.5281/zenodo.1437219