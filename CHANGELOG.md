# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## alfred3_interact v0.2.0 [unreleased]

### Added

#### MatchMaker

- `MatchMaker.check_activation`
- You can now tell the `MatchMaker` to collect only a certain number
  of groups with the arguments `max_groups` and `max_groups_mode`.
  Check out the documentation for more! **NOTE that this feature requires
  alfred3 v2.1.7 or newer!**
- New method `MatchMaker.check_group_number` gives you the possibility
  to check for the number of collected groups and abort the experiment
  if necessary at any time in the experiment.
- New attribute `MatchMaker.full` returns *True* if the maximum number of
  groups has been reached.

#### Group

- `Group.sessions`

#### Chat
- `room`

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
