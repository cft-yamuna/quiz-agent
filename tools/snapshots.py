"""Snapshot engine — take/list/revert project snapshots for undo support."""

import os
import json
import shutil
import time
import uuid

# Files/dirs to snapshot from the project root
SNAPSHOT_ITEMS = [
    "src",
    "package.json",
    "vite.config.js",
    "index.html",
    ".chat_history.json",
    ".project_memory.json",
]

MAX_SNAPSHOTS = 5

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _snapshots_dir(project_name):
    """Return the .snapshots directory for a project."""
    return os.path.join(BASE_DIR, "output", project_name, ".snapshots")


def take_snapshot(project_name, session_id, user_prompt=""):
    """Copy key project files into a timestamped snapshot folder.

    Args:
        project_name: Name of the project in output/
        session_id: Unique session identifier (used as snapshot ID)
        user_prompt: First ~100 chars of the user prompt (for manifest)

    Returns:
        The snapshot_id (same as session_id) or None on failure.
    """
    project_dir = os.path.join(BASE_DIR, "output", project_name)
    if not os.path.isdir(project_dir):
        return None

    snap_dir = _snapshots_dir(project_name)
    snapshot_id = session_id or uuid.uuid4().hex[:8]
    dest = os.path.join(snap_dir, snapshot_id)
    os.makedirs(dest, exist_ok=True)

    # Copy each item
    for item in SNAPSHOT_ITEMS:
        src_path = os.path.join(project_dir, item)
        dst_path = os.path.join(dest, item)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
        elif os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)

    # Write manifest
    manifest = {
        "snapshot_id": snapshot_id,
        "timestamp": time.time(),
        "iso_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "prompt_preview": user_prompt[:100] if user_prompt else "",
    }
    with open(os.path.join(dest, "_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Prune old snapshots (keep newest MAX_SNAPSHOTS)
    _prune_snapshots(project_name)

    return snapshot_id


def list_snapshots(project_name):
    """Return list of snapshot manifest dicts, newest-first."""
    snap_dir = _snapshots_dir(project_name)
    if not os.path.isdir(snap_dir):
        return []

    snapshots = []
    for entry in os.listdir(snap_dir):
        manifest_path = os.path.join(snap_dir, entry, "_manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                manifest["snapshot_id"] = entry  # ensure ID is set
                snapshots.append(manifest)
            except Exception:
                continue

    # Sort newest-first
    snapshots.sort(key=lambda s: s.get("timestamp", 0), reverse=True)
    return snapshots


def revert_to_snapshot(project_name, snapshot_id):
    """Restore project files from a snapshot, then remove that snapshot and all newer ones.

    Args:
        project_name: Name of the project
        snapshot_id: The snapshot to revert to

    Returns:
        dict with "status" key ("ok" or "error") and optional "message".
    """
    project_dir = os.path.join(BASE_DIR, "output", project_name)
    snap_dir = _snapshots_dir(project_name)
    source = os.path.join(snap_dir, snapshot_id)

    if not os.path.isdir(source):
        return {"status": "error", "message": f"Snapshot '{snapshot_id}' not found."}

    # Read target manifest to get its timestamp
    manifest_path = os.path.join(source, "_manifest.json")
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            target_manifest = json.load(f)
        target_ts = target_manifest.get("timestamp", 0)
    except Exception:
        return {"status": "error", "message": "Could not read snapshot manifest."}

    # Restore files from snapshot back to project dir
    for item in SNAPSHOT_ITEMS:
        src_path = os.path.join(source, item)
        dst_path = os.path.join(project_dir, item)

        if os.path.isdir(src_path):
            # Remove existing dir first, then copy
            if os.path.isdir(dst_path):
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
        elif os.path.isfile(src_path):
            shutil.copy2(src_path, dst_path)

    # Remove the target snapshot and all newer ones
    all_snapshots = list_snapshots(project_name)
    for snap in all_snapshots:
        if snap.get("timestamp", 0) >= target_ts:
            snap_path = os.path.join(snap_dir, snap["snapshot_id"])
            if os.path.isdir(snap_path):
                shutil.rmtree(snap_path)

    return {"status": "ok", "message": "Reverted successfully."}


def _prune_snapshots(project_name):
    """Keep only the newest MAX_SNAPSHOTS snapshots."""
    all_snapshots = list_snapshots(project_name)
    if len(all_snapshots) <= MAX_SNAPSHOTS:
        return

    snap_dir = _snapshots_dir(project_name)
    # all_snapshots is newest-first; remove from index MAX_SNAPSHOTS onward
    for old in all_snapshots[MAX_SNAPSHOTS:]:
        snap_path = os.path.join(snap_dir, old["snapshot_id"])
        if os.path.isdir(snap_path):
            shutil.rmtree(snap_path)
