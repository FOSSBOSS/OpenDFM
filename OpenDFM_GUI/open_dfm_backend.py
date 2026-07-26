#!/usr/bin/env python3
"""Shared scan and download helpers for OpenDFM."""

from __future__ import annotations

import os
import re
import time
from collections import deque
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from threading import Event
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from MiSmSDCard import MiSmSDCard

DATE_FOLDER = re.compile(r"^[0-9]{8}$")
StatusCallback = Optional[Callable[[str], None]]
ProgressCallback = Optional[Callable[[int, int, float, float], None]]
FoldersCallback = Optional[Callable[[str, List[str]], None]]


class TransferCancelled(Exception):
    """Raised when the user requests that an active operation stop."""


def human_size(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} TiB"


def parse_log_date(value: str) -> date:
    compact = value.strip().replace("-", "")
    return datetime.strptime(compact, "%Y%m%d").date()


def folder_date(name: str) -> Optional[date]:
    if not DATE_FOLDER.fullmatch(name):
        return None
    try:
        return datetime.strptime(name, "%Y%m%d").date()
    except ValueError:
        return None


def join_remote(path: str, name: str) -> str:
    return path.rstrip("/") + "/" + name


def relative_path(root: str, remote: str) -> Path:
    root_path = PurePosixPath("/" + root.strip("/"))
    remote_path = PurePosixPath("/" + remote.strip("/"))
    return Path(*remote_path.relative_to(root_path).parts)


def safe_entry_name(entry: Dict[str, Any]) -> str:
    name = str(entry["name"])
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"Unsafe SD-card entry name: {name!r}")
    return name


def check_cancel(cancel: Optional[Event]) -> None:
    if cancel is not None and cancel.is_set():
        raise TransferCancelled("Operation stopped by user")


def resolve_date_range(
    available: Iterable[date], days: Optional[int], start: Optional[date],
    end: Optional[date],
) -> Tuple[date, date]:
    dates = sorted(set(available))
    if not dates:
        raise ValueError("No YYYYMMDD log folders were found below the remote path")

    if days is not None:
        if days < 1:
            raise ValueError("Days must be at least 1")
        if start is not None:
            raise ValueError("Last N days cannot be combined with a start date")
        end = end or dates[-1]
        start = end - timedelta(days=days - 1)
    else:
        start = start or dates[0]
        end = end or dates[-1]

    if start > end:
        raise ValueError("Start date must not be later than end date")
    return start, end


def _list_directory(
    sd: MiSmSDCard, path: str, status: StatusCallback, cancel: Optional[Event],
) -> List[Dict[str, Any]]:
    check_cancel(cancel)
    if status:
        status(f"Listing {path}")
    try:
        entries = sd.listSD(path, cancel=cancel)
    except Exception:
        check_cancel(cancel)
        raise
    check_cancel(cancel)
    return entries


def _file_entry(entry: Dict[str, Any], full_path: str, selected: bool) -> Dict[str, Any]:
    item = dict(entry)
    item["full_path"] = full_path
    item["default_selected"] = selected
    return item


