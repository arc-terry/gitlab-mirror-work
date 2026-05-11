# Technical Details

This document describes the internals of `mirror.py` — a GitLab nested-group
mirroring tool.

## Execution Flow

```
startup
 ├─ load_last_config_defaults()   load .lastconfig.env defaults (if exists)
main()
 ├─ init_lastlog()                truncate .lastlog
 ├─ write_last_config_snapshot()  refresh .lastconfig.env (tokens excluded)
 ├─ preflight_report()
 │   ├─ verify source/target connectivity
 │   ├─ collect_source_tree()  recursive group/project discovery
 │   └─ show create/mirror plan + sample Git URLs
 ├─ confirm_before_process()   prompt unless DRY_RUN or AUTO_CONFIRM
 ├─ ensure_group_path()        create target root group chain
 └─ migrate_group_recursive()
      ├─ create_group_if_missing()
      ├─ for each project:
      │    ├─ create_project_if_missing()
      │    └─ mirror_project()
      │         ├─ ensure_local_mirror()   clone or fetch --prune
      │         └─ git push --mirror       to target
      └─ recurse into subgroups
```

## GitLab API v4 Usage

All API communication goes through three helpers:

| Helper        | Purpose                                |
|---------------|----------------------------------------|
| `api_request` | Low-level call (any HTTP method)       |
| `api_get`     | Paginated GET — follows `Link: next`   |
| `api_post`    | POST with automatic dry-run guard      |

Authentication uses `PRIVATE-TOKEN` header with personal access tokens.

Pagination is handled automatically in `api_get`: the function follows
`resp.links["next"]` until no more pages remain, collecting all results
into a single list.

### Endpoints used

| Endpoint                              | Operation                |
|---------------------------------------|--------------------------|
| `GET /groups/:id`                     | Lookup group by path     |
| `GET /projects/:id`                   | Lookup project by path   |
| `GET /groups/:id/subgroups`           | List subgroups           |
| `GET /groups/:id/projects`            | List projects in group   |
| `POST /groups`                        | Create group             |
| `POST /projects`                      | Create project           |

Path parameters (group/project full paths) are URL-encoded via
`urllib.parse.quote`.

## Git Mirroring Mechanism

Each project is mirrored through a **local bare repository cache** stored
under `repositories_mirror-use/`.

### Steps per project

1. **Ensure local mirror** (`ensure_local_mirror`):
   - If a valid bare repo already exists → `git fetch --prune origin`
     (incremental update).
   - If the path exists but is not a valid bare repo → remove and re-clone.
   - Otherwise → `git clone --mirror <source_url>`.

2. **Set push target** → `git remote set-url --push origin <target_url>`.

3. **Preserve optional target prefix refs** (if configured):
   - fetch `refs/heads/<TARGET_DEV_BRANCH_PREFIX>/*` from target into local mirror.
4. **Push** → `git push --mirror` to the target GitLab.

### Dry-run ref-diff report

When `DRY_RUN=true`, project mirroring switches to a read-only comparison mode:

1. Read source refs via `git ls-remote --refs <source_url>`
2. Read target refs via `git ls-remote --refs <target_url>`
   - If the target project is planned for creation, target refs are treated as empty.
3. Classify differences:
   - **to-create**: ref exists only in source
   - **to-update**: ref exists on both sides with different SHA
   - **to-delete**: target-only ref not under preserved prefix
   - **preserved-target-only**: target-only ref under `refs/heads/<TARGET_DEV_BRANCH_PREFIX>/*`

The script logs summary counts and full per-category ref lists, so dry-run shows
exactly what is not yet mirrored.

### URL construction

| Protocol | Format                                                |
|----------|-------------------------------------------------------|
| HTTPS    | `https://oauth2:<token>@host/group/project.git`       |
| SSH      | `git@host:group/project.git` or `ssh://git@host:port/…` |

Source defaults to HTTPS (token-embedded); target defaults to SSH.

## Safety Design

The script ships with conservative defaults to prevent accidental damage:

| Flag                   | Default | Effect                                           |
|------------------------|---------|--------------------------------------------------|
| `DRY_RUN`              | `true`  | No API writes/push; run read-only ref diff checks |
| `AUTO_CONFIRM`         | `false` | Prompt `Type YES` before real execution           |
| `CONTINUE_ON_ERROR`    | `true`  | Log per-project failures, keep going              |
| `PUSH_EXISTING_PROJECTS` | `true` | Re-push into existing target projects            |
| `TARGET_DEV_BRANCH_PREFIX` | **required** | Preserve target-only branches under this prefix (`refs/heads/<prefix>/*`), or set `NONE` to disable |

