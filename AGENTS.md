# AGENTS.md

This file is the Codex entrypoint for repo instructions.

## Instruction Precedence

For Codex, follow instructions in this order:

1. Active Codex system and developer instructions.
2. Current user instructions for the task.
3. This `AGENTS.md` file.
4. `CLAUDE.md` as the canonical project instruction file.

## Canonical Instructions

Read and follow [CLAUDE.md](CLAUDE.md) as the canonical project instruction file.
Do not duplicate its content here. Treat every repository rule, architecture note,
documentation requirement, environment note, and workflow constraint in
`CLAUDE.md` as applying to Codex too.

## Backlog Rule

The Backlog.md workflow in `CLAUDE.md` applies to Codex. Start each project
request by running `backlog instructions overview`, then decide whether a task is
needed.

## Codex Translation Rules

When `CLAUDE.md` refers to Claude Code, translate that instruction to Codex:

- "Claude Code" means "Codex" for this repo.
- "Claude Code CLI" means Codex CLI or this Codex coding session, as applicable.
- The path and filesystem rules still apply exactly as written.

## Codex-Specific Caveats

- Follow the active system and developer instructions for this Codex session first.
- If a `CLAUDE.md` instruction conflicts with higher-priority Codex system or
  developer instructions, follow the higher-priority instruction and note the
  conflict when relevant.
- Do not assume Claude-specific tools or UI behavior exist in Codex. Use the
  tools available in the current Codex session.
- Preserve existing uncommitted user changes. Do not revert unrelated files.

## Shared Agent Skills

Project skills have a single canonical location: `.agents/skills/`.

`.claude/skills` is a relative symlink to `.agents/skills`, so Claude Code
auto-discovers the same skills natively. Any change under `.agents/skills/` is
immediately visible to both agents.

- Edit skills only under `.agents/skills/`.
- Do not replace the `.claude/skills` symlink with a real directory or create
  separate copies there.
- Keep skill wording agent-neutral unless there is a clear agent-specific
  reason to diverge.

## Future Updates

Keep [CLAUDE.md](CLAUDE.md) as the single canonical instruction body for both
Claude Code and Codex.

When project instructions change:

1. Update `CLAUDE.md`.
2. Update this `AGENTS.md` only if the Codex redirect, translation rules, or
   Codex-specific caveats themselves need to change.

Do not re-copy the full `CLAUDE.md` content into this file.

## One documented exception to the Backlog rule

The Backlog block below says never to edit Backlog markdown directly. That holds
for tasks, drafts, documents and milestones, all of which have CLI paths for
their content.

**Decisions are the exception.** `backlog decision create <title> [-s status]`
accepts only a title and a status — there is no `--content` flag, no `update`
subcommand and no MCP tool — so the CLI scaffolds the frontmatter, id and section
headings, and the author writes the body into the file. That is the intended
workflow, not a workaround. Leave the frontmatter untouched; the CLI owns it.
See `CONTRIBUTING.md`.

<!-- BACKLOG.MD GUIDELINES START -->
<CRITICAL_INSTRUCTION>

## Backlog.md Workflow

This project uses Backlog.md for task and project management.

**For every user request in this project, run `backlog instructions overview` before answering or taking action.**

Use the overview to decide whether to search, read, create, or update Backlog tasks.

Use the detailed guides when needed:
- `backlog instructions task-creation` for creating or splitting tasks
- `backlog instructions task-execution` for planning and implementation workflow
- `backlog instructions task-finalization` for completion and handoff

Use `backlog <command> --help` before running unfamiliar commands. Help shows options, fields, and examples.

Do not edit Backlog task, draft, document, decision, or milestone markdown files directly. Use the `backlog` CLI so metadata, relationships, and history stay consistent.

</CRITICAL_INSTRUCTION>
<!-- BACKLOG.MD GUIDELINES END -->
