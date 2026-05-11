#!/usr/bin/env python3

import os
import sys
import shutil
import shlex
import subprocess
import urllib.parse
from datetime import datetime
from typing import List, Optional, Tuple

import requests
import urllib3


# ============================================================
# Required environment variables
# ============================================================

SRC_GITLAB = os.environ["SRC_GITLAB"].rstrip("/")
DST_GITLAB = os.environ["DST_GITLAB"].rstrip("/")

SRC_TOKEN = os.environ["SRC_TOKEN"]
DST_TOKEN = os.environ["DST_TOKEN"]

SRC_ROOT_GROUP = os.environ["SRC_ROOT_GROUP"].strip("/")
DST_ROOT_GROUP = os.environ.get("DST_ROOT_GROUP", SRC_ROOT_GROUP).strip("/")


# ============================================================
# Optional environment variables
# ============================================================

VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() not in (
    "0",
    "false",
    "no",
)

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() in (
    "1",
    "true",
    "yes",
)

AUTO_CONFIRM = os.environ.get("AUTO_CONFIRM", "false").lower() in (
    "1",
    "true",
    "yes",
)

SRC_GIT_PROTO = os.environ.get("SRC_GIT_PROTO", "https").lower()
DST_GIT_PROTO = os.environ.get("DST_GIT_PROTO", "ssh").lower()

SRC_SSH_PORT = os.environ.get("SRC_SSH_PORT")
DST_SSH_PORT = os.environ.get("DST_SSH_PORT")

GIT_SSL_CAINFO = os.environ.get("GIT_SSL_CAINFO")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_MIRROR_BASE = os.path.join(SCRIPT_DIR, "repositories_mirror-use")
LASTLOG_PATH = os.path.join(SCRIPT_DIR, ".lastlog")
LOG_ARCHIVE_DIR = os.path.join(SCRIPT_DIR, "log")

PUSH_EXISTING_PROJECTS = os.environ.get("PUSH_EXISTING_PROJECTS", "true").lower() in (
    "1",
    "true",
    "yes",
)

CONTINUE_ON_ERROR = os.environ.get("CONTINUE_ON_ERROR", "true").lower() in (
    "1",
    "true",
    "yes",
)


if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ============================================================
# Logging helpers
# ============================================================

