---
id: ARC-054
title: 'Align README and USER_GUIDE, and add worked example prompts'
status: Done
assignee:
  - '@claude'
created_date: '2026-07-28 11:28'
updated_date: '2026-07-28 11:31'
labels: []
dependencies: []
priority: high
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
README.md and docs/USER_GUIDE.md disagree about how to install and connect to this server, because the USER_GUIDE predates the PyPI release and was never updated for it. A user arriving from the PyPI page, where the README tells them "nothing to clone", follows the link to the User Guide and is told to `git clone <repository-url>`.

Confirmed misalignments:
1. USER_GUIDE "Installation" is checkout-only. There is no uvx, pipx or pip path anywhere in the document, and the clone command still has a `<repository-url>` placeholder.
2. USER_GUIDE line 97 says the application is "named archimate-mcp". That was renamed to mcp-archimate in 0.7.1 (ARC-053).
3. The two documents give different MCP client configuration. README uses server key "archimate" with `uvx mcp-archimate`; USER_GUIDE uses key "archimate-mcp" with `uv --directory <path> run python -m ...`. Both work, but a reader following both gets contradictory instructions.
4. USER_GUIDE covers only MCP Inspector and Claude Desktop. README covers Claude Code, Claude Desktop, Codex and Inspector. Claude Code and Codex users find nothing in the reference document.
5. USER_GUIDE never mentions the filesystem trust model or SECURITY.md, so the reference document is silent on the one thing a user should know before pointing an agent at their disk.

Also wanted: worked example prompts in the README. It currently has three one-line prompts, which show the shape but do not show what a real session looks like — particularly for editing and improving an existing model, which is the common case after the first build and is currently unrepresented.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A reader can install and connect from either document without contradiction
- [x] #2 Both documents use the same MCP client configuration, server key and command
- [x] #3 USER_GUIDE documents the uvx install path first and the source checkout as the contributor path
- [x] #4 USER_GUIDE covers the same four clients as the README
- [x] #5 No document refers to the server as archimate-mcp or leaves a placeholder URL
- [x] #6 README carries example prompts covering create, explore, edit, improve, validate/export and one full build
- [x] #7 USER_GUIDE points to the security model rather than being silent on it
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The root problem was that USER_GUIDE.md was written before the PyPI release and never revisited. Its Installation section opened with 'git clone <repository-url>' while the README opened with 'Nothing to clone' — the two documents disagreed on the very first instruction a new user reads.

USER_GUIDE changes: Installation now leads with uvx and demotes the checkout to a contributor path with the real clone URL; Running The Server drops the repository-root assumption; Connecting From MCP Clients now covers the same four clients as the README (Claude Code, Claude Desktop, Codex, Inspector) with identical config, including the same server key 'archimate' so prompts stay portable between the documents; a new Security Model section summarises the filesystem and untrusted-input posture and points at SECURITY.md, which the reference document had been silent on.

Fixed the stale 'named archimate-mcp' (renamed in 0.7.1) and the mcp[cli] paragraph, which described Claude Desktop install workflows that no longer exist. Requirements no longer claims uv is required — it is not, if you pip install.

Added two troubleshooting entries for the questions this setup actually generates: a client showing no tools (now says to verify with the Inspector against uvx, so the reader can tell a broken server from a broken config), and 'the server seems to hang', which is correct stdio behaviour and looks like a fault.

README: replaced three one-line prompts with a six-part Example prompts section — build something small, explore, edit, improve, validate/export, and the full ecommerce build the author supplied. Edit and improve were entirely unrepresented before, despite being the common case after the first model exists.

Deliberately avoided <details>/<summary> collapsing for the long example: the README is the PyPI long_description, and PyPI's HTML sanitiser is a narrower allowlist than GitHub's, so a collapsed block risks rendering as stripped or raw markup on the project page.

Verified rather than assumed: every tool name cited in either document was checked against the 45 actually registered via mcp.list_tools(); all internal anchors resolve (across all six heading levels — an earlier check that only scanned h2-h4 produced a false 'broken anchor' report); and every relative file link in both documents resolves.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Aligned README.md and docs/USER_GUIDE.md, which had contradicted each other on installation since the PyPI release — the README said 'nothing to clone' while the User Guide said to clone a placeholder URL. USER_GUIDE now leads with uvx, covers the same four MCP clients with identical configuration and the same server key, carries a Security Model section it previously lacked, and drops the stale archimate-mcp name and the obsolete mcp[cli] install workflows. Added two troubleshooting entries for the failures this setup actually produces. README gained a six-part Example prompts section covering build, explore, edit, improve, validate/export and one full end-to-end build, with edit and improve newly represented. Verified all 45 cited tool names exist, all internal anchors resolve and all relative links resolve; 179 tests and ruff still pass.
<!-- SECTION:FINAL_SUMMARY:END -->
