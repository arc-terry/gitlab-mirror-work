# Copilot Instructions for this Repository

## Build, test, and lint commands

This repository is a single Python script (`mirror.py`) and does not currently define a build system, test suite, or lint configuration (`pytest`, `unittest` test files, `ruff`, `flake8`, `mypy`, etc. are not present).

Use these commands during development:

```bash
# Install runtime dependency used by mirror.py
pip install requests

# Run the script (dry-run by default)
SRC_GITLAB=... DST_GITLAB=... SRC_TOKEN=... DST_TOKEN=... SRC_ROOT_GROUP=... python3 mirror.py
```

There is no repository-defined “single test” command yet.

## High-level architecture

`mirror.py` is an end-to-end GitLab group migration tool that mirrors nested groups and projects from a source GitLab to a target GitLab.

Core flow in `main()`:
1. Load `.lastconfig.env` defaults, then read required/optional environment variables at module import time.
2. Run `preflight_report()`:
   - verify source/target connectivity and permissions,
   - recursively discover all source groups/projects via `collect_source_tree()`,
   - show a create/mirror plan and sample source/target Git URLs.
3. Confirm execution (`confirm_before_process()`), with `DRY_RUN=true` as safe default.
4. Ensure target root chain exists (`ensure_group_path()`).
5. Recurse through source groups (`migrate_group_recursive()`):
   - create missing target groups/projects through GitLab API,
   - mirror each project via persistent local bare cache under `repositories_mirror-use` (`git fetch --prune` + `git push --mirror`).
6. Write latest runtime config snapshot to repository-root `.lastconfig.env` (tokens excluded).
7. Write run logs to repository-root `.lastlog` (refreshed/truncated at each script start).

Functional layers:
- **Config + behavior flags:** top-level env parsing (`DRY_RUN`, `AUTO_CONFIRM`, `PUSH_EXISTING_PROJECTS`, `CONTINUE_ON_ERROR`, SSL/protocol options).
- **API layer:** `api_request`/`api_get`/`api_post` and object lookup/list helpers.
- **Path translation:** `map_source_to_target_path()` maps source namespace under `SRC_ROOT_GROUP` to target `DST_ROOT_GROUP`.
- **Git execution:** `run()` and `mirror_project()` perform actual clone/push operations and SSL env wiring for Git.
- **Local mirror cache:** `ensure_local_mirror()` reuses valid bare repos and re-clones when a conflicting non-bare path exists.
- **Config persistence:** `.lastconfig.env` stores latest non-secret runtime config and is loaded as defaults on next run.
- **Log persistence:** `init_lastlog()` truncates `.lastlog` each run; `log()` writes to both stdout and `.lastlog`.

## Key conventions in this codebase

- Required env vars are resolved at import time after `.lastconfig.env` defaults are loaded.
- `TARGET_DEV_BRANCH_PREFIX` is required: use real prefix to enable preserve-prefix behavior, or `NONE` to disable.
- Safety defaults are intentional: `DRY_RUN=true`, `AUTO_CONFIRM=false`.
- All source→target namespace mapping must go through `map_source_to_target_path()`; do not hand-build target paths.
- GitLab listing is page-aware only through `api_get()` (follows `resp.links["next"]`). Reuse it for list endpoints.
- Existence checks are explicit 404-aware wrappers (`get_group_by_full_path`, `get_project_by_full_path`) returning `None` on not found.
- Per-project failures are logged inside `migrate_group_recursive()` and only abort when `CONTINUE_ON_ERROR=false`.
- Existing target projects are still mirrored when `PUSH_EXISTING_PROJECTS=true` (default), so behavior is not “create-only.”
- Subgroup creation visibility is clamped by parent visibility to avoid invalid GitLab combinations (for example, public child under private parent).
- `.lastlog` lives at repository root and always contains the latest execution output (not cumulative history).
- `.lastconfig.env` lives at repository root and contains latest non-secret config only (never tokens).

## Development discussion records policy

- Track development discussions under `doc/dev/` with filename format:
  - `doc/dev/<status>_<topic>.md`
- Allowed `<status>` values:
  - `todo`
  - `planning`
  - `developing`
  - `finished`
  - `pending`
- `<topic>` must be a lowercase hyphenated slug that reflects the user question.
- When status changes, rename the file to the new status prefix (for example, `planning_x.md` -> `developing_x.md`).
- Each discussion record should contain:
  - question/topic summary
  - decisions
  - pros/cons or tradeoffs
  - implementation next steps (if any)

### Pending implementation hint behavior

- At the start of every new user request, check for:
  - `doc/dev/planning_*.md`
  - `doc/dev/developing_*.md`
- If any exist, add a concise reminder that implementation tasks are still pending.