def _scan_all(
    sd: MiSmSDCard, root: str, status: StatusCallback, cancel: Optional[Event],
    folders: FoldersCallback,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    dirs = {root}
    files: List[Dict[str, Any]] = []
    pending = deque([root])

    while pending:
        current = pending.popleft()
        child_dirs: List[str] = []
        for entry in _list_directory(sd, current, status, cancel):
            check_cancel(cancel)
            name = safe_entry_name(entry)
            full_path = join_remote(current, name)
            if entry.get("is_dir"):
                if full_path not in dirs:
                    dirs.add(full_path)
                    child_dirs.append(full_path)
            else:
                files.append(_file_entry(entry, full_path, True))

        child_dirs.sort()
        if folders and child_dirs:
            folders(current, child_dirs)
        pending.extend(child_dirs)

    return sorted(dirs), sorted(files, key=lambda item: item["full_path"])


def _discover_date_folders(
    sd: MiSmSDCard, root: str, status: StatusCallback, cancel: Optional[Event],
    folders: FoldersCallback,
) -> Tuple[set[str], List[Dict[str, Any]], List[Tuple[str, date]]]:
    """Walk non-date folders breadth-first, stopping at YYYYMMDD folders."""
    dirs = {root}
    loose_files: List[Dict[str, Any]] = []
    date_dirs: List[Tuple[str, date]] = []
    root_value = folder_date(PurePosixPath(root).name)

    if root_value is not None:
        date_dirs.append((root, root_value))
        return dirs, loose_files, date_dirs

    pending = deque([root])
    while pending:
        current = pending.popleft()
        child_dirs: List[str] = []
        next_dirs: List[str] = []
        for entry in _list_directory(sd, current, status, cancel):
            check_cancel(cancel)
            name = safe_entry_name(entry)
            full_path = join_remote(current, name)
            if entry.get("is_dir"):
                dirs.add(full_path)
                child_dirs.append(full_path)
                value = folder_date(name)
                if value is None:
                    next_dirs.append(full_path)
                else:
                    date_dirs.append((full_path, value))
            else:
                loose_files.append(_file_entry(entry, full_path, False))

        child_dirs.sort()
        next_dirs.sort()
        if folders and child_dirs:
            folders(current, child_dirs)
        pending.extend(next_dirs)

    date_dirs.sort(key=lambda item: item[0])
    loose_files.sort(key=lambda item: item["full_path"])
    return dirs, loose_files, date_dirs


def _scan_selected_date_folders(
    sd: MiSmSDCard, selected: Iterable[str], dirs: set[str],
    status: StatusCallback, cancel: Optional[Event], folders: FoldersCallback,
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    pending = deque(sorted(selected))

    while pending:
        current = pending.popleft()
        child_dirs: List[str] = []
        for entry in _list_directory(sd, current, status, cancel):
            check_cancel(cancel)
            name = safe_entry_name(entry)
            full_path = join_remote(current, name)
            if entry.get("is_dir"):
                if full_path not in dirs:
                    dirs.add(full_path)
                    child_dirs.append(full_path)
            else:
                files.append(_file_entry(entry, full_path, True))

        child_dirs.sort()
        if folders and child_dirs:
            folders(current, child_dirs)
        pending.extend(child_dirs)

    files.sort(key=lambda item: item["full_path"])
    return files


def scan_tree(
    sd: MiSmSDCard, root: str, days: Optional[int] = None,
    start: Optional[date] = None, end: Optional[date] = None,
    status: StatusCallback = None, cancel: Optional[Event] = None,
    folders: FoldersCallback = None,
) -> Tuple[List[str], List[Dict[str, Any]], Optional[date], Optional[date]]:
    """
    Scan an SD-card path and optionally filter YYYYMMDD folders at any depth.

    Directories are traversed breadth-first, so all siblings at the current level
    are listed before OpenDFM descends into older or deeper log folders.
    """
    root = "/" + root.strip("/")
    requested = days is not None or start is not None or end is not None
    if not requested:
        dirs, files = _scan_all(sd, root, status, cancel, folders)
        return dirs, files, None, None

    dirs, loose_files, date_dirs = _discover_date_folders(
        sd, root, status, cancel, folders,
    )
    if not date_dirs:
        if status:
            status(
                "No YYYYMMDD folders were found. Showing the valid directory "
                "contents without applying the date filter."
            )
        return sorted(dirs), loose_files, None, None

    start, end = resolve_date_range(
        (value for _path, value in date_dirs), days, start, end,
    )
    selected = [
        path for path, value in date_dirs if start <= value <= end
    ]
    if status:
        status(
            f"Found {len(date_dirs)} date folders; scanning {len(selected)} "
            f"from {start:%Y%m%d} through {end:%Y%m%d}."
        )

    files = loose_files + _scan_selected_date_folders(
        sd, selected, dirs, status, cancel, folders,
    )
    files.sort(key=lambda item: item["full_path"])
    return sorted(dirs), files, start, end


def reset_transport(plc: Any) -> None:
    reconnect = getattr(plc, "reconnect", None)
    if callable(reconnect):
        reconnect()
        return

    ser = getattr(plc, "_ser", None)
    if ser is not None:
        for name in ("reset_input_buffer", "reset_output_buffer"):
            fn = getattr(ser, name, None)
            if callable(fn):
                try:
                    fn()
                except Exception:
                    pass
        return

    close = getattr(plc, "close", None)
    connect = getattr(plc, "connect", None)
    if callable(close):
        close()
    if callable(connect):
        time.sleep(0.25)
        connect()


def download_file(
    plc: Any, sd: MiSmSDCard, remote: str, local: Path, expected: int,
    retries: int = 4, block_size: int = 0x5C0, overwrite: bool = False,
    progress: ProgressCallback = None, status: StatusCallback = None,
    cancel: Optional[Event] = None,
) -> str:
    check_cancel(cancel)
    if local.exists() and local.stat().st_size == expected and not overwrite:
        return "skipped"

    local.parent.mkdir(parents=True, exist_ok=True)
    attempts = max(int(retries), 1)

    for attempt in range(1, attempts + 1):
        check_cancel(cancel)
        start_time = time.monotonic()
        sample_time = start_time
        sample_bytes = 0

        def report(done: int, total: int) -> None:
            nonlocal sample_time, sample_bytes
            check_cancel(cancel)
            now = time.monotonic()
            elapsed = max(now - sample_time, 0.001)
            current = (done - sample_bytes) / elapsed
            average = done / max(now - start_time, 0.001)
            sample_time = now
            sample_bytes = done
            if progress:
                progress(done, total, current, average)

        try:
            if status:
                status(f"GET {remote}")
            sd.saveSD(
                remote, local_path=os.fspath(local), block_size=block_size,
                progress=report,
            )
            actual = local.stat().st_size
            if actual != expected:
                raise IOError(
                    f"Size mismatch: expected {expected}, downloaded {actual}"
                )
            return "downloaded"
        except TransferCancelled:
            raise
        except Exception as exc:
            if cancel is not None and cancel.is_set():
                raise TransferCancelled("Operation stopped by user") from exc
            partial = Path(os.fspath(local) + ".part")
            suffix = ""
            if partial.exists():
                size = human_size(partial.stat().st_size)
                suffix = f"; partial retained: {partial} ({size})"
            if status:
                status(f"Attempt {attempt}/{attempts} failed: {exc}{suffix}")
            if attempt == attempts:
                raise
            reset_transport(plc)

    raise RuntimeError("unreachable")
