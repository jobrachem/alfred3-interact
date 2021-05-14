# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## alfred3-interact v0.1.2 [unreleased]

### Added

- `alfred3_interact.Chat` gains the new parameter *you_label*.
- `alfred3_interact.WaitingPage` gains the parameters *wait_timeout_page*
  and *wait_exception_page*, thereby allowing users to customize the
  pages shown to participants if the experiment is aborted while waiting.

### Fixed

- Decryption of loaded messages in chat element
- In some corner cases, the chat element displayed the same message
  twice. This release fixes this bug.

## alfred3-interact v0.1.1 (Released 2021-04-21)

### Fixed

- The HTML and JavaScript templates used in the package were not correctly
  added to the package, so that the package distributed via pypi did
  not work. This release fixes that problem.