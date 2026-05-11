# Technical Details

This document describes the internals of `mirror.py` — a GitLab nested-group
mirroring tool.

## Execution Flow

```
main()
 ├─ init_lastlog()            truncate .lastlog
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

3. **Push** → `git push --mirror` to the target GitLab.

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
| `DRY_RUN`              | `true`  | No API writes, no git push — log only            |
| `AUTO_CONFIRM`         | `false` | Prompt `Type YES` before real execution           |
| `CONTINUE_ON_ERROR`    | `true`  | Log per-project failures, keep going              |
| `PUSH_EXISTING_PROJECTS` | `true` | Re-push into existing target projects            |

When `DRY_RUN=true`, `api_post` returns `None` and git commands are logged
but not executed.

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
- Specialized helpers (`section`, `status`, `warn`, `ok`, `fail`) format
  output consistently.

`.lastlog` always contains only the latest run output, not cumulative
history.

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
