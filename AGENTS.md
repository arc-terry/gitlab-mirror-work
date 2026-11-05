# Repository Instructions

Shared project overview and development guidance for coding agents.

## Purpose

`mirror-work` is a single-script Python 3 tool (version `1.0`) for mirroring a
GitLab group hierarchy and its projects between GitLab instances. It uses the
GitLab REST API v4 for discovery and creation, and the Git CLI for repository
history and refs. Projects are processed sequentially.

It does not migrate issues, merge-request metadata, wikis, CI/CD pipelines, or
other GitLab application data.

## File map

| Path | Role |
| --- | --- |
| `mirror.py` | Entire application: configuration, API helpers, discovery, creation, Git operations, logging, and entry point. |
| `README.md` | Setup, environment variables, usage examples, and limitations. |
| `CHANGELOG.md` | Version `1.0` feature summary. |
| `AGENTS.md` | Shared repository overview, architecture, and development conventions. |
| `tests/test_logging.py` | Regression tests for grouped repository output and terminal-only heading color. |
| `docs/superpowers/specs/` | Dated feature designs, including migrated completed design records. |
| `docs/superpowers/plans/` | Location for future executable implementation plans; none currently migrated. |
| `.gitignore` | Excludes local configuration, logs, bytecode, and mirrored repositories. |
| `.lastconfig.env` | Ignored local defaults from the previous run; excludes tokens. |
| `.lastlog` | Ignored latest run output, truncated at application startup. |
| `log/` | Ignored historical run logs with appended command traces; older runs may have separate command reports. |
| `repositories_mirror-use/` | Ignored persistent bare Git repository cache, organized by source project path. |
| `__pycache__/` | Generated Python bytecode. |

## Execution flow

1. Handle `--help` / `-h` or `--version` / `-V` before requiring configuration.
2. Load `.lastconfig.env` defaults, then parse environment variables at module
   import time. Existing environment values take precedence.
3. `main()` resets `.lastlog` and atomically saves the non-secret runtime config.
4. `preflight_report()` checks group access, recursively discovers the source
   tree, and reports existing/missing target groups and projects.
5. Confirm a real run, then ensure the destination root group chain exists.
6. `migrate_group_recursive()` creates missing groups/projects and mirrors each
   project unless existing-project pushes are disabled.
7. `mirror_project()` reads source/target refs using `git ls-remote --refs` and
   classifies creates, updates, deletions, and preserved target-only branches.
   - Dry run: print the diff without creating repositories or pushing.
   - Real run: confirm deletions, clone/reuse the bare cache, fetch with pruning,
     remove GitLab-internal refs, configure the push URL, fetch preserved target
     branches when needed, then run `git push --mirror`.
8. The entry point archives the latest log and appends a numbered command trace,
   including when execution fails or is interrupted.

## Functional layers

- **Configuration:** top-level environment parsing and `load_last_config_defaults()`.
- **API:** `api_request()`, paginated `api_get()`, dry-run-aware `api_post()`,
  and group/project lookup and listing helpers.
- **Namespace mapping:** `map_source_to_target_path()` translates source paths
  under `SRC_ROOT_GROUP` to `DST_ROOT_GROUP` and rejects paths outside the root.
- **Git execution:** `run()`, `mirror_project()`, and push diagnostics; Git SSL
  settings are supplied through `git_command_env()`.
- **Cache:** `ensure_local_mirror()` validates and reuses bare repositories or
  removes conflicting paths before cloning.
- **Persistence:** config snapshots exclude tokens; `log()` writes stdout and
  `.lastlog`; archives append numbered commands in a `COMMAND TRACE` section.

## Configuration and running

Requirements: Python 3, Git CLI, and `requests` (`urllib3` is also imported).
SSH operations require working keys and host access.

```bash
pip install requests
python3 mirror.py --help
python3 mirror.py --version
```

Example with explicit safe settings:

