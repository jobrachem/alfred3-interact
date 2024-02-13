# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Newer versions

See https://github.com/jobrachem/alfred3-interact/releases

## alfred3_interact v0.2.4 (Released 2023-12-08)

### Fixed v0.2.4

- There seems to be a race condition in `MatchMaker._init_member()`. Sometimes,
  apparently a member has already been created, but the session ID is not available
  in the database yet. We added a hotfix to try and make this problem less severe.
  Now, `GroupMemberIO.load` will try to load the member data repeatedly, with
  a one-second sleep in between tries for 15 seconds before aborting. In most cases,
  this should give the database enough time to catch up.

## alfred3_interact v0.2.3 (Released 2022-06-18)

### Fixed v0.2.3

- Fixed #28, #29, #27, #16

### Changed v0.2.3

- Set up continuous integration

## alfred3_interact v0.2.2 (Released 2022-02-14)

### Added v0.2.2

- Added the parameter `shuffle_waiting_members` to `ParallelSpec`. If *True*,
  groups will be composed after shuffling the list of waiting members.
  If *False*, members who have been waiting for a longer time have a
  higher priority (although their prioritization is not entirely deterministic).


## alfred3_interact v0.2.1 (Released 2021-10-28)

### Added v0.2.1

- Added `alfred3_interact.MatchTestPage`, a page that can be used to
  quickly test the matchmaking of interactive experiments.

### Fixed v0.2.1

- Fixed an issue that lead to problems with role assignment in parallel
  groups.

## alfred3_interact v0.2.0 (Released 2021-10-14)

### Changed v0.2.0

- We refactored the matchmaking system to make it more robust, more
  powerful, and easier to use.

  - You can now *randomize* and *chain* group
    creation through `alfred3_interact.MatchMaker.match_random` and
    `alfred3_interact.MatchMaker.match_chain`. Both of these methods enable
    you to take the special challenges of interactive experiments into
    account. *Chaining* group creation is handy, for example when you want
    to create groups of different sizes. Larger groups are harder to realize,
    and thus you may wish to prioritize them: When possible, create a
    large group. Only when large group creation fails, create the smaller
    groups. Please refer to the documentation for more details.

  - Matchmaking now requires the definition of "Group specs". These specs
    currently come in three different flavours: `alfred3_interact.ParallelSpec`
    for parallel (synchronous) groups, `alfred3_interact.SequentialSpec` for sequential
    (asynchronous) groups, and `alfred3_interact.IndividualSpec` for
    "groups" of size one. The latter allow you to include individual-sized
    conditions in group experiments via `match_random` and `match_chain`.
    You can use group specs to control the maximum number of groups that
    should be created based on a specific spec via their parameter `nslots`.

- We changed the admin facilities to use the new admin mode introduced
  in alfred3 v2.2.0. You can now add `alfred3_interact.MatchMakerActivation`
  and `alfred3_interact.MatchMakerMonitoring` to your experiment
  individually.

## alfred3_interact v0.1.9 (Released 2021-06-17)

### Added v0.1.9

#### MatchMaker

- New method `MatchMaker.check_activation` allows you to check whether
  the MatchMaker is activated at any time in an experiment. This
  can be useful, if tha actual matching takes place at some later point
  in an experiment: In this case, it is sensible to only allow
  participants to progress, if they will actually be matched.

#### Chat

- New argument `room` for `ChatElement` and `Group.chat`. This argument
  offers a convenient way to create distinct chat-rooms for the same
  group of participants. Just enter a string as the group name; you may,
  for instance, want to use a page name.


## alfred3_interact v0.1.8 (Released 2021-06-09)

### Changed

- alfred3_interact was updated for compatibility to alfred3 v2.1.5

## alfred3_interact v0.1.7 (Released 2021-05-28)

### Fixed v0.1.7

- Fixed #7


## alfred3_interact v0.1.6 (Released 2021-05-28)

### Changed v0.1.6

- The admin view now includes the start date of each member's session.

### Fixed v0.1.6

- Improved the fix of #6. The fix in v0.1.5 was incomplete.
- Fixed a bug in ping handling of groupwise matching.


## alfred3_interact v0.1.5 (Released 2021-05-27)

### Changed v0.1.5

- Changed the way repeated calls are made during matchmaking (adressing in the process #1). Now, the `MatchingPage` and the `WaitingPage` operate almost identically, both using repeated AJAX calls originating from the client's browser. Hopefully, this will further increase the robustness of waiting and matchmaking. **This removes the arguments 'match_timeout', 'timeout_page', and 'raise_exception' from `match_groupwise`**

### Fixed v0.1.5

- Fixed #7
- Fixed #6


## alfred3-interact v0.1.4 (Released 2021-05-18)

### Fixed v0.1.4

- Version v0.1.3 introduced a bug on the `MatchingPage`: The page did not
  correctly hide its navigation buttons. This update fixes the bug.

## alfred3-interact v0.1.3 (Released 2021-05-18)

### Changed v0.1.3

- Improved cooperation of two MatchMakers in one experiment (#4)
- Improved robustness of groupwise matching (#3)

## alfred3-interact v0.1.2 (Released 2021-05-14)

### Added v0.1.2

- `alfred3_interact.Chat` gains the new parameter *you_label*.
- `alfred3_interact.WaitingPage` gains the parameters *wait_timeout_page*
  and *wait_exception_page*, thereby allowing users to customize the
  pages shown to participants if the experiment is aborted while waiting.

### Fixed v0.1.2

- Decryption of loaded messages in chat element
- In some corner cases, the chat element displayed the same message
  twice. This release fixes this bug.

## alfred3-interact v0.1.1 (Released 2021-04-21)

### Fixed v0.1.1

- The HTML and JavaScript templates used in the package were not correctly
  added to the package, so that the package distributed via pypi did
  not work. This release fixes that problem.
