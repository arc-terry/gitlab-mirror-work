#!/usr/bin/env python3

import os
import sys
import time
import shutil
import tempfile
import subprocess
import urllib.parse
from typing import Dict, List, Optional

import requests


SRC_GITLAB = os.environ["SRC_GITLAB"].rstrip("/")
DST_GITLAB = os.environ["DST_GITLAB"].rstrip("/")
SRC_TOKEN = os.environ["SRC_TOKEN"]
DST_TOKEN = os.environ["DST_TOKEN"]

SRC_ROOT_GROUP = os.environ["SRC_ROOT_GROUP"].strip("/")
DST_ROOT_GROUP = os.environ.get("DST_ROOT_GROUP", SRC_ROOT_GROUP).strip("/")

VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() not in ("0", "false", "no")

DRY_RUN = os.environ.get("DRY_RUN", "false").lower() in ("1", "true", "yes")


def api_get(base: str, token: str, path: str, params=None):
    url = f"{base}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token}
    results = []

    while url:
        resp = requests.get(url, headers=headers, params=params, verify=VERIFY_SSL)
        params = None

        if resp.status_code >= 400:
            raise RuntimeError(f"GET {url} failed: {resp.status_code} {resp.text}")

        data = resp.json()

        if isinstance(data, list):
            results.extend(data)
        else:
            return data

        url = resp.links.get("next", {}).get("url")

    return results


def api_post(base: str, token: str, path: str, data=None):
    url = f"{base}/api/v4{path}"
    headers = {"PRIVATE-TOKEN": token}

    if DRY_RUN:
        print(f"[DRY-RUN] POST {url} data={data}")
        return None

    resp = requests.post(url, headers=headers, data=data, verify=VERIFY_SSL)

    if resp.status_code >= 400:
        raise RuntimeError(f"POST {url} failed: {resp.status_code} {resp.text}")

    return resp.json()


def encode_path(path: str) -> str:
    return urllib.parse.quote(path, safe="")


def get_group_by_full_path(base: str, token: str, full_path: str) -> Optional[dict]:
    try:
        return api_get(base, token, f"/groups/{encode_path(full_path)}")
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise


def get_project_by_full_path(base: str, token: str, full_path: str) -> Optional[dict]:
    try:
        return api_get(base, token, f"/projects/{encode_path(full_path)}")
    except RuntimeError as e:
        if "404" in str(e):
            return None
        raise