When `DRY_RUN=true`, `api_post` returns `None` and mutating git operations
(`clone`, `fetch`, `push`) are skipped. Read-only `ls-remote` checks are used
to produce the pending-change report.

## Deletion Confirmation Gate

In real mode (`DRY_RUN=false`), the script computes non-preserved delete
candidates before push. If such refs exist:

- with `AUTO_CONFIRM=false`: it prompts
  `Delete <N> non-preserved target refs? [y/N]`
- with `AUTO_CONFIRM=true`: it auto-approves and logs that decision.

If the prompt is rejected, that project's mirror push is skipped.

## Runtime Configuration Snapshot

The script maintains a latest runtime configuration snapshot at:

- `.lastconfig.env` (repository root, `KEY=VALUE` format)

Read/write behavior:

1. On startup, if `.lastconfig.env` exists, values are loaded as defaults.
2. Current-run environment variables override loaded defaults.
3. After normalization/validation, the script overwrites `.lastconfig.env`
   with the latest non-secret configuration.

Secret handling:

- `SRC_TOKEN` and `DST_TOKEN` are never loaded from or written to this file.

## History Rewrite Diagnostics

`git push --mirror` is executed through a dedicated wrapper that captures stdout
and stderr. On failure, the output is scanned for rewrite/protection markers
such as:

- `non-fast-forward`
- `pre-receive hook declined`
- `protected branch hook declined`
- `remote rejected`
- `deny deleting` / deletion-prohibited style messages

When detected, the script prints:

- a symptom summary,
- likely causes (protected refs, server hooks, policy, permissions),
- debug commands:
  - `git -C <local-mirror> show-ref --head | sort`
  - `git ls-remote --refs <target-url> | sort`
  - `git -C <local-mirror> push --mirror --verbose`

## Visibility Clamping

GitLab forbids a child group from having higher visibility than its parent
(e.g. public child under private parent returns HTTP 400).

`clamp_group_visibility()` enforces this by comparing the requested
visibility rank against the parent's:

```
private (0) < internal (1) < public (2)
```

If the requested rank exceeds the parent's, visibility is silently
clamped down and a warning is logged.

## Local Mirror Cache

| Directory                           | Contents                        |
|-------------------------------------|---------------------------------|
| `repositories_mirror-use/`          | Root of all bare caches         |
| `repositories_mirror-use/<path>.git`| One bare repo per source project|

The cache directory mirrors the source group hierarchy. Bare repos are
validated with `git rev-parse --is-bare-repository` before reuse. If a
conflicting non-bare path exists, it is removed and the bare repo is
re-cloned.

The cache enables **incremental mirroring**: subsequent runs only fetch
new objects (`git fetch --prune`) instead of full re-clones.

## Logging

- `init_lastlog()` truncates `.lastlog` at the start of every run.
- `log()` dual-writes each message to stdout and `.lastlog`.
- `archive_lastlog()` copies `.lastlog` to `log/` after execution (success or failure).
- Specialized helpers (`section`, `status`, `warn`, `ok`, `fail`) format
  output consistently.

Runtime log files:

| Path / Pattern | Meaning |
|----------------|---------|
| `.lastlog` | Latest run output only (refreshed each run) |
| `log/<mmddyyyy>_<HHMMSS>_<RUN|DRYRUN>.log` | Archived per-run snapshot (local system time) |

If the same archive filename already exists in the same second, the script
adds a numeric suffix (`_1`, `_2`, ...) to avoid overwrite.

## Path Translation

`map_source_to_target_path()` converts source namespace paths to target
namespace paths:

```
SRC_ROOT_GROUP = "company/engineering"
DST_ROOT_GROUP = "backup/engineering"

source: "company/engineering/team/repo"
target: "backup/engineering/team/repo"
```

The function strips the `SRC_ROOT_GROUP` prefix and prepends
`DST_ROOT_GROUP`. It raises an error if a source path falls outside
the source root.

## SSL and Custom CA Handling

| Variable        | Effect                                       |
|-----------------|----------------------------------------------|
| `VERIFY_SSL`    | When `false`, disables SSL verification for both API calls and git operations |
| `GIT_SSL_CAINFO`| Path to a custom CA bundle — injected as `GIT_SSL_CAINFO` env var for git commands |

When `VERIFY_SSL=false`, `urllib3` InsecureRequestWarning is suppressed
and git receives `GIT_SSL_NO_VERIFY=true`.
