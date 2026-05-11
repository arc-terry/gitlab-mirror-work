# mirror-work

Mirror nested GitLab groups and all their projects from one GitLab instance
to another — including subgroups, project creation, and full git history.

## Usage

### Prerequisites

- Python 3
- `pip install requests`
- git CLI

### Help

```bash
python3 mirror.py --help
```

This prints the full environment-variable usage and behavior notes without
requiring the runtime variables to be set.

### Environment Variables

**Required:**

| Variable         | Description                           |
|------------------|---------------------------------------|
| `SRC_GITLAB`     | Source GitLab base URL                |
| `DST_GITLAB`     | Target GitLab base URL                |
| `SRC_TOKEN`      | Source GitLab personal access token   |
| `DST_TOKEN`      | Target GitLab personal access token   |
| `SRC_ROOT_GROUP` | Source root group path to mirror      |
| `TARGET_DEV_BRANCH_PREFIX` | Preserved target branch prefix (for example `arc-hsinchu`) or `NONE` |

**Optional:**

| Variable               | Default   | Description                              |
|------------------------|-----------|------------------------------------------|
| `DST_ROOT_GROUP`       | *(same as source)* | Target root group path        |
| `DRY_RUN`              | `true`    | Log only, no writes                      |
| `AUTO_CONFIRM`         | `false`   | Skip interactive confirmation            |
| `VERIFY_SSL`           | `true`    | Verify SSL certificates                  |
| `SRC_GIT_PROTO`        | `https`   | Git protocol for source (`https`/`ssh`)  |
| `DST_GIT_PROTO`        | `ssh`     | Git protocol for target (`https`/`ssh`)  |
| `SRC_SSH_PORT`         | *(default)* | Custom SSH port for source             |
| `DST_SSH_PORT`         | *(default)* | Custom SSH port for target             |
| `GIT_SSL_CAINFO`       | *(none)*  | Path to custom CA bundle                 |
| `PUSH_EXISTING_PROJECTS` | `true`  | Re-push into existing target projects    |
| `CONTINUE_ON_ERROR`    | `true`    | Keep going on per-project failures       |

### Run

```bash
SRC_GITLAB=https://source.example.com \
DST_GITLAB=https://target.example.com \
SRC_TOKEN=glpat-xxxx \
DST_TOKEN=glpat-yyyy \
SRC_ROOT_GROUP=company/engineering \
python3 mirror.py
```

The script auto-loads defaults from `.lastconfig.env` (if present), then applies
current environment variables on top.

`TARGET_DEV_BRANCH_PREFIX` is required after merge. Set either:
- a prefix (for example `arc-hsinchu`) to preserve `arc-hsinchu/*` branches, or
- `NONE` to disable prefix-preserve behavior.

The script runs in **dry-run mode by default** — no changes are made until
you set `DRY_RUN=false`.

Each run writes the latest output to `.lastlog` and archives it to `log/`
as `<mmddyyyy>_<HHMMSS>_<RUN|DRYRUN>.log` (local system time).

When `TARGET_DEV_BRANCH_PREFIX` is a real prefix, target-only branches under
`<prefix>/*` are preserved and not deleted by mirror push.

## Practical Examples

### Dry-run preview

See what would happen without touching anything:

```bash
SRC_GITLAB=https://gitlab-a.com \
DST_GITLAB=https://gitlab-b.com \
SRC_TOKEN=glpat-xxxx \
DST_TOKEN=glpat-yyyy \
SRC_ROOT_GROUP=org/platform \
python3 mirror.py
```

Dry-run now prints a per-project ref diff report (`refs to create`, `refs to update`,
`refs to delete`) so you can see exactly what is not yet mirrored.

### Full mirror execution

```bash
SRC_GITLAB=https://gitlab-a.com \
DST_GITLAB=https://gitlab-b.com \
SRC_TOKEN=glpat-xxxx \
DST_TOKEN=glpat-yyyy \
SRC_ROOT_GROUP=org/platform \
DRY_RUN=false \
python3 mirror.py
```

Type `YES` when prompted to proceed.

### Mirror to a different target group

```bash
SRC_ROOT_GROUP=org/platform \
DST_ROOT_GROUP=backup/platform-mirror \
DRY_RUN=false \
AUTO_CONFIRM=true \
# ... (other env vars) ...
python3 mirror.py
```

### Custom SSH port and CA certificate

```bash
DST_GIT_PROTO=ssh \
DST_SSH_PORT=2222 \
GIT_SSL_CAINFO=/etc/ssl/custom-ca.pem \
# ... (other env vars) ...
python3 mirror.py
```

### Incremental sync (re-run)

Simply run the same command again. The local bare cache under
`repositories_mirror-use/` is reused — only new objects are fetched
before pushing to the target.

### History rewrite rejection troubleshooting

If `git push --mirror` is rejected due to rewritten history or ref protection,
the tool now prints:

- symptom summary,
- likely causes (protected refs, hooks, policy restrictions, permission gaps),
- debug commands to inspect local and target refs in detail.

### Preserve target development branches by prefix

If you maintain target-only branches (for example `arc-hsinchu/*`), set:

```bash
TARGET_DEV_BRANCH_PREFIX=arc-hsinchu
```

To disable this feature explicitly, set:

```bash
TARGET_DEV_BRANCH_PREFIX=NONE
```

Behavior:

- `arc-hsinchu/*` target-only branches are kept.
- Other target-only branches still follow mirror deletion behavior.
- In real run (`DRY_RUN=false`), if non-preserved target refs would be deleted,
  the script prompts for confirmation: `Delete <N> non-preserved target refs? [y/N]`.

## Background

The tool uses the **GitLab REST API v4** to discover and create groups and
projects, then performs git-level mirroring via `git clone --mirror` /
`git fetch --prune` + `git push --mirror` through a persistent local bare
repository cache.

For detailed technical information, see
[doc/technical-details.md](doc/technical-details.md).

### Limitations

- **Git data only** — issues, merge requests, wikis, CI/CD pipelines, and
  other GitLab metadata are not mirrored.
- **Sequential processing** — projects are mirrored one at a time.
- **Token permissions** — API tokens need sufficient access to list, create,
  and read groups/projects on both instances.
- **SSH keys** — when using SSH protocol for push, SSH keys must be
  pre-configured on the target host.
- **`git push --mirror`** — can overwrite or delete refs on the target.
  Safest when target projects are new or empty.

### Specifications

| Component      | Version / Detail  |
|----------------|-------------------|
| Language       | Python 3          |
| Dependencies   | `requests`        |
| GitLab API     | v4                |
| Git operations | CLI (`git`)       |
| Protocols      | HTTPS, SSH        |