def list_subgroups(base: str, token: str, group_id: int) -> List[dict]:
    return api_get(
        base,
        token,
        f"/groups/{group_id}/subgroups",
        params={"per_page": 100, "all_available": "false"},
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


def create_group_if_missing(
    target_full_path: str,
    name: str,
    path: str,
    parent_full_path: Optional[str],
    visibility: str,
) -> dict:
    existing = get_group_by_full_path(DST_GITLAB, DST_TOKEN, target_full_path)
    if existing:
        print(f"[GROUP EXISTS] {target_full_path}")
        return existing

    parent_id = None
    if parent_full_path:
        parent = get_group_by_full_path(DST_GITLAB, DST_TOKEN, parent_full_path)
        if not parent:
            raise RuntimeError(f"Parent group missing on target: {parent_full_path}")
        parent_id = parent["id"]

    data = {
        "name": name,
        "path": path,
        "visibility": visibility,
    }

    if parent_id is not None:
        data["parent_id"] = parent_id

    print(f"[CREATE GROUP] {target_full_path}")
    created = api_post(DST_GITLAB, DST_TOKEN, "/groups", data=data)

    if DRY_RUN:
        return {
            "id": -1,
            "name": name,
            "path": path,
            "full_path": target_full_path,
        }

    return created


def create_project_if_missing(
    target_full_path: str,
    project_name: str,
    project_path: str,
    namespace_full_path: str,
    visibility: str,
    description: str,
) -> dict:
    existing = get_project_by_full_path(DST_GITLAB, DST_TOKEN, target_full_path)
    if existing:
        print(f"[PROJECT EXISTS] {target_full_path}")
        return existing

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

    print(f"[CREATE PROJECT] {target_full_path}")
    created = api_post(DST_GITLAB, DST_TOKEN, "/projects", data=data)

    if DRY_RUN:
        return {
            "id": -1,
            "name": project_name,
            "path": project_path,
            "path_with_namespace": target_full_path,
        }

    return created


def tokenized_repo_url(base: str, token: str, full_path: str) -> str:
    parsed = urllib.parse.urlparse(base)
    host = parsed.netloc
    scheme = parsed.scheme
    return f"{scheme}://oauth2:{urllib.parse.quote(token, safe='')}@{host}/{full_path}.git"


def run(cmd: List[str], cwd: Optional[str] = None):
    print("+ " + " ".join(cmd))
    if DRY_RUN:
        return

    subprocess.run(cmd, cwd=cwd, check=True)


def mirror_project(src_project: dict, dst_project_full_path: str):
    src_full_path = src_project["path_with_namespace"]

    print(f"[MIRROR] {src_full_path} -> {dst_project_full_path}")

    if DRY_RUN:
        print("[DRY-RUN] skip git clone/push")
        return

    src_url = tokenized_repo_url(SRC_GITLAB, SRC_TOKEN, src_full_path)
    dst_url = tokenized_repo_url(DST_GITLAB, DST_TOKEN, dst_project_full_path)

    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = os.path.join(tmp, "repo.git")

        run(["git", "clone", "--mirror", src_url, repo_dir])
        run(["git", "remote", "set-url", "--push", "origin", dst_url], cwd=repo_dir)
        run(["git", "push", "--mirror"], cwd=repo_dir)


def map_source_to_target_path(src_full_path: str) -> str:
    if not src_full_path.startswith(SRC_ROOT_GROUP):
        raise RuntimeError(f"Source path outside root group: {src_full_path}")

    suffix = src_full_path[len(SRC_ROOT_GROUP):].lstrip("/")
    if suffix:
        return f"{DST_ROOT_GROUP}/{suffix}"
    return DST_ROOT_GROUP


def migrate_group_recursive(src_group: dict):
    src_full_path = src_group["full_path"]
    dst_full_path = map_source_to_target_path(src_full_path)

    parent_src_path = None
    parent_dst_path = None

    if "/" in src_full_path:
        parent_src_path = src_full_path.rsplit("/", 1)[0]
        parent_dst_path = map_source_to_target_path(parent_src_path)

    create_group_if_missing(
        target_full_path=dst_full_path,
        name=src_group["name"],
        path=src_group["path"],
        parent_full_path=parent_dst_path,
        visibility=src_group.get("visibility", "private"),
    )

    projects = list_projects(SRC_GITLAB, SRC_TOKEN, src_group["id"])
    for project in projects:
        src_project_full_path = project["path_with_namespace"]
        dst_project_full_path = map_source_to_target_path(src_project_full_path)
        dst_namespace_full_path = dst_project_full_path.rsplit("/", 1)[0]

        create_project_if_missing(
            target_full_path=dst_project_full_path,
            project_name=project["name"],
            project_path=project["path"],
            namespace_full_path=dst_namespace_full_path,
            visibility=project.get("visibility", "private"),
            description=project.get("description") or "",
        )

        mirror_project(project, dst_project_full_path)

    subgroups = list_subgroups(SRC_GITLAB, SRC_TOKEN, src_group["id"])
    for subgroup in subgroups:
        migrate_group_recursive(subgroup)


def main():
    print(f"Source GitLab: {SRC_GITLAB}")
    print(f"Target GitLab: {DST_GITLAB}")
    print(f"Source root group: {SRC_ROOT_GROUP}")
    print(f"Target root group: {DST_ROOT_GROUP}")
    print(f"SSL verify: {VERIFY_SSL}")
    print(f"Dry run: {DRY_RUN}")

    src_root = get_group_by_full_path(SRC_GITLAB, SRC_TOKEN, SRC_ROOT_GROUP)
    if not src_root:
        raise RuntimeError(f"Source group not found: {SRC_ROOT_GROUP}")

    # If the target root group does not exist, create it as top-level.
    create_group_if_missing(
        target_full_path=DST_ROOT_GROUP,
        name=src_root["name"] if DST_ROOT_GROUP == SRC_ROOT_GROUP else DST_ROOT_GROUP.split("/")[-1],
        path=DST_ROOT_GROUP.split("/")[-1],
        parent_full_path=DST_ROOT_GROUP.rsplit("/", 1)[0] if "/" in DST_ROOT_GROUP else None,
        visibility=src_root.get("visibility", "private"),
    )

    migrate_group_recursive(src_root)

    print("[DONE]")


if __name__ == "__main__":
    main()
