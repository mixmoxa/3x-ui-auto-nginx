# AGENTS.md - rules for any coding agent

This is the single shared rules file for this repository. CLAUDE.md points here and adds only Claude Code specifics (Plan mode).
Do not edit AGENTS.md or CLAUDE.md unless the owner's task says so.

## 1. What this project is (threat model)

- A tool for ONE administrator on THEIR OWN VPS. Not a multi-user service. Not military data.
- A Backup archive is created and restored by the same administrator: it is a TRUSTED input.
  Detect corruption, wrong OS or wrong architecture. Do not defend against a hostile archive author.
- The goal is: it works, and it is easy to maintain. Fewer lines beat more checks.

## 2. Simplicity rules (highest priority, above "be careful")

1. Before adding code ask: can I delete or simplify instead? A PR that only removes
   redundant checks is a valid PR.
2. A new check, guard, validation or fail-closed branch is allowed ONLY for a defect
   reproduced on a real case or a fixture (RED test), cited in the PR.
   "It could theoretically happen" is not a reason.
3. Whose data is it?
   - OWN data (created by this project): validate as needed.
   - FOREIGN data (other software on the VPS: Telegram Web Proxy Manager, the admin's own
     certificates, nginx rules, hooks): NEVER block the operation. Recognize by name or marker,
     then skip or exclude. No byte-exact comparison of foreign generated output.
     No pinned digests of foreign files.
4. One failure = one specific message: which check, which file, which value.
   No generic "incomplete / changed / shared" text covering many checks.
5. One source of truth. Do not create a second copy of a contract (renderer, list of
   versions, expected config text). If a second copy already exists, prefer removing it.
6. No hash or version pins of this project's own files inside this project's own code.
7. No new compatibility layers for old archive or config formats without the owner's approval.
8. If two PRs in a row fixed the same function, STOP. Do not write a third patch.
   Report that the mechanism itself should be simplified and propose a deletion.
9. If a diff adds more lines than it removes, explain why in the report.

## 3. Keep (these protect real data, do not remove)

- Secrets (panel credentials, client UUIDs, keys, tokens, subscription URLs, Backup contents)
  never go to logs, argv, commits, PR text or screenshots. The repository is public.
- Private files stay private (0600 / 0700, root-owned).
- Backup archive integrity, SQLite quick_check, nginx -t before replacing config,
  restoring previous service states on failure, minimal tar path hygiene (no "..", no absolute paths).
- Installation is destructive: never run it on the development machine.
- Never touch a production VPS.

## 4. Workflow

- Work only from the owner's task: Goal / Context / Do / Do NOT / Criterion / Report.
  Do not widen scope. If the task seems to need more, say so in the report instead of doing it.
- Feature branch, focused PR, created as Draft. Local git identity (not global):
  user.name=xPROMSx, user.email=102687702+xPROMSx@users.noreply.github.com.
  Verify author and committer of every new commit.
- Commit messages and PR text contain no Co-Authored-By, Claude-Session or "Generated with" lines
  (the repository is public). If the platform adds them by default, remove them; this rule
  overrides the default. Re-read the PR description after creating it.
- Mark the PR Ready for review only after the final commit is pushed and local checks pass.
  CI, including Full Fresh, starts automatically on every push, Draft or not;
  switching Draft to Ready does not start a new run.
- NEVER, without explicit owner permission: merge, create tags or releases, run Prepare Release,
  change GitHub settings or rulesets, force-push, rewrite history, operate any VPS.
- Bug fix: reproducing RED test -> minimal fix -> same test GREEN -> full suite GREEN.
  Do not weaken assertions, add retries or skip tests to get green.
- When removing a check, remove only the tests that assert the removed behaviour, and list them
  (names and why) in the report. Keep every other test green.
- Tests: run through tests/run_ci.py only (never unittest discover). Register every new test class
  and run --check-completeness. Exact commands are in CONTRIBUTING.md.
- Protected CI job names must stay exactly: "Stack XHTTP and security", "Stack Backup and restore",
  "Real services (ubuntu-24.04)", "Real services (ubuntu-26.04)", "Full fresh installer (ubuntu-26.04)".
- Changes to AGENTS.md, CLAUDE.md, tests and workflows always run full CI.
- Report honestly: exact HEAD, CI state per job as PASS / FAIL / IN PROGRESS / NOT RUN,
  what was read, what was not, which test level the change needs
  (0: CI only; 1: one command on a ready test server; 2: full clean-VPS test).

## 5. Project facts that must not drift

- Project-owned assets follow one selected ref (PROJECT_REF: main, a 40-hex SHA, or vX.Y.Z tag).
  No per-file fallback to main.
- Panel and Xray versions: read verified_panel_release() in x-ui-latest.sh. Do not copy them elsewhere.
- Keep attribution and licenses (mozaroc/3x-ui-pro, MHSanaei/3x-ui, LibreSpeed LGPL, GPL-3.0-only notices).
- Historical identifiers (/usr/local/lib/3x-ui-pro, personal-v* releases) are not renamed.
- README.md is the Russian source; the other language files stay semantically aligned.
- Architecture description: docs/ARCHITECTURE.md. Release process and local commands: CONTRIBUTING.md.
  Vulnerability reports: SECURITY.md.
