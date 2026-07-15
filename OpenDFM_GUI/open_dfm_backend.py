#!/usr/bin/env python3
"""Shared scan and download helpers for OpenDFM."""

from __future__ import annotations

import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from threading import Event
from typing import Any, Callable, Dict, List, Optional, Tuple

from MiSmSDCard import MiSmSDCard

DATE_FOLDER = re.compile(r"^[0-9]{8}$")
StatusCallback = Optional[Callable[[str], None]]
ProgressCallback = Optional[Callable[[int, int, float, float], None]]


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
    root_entries: List[Dict[str, Any]], days: Optional[int], start: Optional[date],
    end: Optional[date],
) -> Tuple[Optional[date], Optional[date]]:
    if days is None and start is None and end is None:
        return None, None

    available = sorted(
        value for entry in root_entries if entry.get("is_dir")
        for value in [folder_date(str(entry["name"]))] if value is not None
    )
    if not available:
        raise ValueError("No YYYYMMDD log folders were found below the remote path")

    if days is not None:
        if days < 1:
            raise ValueError("Days must be at least 1")
        if start is not None:
            raise ValueError("Last N days cannot be combined with a start date")
        end = end or available[-1]
        start = end - timedelta(days=days - 1)
    else:
        start = start or available[0]
        end = end or available[-1]

    if start > end:
        raise ValueError("Start date must not be later than end date")
    return start, end


def scan_tree(
    sd: MiSmSDCard, root: str, days: Optional[int] = None,
    start: Optional[date] = None, end: Optional[date] = None,
    status: StatusCallback = None, cancel: Optional[Event] = None,
) -> Tuple[List[str], List[Dict[str, Any]], Optional[date], Optional[date]]:
    root = "/" + root.strip("/")
    check_cancel(cancel)
    if status:
        status(f"Listing {root}")
    root_entries = sd.listSD(root)
    start, end = resolve_date_range(root_entries, days, start, end)

    dirs = [root]
    files: List[Dict[str, Any]] = []
    pending: List[str] = []

    for entry in root_entries:
        check_cancel(cancel)
        name = safe_entry_name(entry)
        full_path = join_remote(root, name)
        if entry.get("is_dir"):
            value = folder_date(name)
            if start is not None and (value is None or not start <= value <= end):
                continue
            dirs.append(full_path)
            pending.append(full_path)
        elif start is None:
            item = dict(entry)
            item["full_path"] = full_path
            files.append(item)

    pending.sort(reverse=True)
    while pending:
        check_cancel(cancel)
        current = pending.pop()
        if status:
            status(f"Listing {current}")
        for entry in sd.listSD(current):
            check_cancel(cancel)
            name = safe_entry_name(entry)
            full_path = join_remote(current, name)
            if entry.get("is_dir"):
                dirs.append(full_path)
                pending.append(full_path)
            else:
                item = dict(entry)
                item["full_path"] = full_path
                files.append(item)

    dirs.sort()
    files.sort(key=lambda item: item["full_path"])
    return dirs, files, start, end


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
                suffix = f"; partial retained: {partial} ({human_size(partial.stat().st_size)})"
            if status:
                status(f"Attempt {attempt}/{attempts} failed: {exc}{suffix}")
            if attempt == attempts:
                raise
            reset_transport(plc)

    raise RuntimeError("unreachable")
