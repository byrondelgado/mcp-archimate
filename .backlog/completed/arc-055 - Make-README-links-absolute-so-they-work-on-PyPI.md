---
id: ARC-055
title: Make README links absolute so they work on PyPI
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 12:11'
updated_date: '2026-07-28 12:11'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
README.md is the PyPI long_description. Relative markdown links resolve against the PyPI project page rather than the repository, so every one of them 404s there: [User Guide](docs/USER_GUIDE.md) becomes https://pypi.org/project/mcp-archimate/docs/USER_GUIDE.md.

Thirteen links are affected, including the license badge, both User Guide references, the whole Documentation table, and the SECURITY and CONTRIBUTING pointers — that is every navigational link a PyPI visitor would try.

Rewrite them as absolute github.com URLs against main. Directory references use /tree/main/, files use /blob/main/.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 No relative markdown link remains in README.md
- [x] #2 Every rewritten link resolves with HTTP 200
- [x] #3 Links still work when the README is viewed on GitHub
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Rewrote all twelve relative README links as absolute github.com URLs. README.md is the PyPI long_description, so relative links resolved against the project page and every one 404'd there — including the license badge, both User Guide references and the entire Documentation table. Also promoted the .backlog/decisions reference from plain code to a real link. Verified each of the twelve returns HTTP 200; they render identically on GitHub, since absolute URLs work in both places.
<!-- SECTION:FINAL_SUMMARY:END -->
