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
1. Read required/optional environment variables at module import time.
2. Run `preflight_report()`:
   - verify source/target connectivity and permissions,
   - recursively discover all source groups/projects via `collect_source_tree()`,
   - show a create/mirror plan and sample source/target Git URLs.
3. Confirm execution (`confirm_before_process()`), with `DRY_RUN=true` as safe default.
4. Ensure target root chain exists (`ensure_group_path()`).
5. Recurse through source groups (`migrate_group_recursive()`):
   - create missing target groups/projects through GitLab API,
   - mirror each project via persistent local bare cache under `repositories_mirror-use` (`git fetch --prune` + `git push --mirror`).
6. Write run logs to repository-root `.lastlog` (refreshed/truncated at each script start).

Functional layers:
- **Config + behavior flags:** top-level env parsing (`DRY_RUN`, `AUTO_CONFIRM`, `PUSH_EXISTING_PROJECTS`, `CONTINUE_ON_ERROR`, SSL/protocol options).
- **API layer:** `api_request`/`api_get`/`api_post` and object lookup/list helpers.
- **Path translation:** `map_source_to_target_path()` maps source namespace under `SRC_ROOT_GROUP` to target `DST_ROOT_GROUP`.
- **Git execution:** `run()` and `mirror_project()` perform actual clone/push operations and SSL env wiring for Git.
- **Local mirror cache:** `ensure_local_mirror()` reuses valid bare repos and re-clones when a conflicting non-bare path exists.
- **Log persistence:** `init_lastlog()` truncates `.lastlog` each run; `log()` writes to both stdout and `.lastlog`.

## Key conventions in this codebase

- Required env vars are accessed with `os.environ[...]` at import time. Missing values fail immediately before `main()` runs.
- Safety defaults are intentional: `DRY_RUN=true`, `AUTO_CONFIRM=false`.
- All source→target namespace mapping must go through `map_source_to_target_path()`; do not hand-build target paths.
- GitLab listing is page-aware only through `api_get()` (follows `resp.links["next"]`). Reuse it for list endpoints.
- Existence checks are explicit 404-aware wrappers (`get_group_by_full_path`, `get_project_by_full_path`) returning `None` on not found.
- Per-project failures are logged inside `migrate_group_recursive()` and only abort when `CONTINUE_ON_ERROR=false`.
- Existing target projects are still mirrored when `PUSH_EXISTING_PROJECTS=true` (default), so behavior is not “create-only.”
- Subgroup creation visibility is clamped by parent visibility to avoid invalid GitLab combinations (for example, public child under private parent).
- `.lastlog` lives at repository root and always contains the latest execution output (not cumulative history).