```bash
SRC_GITLAB=https://source.example.com \
DST_GITLAB=https://target.example.com \
SRC_TOKEN='<source-token>' \
DST_TOKEN='<target-token>' \
SRC_ROOT_GROUP=company/engineering \
TARGET_DEV_BRANCH_PREFIX=NONE \
DRY_RUN=true \
VERIFY_SSL=true \
python3 mirror.py
```

- Required settings: `SRC_GITLAB`, `DST_GITLAB`, `SRC_TOKEN`, `DST_TOKEN`,
  `SRC_ROOT_GROUP`, and `TARGET_DEV_BRANCH_PREFIX` (a prefix or `NONE`).
- `DST_ROOT_GROUP` defaults to the source root.
- Built-in defaults: `DRY_RUN=true`, `AUTO_CONFIRM=false`, `VERIFY_SSL=true`,
  `PUSH_EXISTING_PROJECTS=true`, and `CONTINUE_ON_ERROR=true`.
- Git defaults: HTTPS source, SSH destination. Custom SSH ports and
  `GIT_SSL_CAINFO` are supported.
- Tokens must come from the environment, never `.lastconfig.env`.
- Local saved settings override built-in defaults. The inspected snapshot has
  dry run enabled, SSL verification disabled, and preservation prefix
  `arc-hsinchu`; do not assume those are appropriate for another run.

## Safety and implementation caveats

- `git push --mirror` can force-update or delete destination refs. Real runs
  require `YES`; deletion candidates require a further confirmation unless
  `AUTO_CONFIRM=true`.
- Prefix preservation is intended for target-only branches under
  `refs/heads/<prefix>/`, not general protection of all matching branches.
- Dry run still contacts GitLab/Git remotes and writes local config and logs.
- Real runs remove a conflicting non-bare path at the expected cache location.
- GitLab-internal merge-request, pipeline, and environment refs are removed
  from the local mirror before pushing; dry-run comparisons do not filter them,
  so the preview can include refs that will not actually be pushed.
- `migrate_group_recursive()` logs per-project errors and continues unless
  `CONTINUE_ON_ERROR=false`. A final success message or zero exit status does
  not establish that every project succeeded; inspect `[ERROR]` entries.
- Command traces redact configured token strings, but other command logging and
  Git remote configuration may contain token-bearing URLs. Treat logs/cache as
  sensitive; token-free config snapshots do not make all artifacts secret-free.
- This is a mirror utility, not a complete GitLab backup or a concurrent service.

## Development guidance

- Logging regression tests live in `tests/test_logging.py`; run
  `python3 -m unittest discover -s tests -v`. There is no build system, lint
  configuration, or dependency manifest. Help/version commands are lightweight
  smoke checks; they still require the imported dependencies.
- Importing `mirror.py` requires runtime environment settings and loads saved
  defaults; account for this when adding tests.
- All namespace translation must use `map_source_to_target_path()`; do not
  hand-build target paths. Use `api_get()` for paginated listing (it follows
  `resp.links["next"]`) and the existing 404-aware lookup helpers, which return
  `None` for missing groups/projects.
- Preserve dry-run guards, confirmation gates, and parent-group visibility
  clamping when changing behavior.

## Design and implementation records

- Save designs to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`.
- Save implementation plans to `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md`.
- Follow the installed Superpowers brainstorming and writing-plans requirements
  for new designs and plans, including design approval before implementation.
- Designs describe intent, goals/non-goals, constraints, approaches, decisions,
  and any remaining choices. Plans link to their design and specify exact files,
  interfaces, test-first steps, and verification commands.
- Migrated historical designs must identify their provenance and completion
  status. Do not treat completed records as pending implementation or invent
  retrospective approvals, plans, or test evidence.

## Review scope

The initial overview read all existing root-level files, the complete application,
and the project documentation then available, including previous tool-specific
instructions and development records. The local log reviewed at that time
records a dry run scanning 3 groups and 13 projects; it is historical
output, not verification of current remote state. Nested cached Git contents,
Git internals, bytecode, and archived logs were not read individually. No
network mirror operation was run for this overview.