def log(msg: str):
    text = str(msg)
    print(text, flush=True)
    with open(LASTLOG_PATH, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def init_lastlog():
    with open(LASTLOG_PATH, "w", encoding="utf-8"):
        pass


def log_type_tag() -> str:
    return "DRYRUN" if DRY_RUN else "RUN"


def build_archive_log_path(stamp: str, sequence: int = 0) -> str:
    filename = f"{stamp}_{log_type_tag()}.log"
    if sequence > 0:
        filename = f"{stamp}_{log_type_tag()}_{sequence}.log"
    return os.path.join(LOG_ARCHIVE_DIR, filename)


def archive_lastlog() -> str:
    if not os.path.exists(LASTLOG_PATH):
        raise RuntimeError(f"Latest log file does not exist: {LASTLOG_PATH}")

    os.makedirs(LOG_ARCHIVE_DIR, exist_ok=True)

    stamp = datetime.now().strftime("%m%d%Y_%H%M%S")
    archive_path = build_archive_log_path(stamp)

    seq = 1
    while os.path.exists(archive_path):
        archive_path = build_archive_log_path(stamp, seq)
        seq += 1

    shutil.copy2(LASTLOG_PATH, archive_path)
    return archive_path


def section(title: str):
    log("")
    log("=" * 72)
    log(title)
    log("=" * 72)


def status(label: str, value: str):
    log(f"{label:<32} {value}")


def warn(msg: str):
    log(f"[WARN] {msg}")


def ok(msg: str):
    log(f"[OK] {msg}")


def fail(msg: str):
    log(f"[FAIL] {msg}")


# ============================================================
# Basic helpers
# ============================================================

def encode_path(path: str) -> str:
    return urllib.parse.quote(path, safe="")


def git_host_from_base(base: str) -> str:
    parsed = urllib.parse.urlparse(base)
    return parsed.netloc or parsed.path


def https_tokenized_repo_url(base: str, token: str, full_path: str) -> str:
    parsed = urllib.parse.urlparse(base)
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path
    return f"{scheme}://oauth2:{urllib.parse.quote(token, safe='')}@{host}/{full_path}.git"


def safe_https_repo_url(base: str, full_path: str) -> str:
    parsed = urllib.parse.urlparse(base)
    scheme = parsed.scheme or "https"
    host = parsed.netloc or parsed.path
    return f"{scheme}://oauth2:<TOKEN>@{host}/{full_path}.git"


def ssh_repo_url(base: str, full_path: str, port: Optional[str] = None) -> str:
    host = git_host_from_base(base)

    if port:
        return f"ssh://git@{host}:{port}/{full_path}.git"

    return f"git@{host}:{full_path}.git"


def repo_url(
    base: str,
    token: str,
    full_path: str,
    proto: str,
    ssh_port: Optional[str] = None,
) -> str:
    if proto == "ssh":
        return ssh_repo_url(base, full_path, ssh_port)

    if proto == "https":
        return https_tokenized_repo_url(base, token, full_path)

    raise RuntimeError(f"Unsupported Git protocol: {proto}. Use 'ssh' or 'https'.")


def safe_repo_url(
    base: str,
    full_path: str,
    proto: str,
    ssh_port: Optional[str] = None,
) -> str:
    if proto == "ssh":
        return ssh_repo_url(base, full_path, ssh_port)

    if proto == "https":
        return safe_https_repo_url(base, full_path)

    return f"<unsupported proto {proto}>:{full_path}"


def map_source_to_target_path(src_full_path: str) -> str:
    if src_full_path == SRC_ROOT_GROUP:
        return DST_ROOT_GROUP

    prefix = SRC_ROOT_GROUP + "/"
    if not src_full_path.startswith(prefix):
        raise RuntimeError(f"Source path outside source root group: {src_full_path}")

    suffix = src_full_path[len(prefix):]
    return f"{DST_ROOT_GROUP}/{suffix}"


VISIBILITY_RANK = {
    "private": 0,
    "internal": 1,
    "public": 2,
}


def clamp_group_visibility(
    requested_visibility: str,
    parent_visibility: Optional[str],
    group_full_path: str,
) -> str:
    requested = (requested_visibility or "private").lower()
    parent = (parent_visibility or "").lower()

    if parent not in VISIBILITY_RANK or requested not in VISIBILITY_RANK:
        return requested

    if VISIBILITY_RANK[requested] > VISIBILITY_RANK[parent]:
        warn(
            f"Clamp group visibility for {group_full_path}: "
            f"{requested} -> {parent} (parent restriction)"
        )
        return parent

    return requested


def local_mirror_repo_path(src_full_path: str) -> str:
    return os.path.join(LOCAL_MIRROR_BASE, f"{src_full_path}.git")


def is_valid_bare_repo(path: str) -> bool:
    if not os.path.isdir(path):
        return False

    probe = subprocess.run(
        ["git", "rev-parse", "--is-bare-repository"],
        cwd=path,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return probe.returncode == 0 and probe.stdout.strip() == "true"


def remove_conflicting_path(path: str):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


# ============================================================
# GitLab API helpers
# ============================================================

def api_request(method: str, base: str, token: str, path: str, **kwargs):
    url = f"{base}/api/v4{path}"
    headers = kwargs.pop("headers", {})
    headers["PRIVATE-TOKEN"] = token

    return requests.request(
        method,
        url,
        headers=headers,
        verify=VERIFY_SSL,
        **kwargs,
    )


def api_get(base: str, token: str, path: str, params=None):
    url = f"{base}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token}
    results = []

    while url:
        resp = requests.get(
            url,
            headers=headers,
            params=params,
            verify=VERIFY_SSL,
        )
        params = None

        if resp.status_code >= 400:
            raise RuntimeError(f"GET {url} failed: {resp.status_code} {resp.text}")

        data = resp.json()

        if isinstance(data, list):
            results.extend(data)
            url = resp.links.get("next", {}).get("url")
        else:
            return data

    return results


def api_post(base: str, token: str, path: str, data=None):
    url = f"{base}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token}

    if DRY_RUN:
        log(f"[DRY-RUN] POST {url} data={data}")
        return None

    resp = requests.post(
        url,
        headers=headers,
        data=data,
        verify=VERIFY_SSL,
    )

    if resp.status_code >= 400:
        raise RuntimeError(f"POST {url} failed: {resp.status_code} {resp.text}")

    return resp.json()


def get_group_by_full_path(base: str, token: str, full_path: str) -> Optional[dict]:
    resp = api_request(
        "GET",
        base,
        token,
        f"/groups/{encode_path(full_path)}",
    )

    if resp.status_code == 404:
        return None

    if resp.status_code >= 400:
        raise RuntimeError(
            f"GET group {full_path} failed: {resp.status_code} {resp.text}"
        )

    return resp.json()


def get_project_by_full_path(base: str, token: str, full_path: str) -> Optional[dict]:
    resp = api_request(
        "GET",
        base,
        token,
        f"/projects/{encode_path(full_path)}",
    )

    if resp.status_code == 404:
        return None

    if resp.status_code >= 400:
        raise RuntimeError(
            f"GET project {full_path} failed: {resp.status_code} {resp.text}"
        )

    return resp.json()


def list_subgroups(base: str, token: str, group_id: int) -> List[dict]:
    return api_get(
        base,
        token,
        f"/groups/{group_id}/subgroups",
        params={
            "per_page": 100,
            "all_available": "false",
        },
    )


def list_projects(base: str, token: str, group_id: int) -> List[dict]:
    return api_get(
        base,
        token,
        f"/groups/{group_id}/projects",
        params={
            "per_page": 100,
            "include_subgroups": "false",
            "with_shared": "false",
        },
    )


# ============================================================
# Discovery / preflight
# ============================================================

def collect_source_tree(src_group: dict) -> Tuple[List[dict], List[dict]]:
    """
    Returns:
      all_groups, all_projects

    all_groups includes root group.
    """

    groups = [src_group]
    projects = []

    local_projects = list_projects(SRC_GITLAB, SRC_TOKEN, src_group["id"])
    projects.extend(local_projects)

    subgroups = list_subgroups(SRC_GITLAB, SRC_TOKEN, src_group["id"])
    for subgroup in subgroups:
        sub_groups, sub_projects = collect_source_tree(subgroup)
        groups.extend(sub_groups)
        projects.extend(sub_projects)

    return groups, projects


def check_target_group_chain(full_path: str):
    parts = full_path.split("/")
    current = ""

    rows = []

    for part in parts:
        current = part if not current else f"{current}/{part}"
        existing = get_group_by_full_path(DST_GITLAB, DST_TOKEN, current)
        rows.append((current, existing is not None))

    return rows


def preflight_report(src_root: dict):
    section("Current configuration")

    status("Source GitLab API", SRC_GITLAB)
    status("Target GitLab API", DST_GITLAB)
    status("Source root group", SRC_ROOT_GROUP)
    status("Target root group", DST_ROOT_GROUP)
    status("Source Git protocol", SRC_GIT_PROTO)
    status("Target Git protocol", DST_GIT_PROTO)
    status("Source SSH port", SRC_SSH_PORT or "(default)")
    status("Target SSH port", DST_SSH_PORT or "(default)")
    status("Verify SSL", str(VERIFY_SSL))
    status("Git CA file", GIT_SSL_CAINFO or "(none)")
    status("Debug log file", LASTLOG_PATH)
    status("Archive log dir", LOG_ARCHIVE_DIR)
    status("Local mirror cache", LOCAL_MIRROR_BASE)
    status("Dry run", str(DRY_RUN))
    status("Auto confirm", str(AUTO_CONFIRM))
    status("Push existing projects", str(PUSH_EXISTING_PROJECTS))
    status("Continue on error", str(CONTINUE_ON_ERROR))

    section("Connectivity / permission status")

    if src_root:
        ok(f"Source root group found: {SRC_ROOT_GROUP}  id={src_root['id']}")
    else:
        fail(f"Source root group not found: {SRC_ROOT_GROUP}")
        raise RuntimeError(f"Source root group not found: {SRC_ROOT_GROUP}")

    target_root = get_group_by_full_path(DST_GITLAB, DST_TOKEN, DST_ROOT_GROUP)
    if target_root:
        ok(f"Target root group already exists: {DST_ROOT_GROUP}  id={target_root['id']}")
    else:
        warn(f"Target root group does not exist yet: {DST_ROOT_GROUP}")

    section("Target group path check")

    chain = check_target_group_chain(DST_ROOT_GROUP)
    for path, exists in chain:
        if exists:
            ok(f"Target group exists:      {path}")
        else:
            warn(f"Target group will create: {path}")

    section("Scanning source group tree")

    groups, projects = collect_source_tree(src_root)

    status("Source groups found", str(len(groups)))
    status("Source projects found", str(len(projects)))

    section("Target plan summary")

    groups_to_create = []
    groups_existing = []

    for group in groups:
        dst_path = map_source_to_target_path(group["full_path"])
        if get_group_by_full_path(DST_GITLAB, DST_TOKEN, dst_path):
            groups_existing.append(dst_path)
        else:
            groups_to_create.append(dst_path)

    projects_to_create = []
    projects_existing = []

    for project in projects:
        dst_path = map_source_to_target_path(project["path_with_namespace"])
        if get_project_by_full_path(DST_GITLAB, DST_TOKEN, dst_path):
            projects_existing.append(dst_path)
        else:
            projects_to_create.append(dst_path)

    status("Target groups existing", str(len(groups_existing)))
    status("Target groups to create", str(len(groups_to_create)))
    status("Target projects existing", str(len(projects_existing)))
    status("Target projects to create", str(len(projects_to_create)))

    if groups_to_create:
        log("")
        log("Groups to create:")
        for path in groups_to_create[:50]:
            log(f"  + {path}")
        if len(groups_to_create) > 50:
            log(f"  ... {len(groups_to_create) - 50} more")

    if projects_to_create:
        log("")
        log("Projects to create:")
        for path in projects_to_create[:50]:
            log(f"  + {path}")
        if len(projects_to_create) > 50:
            log(f"  ... {len(projects_to_create) - 50} more")

    if projects_existing and PUSH_EXISTING_PROJECTS:
        log("")
        warn("Existing projects will still receive git push --mirror:")
        for path in projects_existing[:30]:
            log(f"  ! {path}")
        if len(projects_existing) > 30:
            log(f"  ... {len(projects_existing) - 30} more")

    if projects:
        sample_project = projects[0]
        sample_src_path = sample_project["path_with_namespace"]
        sample_dst_path = map_source_to_target_path(sample_src_path)

        section("Sample Git URLs")

        status(
            "Sample source clone URL",
            safe_repo_url(SRC_GITLAB, sample_src_path, SRC_GIT_PROTO, SRC_SSH_PORT),
        )
        status(
            "Sample target push URL",
            safe_repo_url(DST_GITLAB, sample_dst_path, DST_GIT_PROTO, DST_SSH_PORT),
        )

    section("Operation meaning")

    log("This script will:")
    log("  1. Create missing target groups/subgroups.")
    log("  2. Create missing empty target projects.")
    log("  3. Reuse or create local bare mirrors under repositories_mirror-use.")
    log("  4. Run git fetch --prune to refresh local mirrors.")
    log("  5. Run git push --mirror to target.")
    log("")
    warn("git push --mirror can overwrite or delete refs on the target repository.")
    warn("This is safest when target projects are new or empty.")

    return groups, projects


def confirm_before_process():
    if AUTO_CONFIRM:
        ok("AUTO_CONFIRM=true, continue without prompt.")
        return

    if DRY_RUN:
        log("")
        ok("DRY_RUN=true, no real create/push will happen.")
        return

    log("")
    answer = input("Type YES to start real mirror process: ").strip()

    if answer != "YES":
        raise RuntimeError("User did not confirm. Abort.")


# ============================================================
# Target group/project creation
# ============================================================

def create_group_if_missing(
    target_full_path: str,
    name: str,
    path: str,
    parent_full_path: Optional[str],
    visibility: str = "private",
) -> dict:
    existing = get_group_by_full_path(DST_GITLAB, DST_TOKEN, target_full_path)
    if existing:
        log(f"[GROUP EXISTS] {target_full_path}")
        return existing

    parent_id = None
    effective_visibility = visibility

    if parent_full_path:
        parent = get_group_by_full_path(DST_GITLAB, DST_TOKEN, parent_full_path)
        if not parent:
            raise RuntimeError(f"Parent group missing on target: {parent_full_path}")
        parent_id = parent["id"]
        effective_visibility = clamp_group_visibility(
            visibility,
            parent.get("visibility"),
            target_full_path,
        )

    data = {
        "name": name,
        "path": path,
        "visibility": effective_visibility,
    }

    if parent_id is not None:
        data["parent_id"] = parent_id

    log(f"[CREATE GROUP] {target_full_path}")

    created = api_post(DST_GITLAB, DST_TOKEN, "/groups", data=data)

    if DRY_RUN:
        return {
            "id": -1,
            "name": name,
            "path": path,
            "full_path": target_full_path,
        }

    return created


def ensure_group_path(full_path: str, visibility: str = "private"):
    parts = full_path.strip("/").split("/")
    current = ""

    for part in parts:
        parent_path = current if current else None
        current = part if not current else f"{current}/{part}"

        existing = get_group_by_full_path(DST_GITLAB, DST_TOKEN, current)
        if existing:
            log(f"[GROUP EXISTS] {current}")
            continue

        parent_id = None
        parent_visibility = None

        if parent_path:
            parent = get_group_by_full_path(DST_GITLAB, DST_TOKEN, parent_path)
            if not parent:
                if DRY_RUN:
                    log(f"[DRY-RUN] Parent would need to exist/create first: {parent_path}")
                else:
                    raise RuntimeError(f"Parent group missing on target: {parent_path}")
            else:
                parent_id = parent["id"]
                parent_visibility = parent.get("visibility")

        effective_visibility = clamp_group_visibility(
            visibility,
            parent_visibility,
            current,
        )

        data = {
            "name": part,
            "path": part,
            "visibility": effective_visibility,
        }

        if parent_id is not None:
            data["parent_id"] = parent_id

        log(f"[CREATE GROUP] {current}")
        api_post(DST_GITLAB, DST_TOKEN, "/groups", data=data)


def create_project_if_missing(
    target_full_path: str,
    project_name: str,
    project_path: str,
    namespace_full_path: str,
    visibility: str = "private",
    description: str = "",
) -> tuple:
    existing = get_project_by_full_path(DST_GITLAB, DST_TOKEN, target_full_path)
    if existing:
        log(f"[PROJECT EXISTS] {target_full_path}")
        return existing, False

    namespace = get_group_by_full_path(DST_GITLAB, DST_TOKEN, namespace_full_path)
    if not namespace:
        raise RuntimeError(f"Target namespace missing: {namespace_full_path}")

    data = {
        "name": project_name,
        "path": project_path,
        "namespace_id": namespace["id"],
        "visibility": visibility,
        "description": description or "",
        "initialize_with_readme": "false",
    }

    log(f"[CREATE PROJECT] {target_full_path}")

    created = api_post(DST_GITLAB, DST_TOKEN, "/projects", data=data)

    if DRY_RUN:
        return {
            "id": -1,
            "name": project_name,
            "path": project_path,
            "path_with_namespace": target_full_path,
        }, True

    return created, True


# ============================================================
# Git operation helpers
# ============================================================

def git_command_env() -> dict:
    env = os.environ.copy()

    if GIT_SSL_CAINFO:
        env["GIT_SSL_CAINFO"] = GIT_SSL_CAINFO
    elif not VERIFY_SSL:
        env["GIT_SSL_NO_VERIFY"] = "true"

    return env


def parse_ls_remote_refs(output: str) -> dict:
    refs = {}

    for line in output.splitlines():
        if "\t" not in line:
            continue

        sha, ref_name = line.split("\t", 1)
        if not ref_name.startswith("refs/"):
            continue

        refs[ref_name] = sha

    return refs


def ls_remote_refs(url: str, side: str) -> dict:
    cmd = ["git", "ls-remote", "--refs", url]
    proc = subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=git_command_env(),
    )

    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(
            f"Failed to list {side} refs via git ls-remote (exit={proc.returncode}): {stderr}"
        )

    return parse_ls_remote_refs(proc.stdout)


def classify_ref_diff(source_refs: dict, target_refs: dict) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    to_create = []
    to_update = []
    to_delete = []

    for ref_name, source_sha in source_refs.items():
        target_sha = target_refs.get(ref_name)
        if target_sha is None:
            to_create.append((ref_name, source_sha))
            continue

        if target_sha != source_sha:
            to_update.append((ref_name, target_sha, source_sha))

    for ref_name, target_sha in target_refs.items():
        if ref_name not in source_refs:
            to_delete.append((ref_name, target_sha))

    to_create.sort(key=lambda row: row[0])
    to_update.sort(key=lambda row: row[0])
    to_delete.sort(key=lambda row: row[0])
    return to_create, to_update, to_delete


def log_dry_run_ref_diff(
    dst_project_full_path: str,
    source_refs: dict,
    target_refs: dict,
):
    to_create, to_update, to_delete = classify_ref_diff(source_refs, target_refs)

    log("[DRY-RUN] Refs not yet mirrored (source -> target)")
    status("Project", dst_project_full_path)
    status("Source refs", str(len(source_refs)))
    status("Target refs", str(len(target_refs)))
    status("Refs to create", str(len(to_create)))
    status("Refs to update", str(len(to_update)))
    status("Refs to delete", str(len(to_delete)))

    if not to_create and not to_update and not to_delete:
        ok("Dry-run diff: target is already in sync with source refs.")
        return

    if to_create:
        log("")
        log("Refs to create:")
        for ref_name, source_sha in to_create:
            log(f"  + {ref_name} {source_sha}")

    if to_update:
        log("")
        log("Refs to update:")
        for ref_name, target_sha, source_sha in to_update:
            log(f"  ~ {ref_name} {target_sha} -> {source_sha}")

    if to_delete:
        log("")
        log("Refs to delete:")
        for ref_name, target_sha in to_delete:
            log(f"  - {ref_name} {target_sha}")


def is_history_rewrite_issue(output: str) -> bool:
    lowered = output.lower()
    markers = [
        "non-fast-forward",
        "pre-receive hook declined",
        "protected branch hook declined",
        "protected tag",
        "remote rejected",
        "cannot force update",
        "deny deleting",
        "deletion prohibited",
        "fetch first",
    ]
    return any(marker in lowered for marker in markers)


def log_history_rewrite_diagnostics(repo_dir: str, safe_dst_url: str):
    repo_arg = shlex.quote(repo_dir)
    url_arg = shlex.quote(safe_dst_url)

    log("")
    warn("Potential history rewrite / ref-protection issue detected.")
    log("Symptom:")
    log("  - git push --mirror was rejected while updating or deleting refs.")
    log("Likely reasons:")
    log("  - Protected branches/tags block force-push or ref deletion.")
    log("  - Server-side hooks reject rewritten history.")
    log("  - Target refs diverged and policy forbids overwrite.")
    log("  - Credentials do not allow force-update/delete operations.")
    log("Debug commands:")
    log(f"  git -C {repo_arg} show-ref --head | sort")
    log(f"  git ls-remote --refs {url_arg} | sort")
    log(f"  git -C {repo_arg} push --mirror --verbose")


def run_push_mirror_with_diagnostics(repo_dir: str, safe_dst_url: str):
    cmd = ["git", "push", "--mirror"]
    log(f"+ {' '.join(cmd)}")

    proc = subprocess.run(
        cmd,
        cwd=repo_dir,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=git_command_env(),
    )

    if proc.stdout:
        for line in proc.stdout.splitlines():
            log(line)

    if proc.stderr:
        for line in proc.stderr.splitlines():
            log(line)

    if proc.returncode == 0:
        return

    merged_output = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
    if is_history_rewrite_issue(merged_output):
        log_history_rewrite_diagnostics(repo_dir, safe_dst_url)

    raise RuntimeError(f"git push --mirror failed with exit code {proc.returncode}")


def run(cmd: List[str], cwd: Optional[str] = None):
    log(f"+ {' '.join(cmd)}")

    if DRY_RUN:
        return

    subprocess.run(cmd, cwd=cwd, check=True, env=git_command_env())


def ensure_local_mirror(src_full_path: str, src_url: str) -> str:
    repo_dir = local_mirror_repo_path(src_full_path)
    repo_parent = os.path.dirname(repo_dir)

    if DRY_RUN:
        log(f"[DRY-RUN] mkdir -p {repo_parent}")
    else:
        os.makedirs(repo_parent, exist_ok=True)

    if os.path.exists(repo_dir):
        if is_valid_bare_repo(repo_dir):
            log(f"[CACHE REUSE] {repo_dir}")
            run(["git", "remote", "set-url", "origin", src_url], cwd=repo_dir)
            run(["git", "fetch", "--prune", "origin"], cwd=repo_dir)
            return repo_dir

        warn(f"Conflicting local path exists and is not bare repo: {repo_dir}")
        if DRY_RUN:
            log(f"[DRY-RUN] rm -rf {repo_dir}")
        else:
            remove_conflicting_path(repo_dir)

    log(f"[CACHE CREATE] {repo_dir}")
    run(["git", "clone", "--mirror", src_url, repo_dir])
    return repo_dir


def mirror_project(src_project: dict, dst_project_full_path: str, target_created_now: bool):
    src_full_path = src_project["path_with_namespace"]

    log("")
    log("-" * 72)
    log(f"[MIRROR PROJECT]")
    status("Source", src_full_path)
    status("Target", dst_project_full_path)
    safe_src_url = safe_repo_url(SRC_GITLAB, src_full_path, SRC_GIT_PROTO, SRC_SSH_PORT)
    safe_dst_url = safe_repo_url(DST_GITLAB, dst_project_full_path, DST_GIT_PROTO, DST_SSH_PORT)
    status("Source URL", safe_src_url)
    status("Target URL", safe_dst_url)
    log("-" * 72)

    src_url = repo_url(
        SRC_GITLAB,
        SRC_TOKEN,
        src_full_path,
        SRC_GIT_PROTO,
        SRC_SSH_PORT,
    )

    dst_url = repo_url(
        DST_GITLAB,
        DST_TOKEN,
        dst_project_full_path,
        DST_GIT_PROTO,
        DST_SSH_PORT,
    )

    if DRY_RUN:
        source_refs = ls_remote_refs(src_url, "source")
        target_refs = {}

        if target_created_now:
            log("[DRY-RUN] Target project will be created; all source refs are pending mirror.")
        else:
            target_refs = ls_remote_refs(dst_url, "target")

        log_dry_run_ref_diff(dst_project_full_path, source_refs, target_refs)
        return

    repo_dir = ensure_local_mirror(src_full_path, src_url)
    run(["git", "remote", "set-url", "--push", "origin", dst_url], cwd=repo_dir)
    run_push_mirror_with_diagnostics(repo_dir, safe_dst_url)

    ok(f"Mirror completed: {dst_project_full_path}")


# ============================================================
# Migration logic
# ============================================================

def migrate_group_recursive(src_group: dict):
    src_group_full_path = src_group["full_path"]
    dst_group_full_path = map_source_to_target_path(src_group_full_path)

    parent_dst_path = None
    if "/" in dst_group_full_path:
        parent_dst_path = dst_group_full_path.rsplit("/", 1)[0]

    create_group_if_missing(
        target_full_path=dst_group_full_path,
        name=src_group["name"],
        path=dst_group_full_path.split("/")[-1],
        parent_full_path=parent_dst_path,
        visibility=src_group.get("visibility", "private"),
    )

    projects = list_projects(SRC_GITLAB, SRC_TOKEN, src_group["id"])

    for project in projects:
        src_project_full_path = project["path_with_namespace"]
        dst_project_full_path = map_source_to_target_path(src_project_full_path)
        dst_namespace_full_path = dst_project_full_path.rsplit("/", 1)[0]

        try:
            _, created_now = create_project_if_missing(
                target_full_path=dst_project_full_path,
                project_name=project["name"],
                project_path=project["path"],
                namespace_full_path=dst_namespace_full_path,
                visibility=project.get("visibility", "private"),
                description=project.get("description") or "",
            )

            if created_now or PUSH_EXISTING_PROJECTS:
                mirror_project(project, dst_project_full_path, created_now)
            else:
                log(f"[SKIP PUSH EXISTING PROJECT] {dst_project_full_path}")

        except Exception as e:
            log(f"[ERROR] Project failed: {src_project_full_path}")
            log(f"[ERROR] {e}")

            if not CONTINUE_ON_ERROR:
                raise

    subgroups = list_subgroups(SRC_GITLAB, SRC_TOKEN, src_group["id"])

    for subgroup in subgroups:
        migrate_group_recursive(subgroup)


def main():
    init_lastlog()
    section("GitLab nested group mirror")

    src_root = get_group_by_full_path(SRC_GITLAB, SRC_TOKEN, SRC_ROOT_GROUP)

    groups, projects = preflight_report(src_root)

    confirm_before_process()

    section("Start mirror process")

    ensure_group_path(
        DST_ROOT_GROUP,
        visibility=src_root.get("visibility", "private"),
    )

    migrate_group_recursive(src_root)

    section("Final result")
    ok("Mirror process finished.")
    status("Source groups scanned", str(len(groups)))
    status("Source projects scanned", str(len(projects)))


if __name__ == "__main__":
    exit_code = 0

    try:
        main()
    except KeyboardInterrupt:
        log("[INTERRUPTED]")
        exit_code = 130
    except Exception as e:
        log(f"[FATAL] {e}")
        exit_code = 1
    finally:
        try:
            archive_path = archive_lastlog()
            status("Archived log file", archive_path)
        except Exception as e:
            warn(f"Failed to archive execution log: {e}")
            if exit_code == 0:
                exit_code = 1

    sys.exit(exit_code)
