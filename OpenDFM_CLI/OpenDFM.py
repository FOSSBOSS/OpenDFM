#!/usr/bin/env python3
"""Recursively download selected FC6A SD-card logs through Maintenance Protocol."""

from __future__ import annotations

import argparse
import os
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional, Tuple

from MiSmSDCard import MiSmSDCard, VERSION as SD_VERSION
from MiSmTCP import MiSmTCP

DEFAULT_HOST = "192.168.1.61"
DEFAULT_REMOTE = "/FCDATA01/DATALOG/1-secLog"
DEFAULT_OUTPUT = "1-secLog"
DATE_FOLDER = re.compile(r"^[0-9]{8}$")
VERSION = "2026.07.14.2"


def human_size(value: float) -> str:
    units = ("B", "KiB", "MiB", "GiB")
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} GiB"


class TransferProgress:
    def __init__(self, name: str):
        self.name = name
        self.start = time.monotonic()
        self.sample_time = self.start
        self.sample_bytes = 0
        self.last_print = 0.0

    def __call__(self, done: int, total: int) -> None:
        now = time.monotonic()
        if done != total and now - self.last_print < 0.5:
            return

        elapsed = max(now - self.sample_time, 0.001)
        current = (done - self.sample_bytes) / elapsed
        average = done / max(now - self.start, 0.001)
        percent = done * 100.0 / total if total else 100.0
        text = (
            f"\r  {percent:6.2f}%  {human_size(done)} / {human_size(total)}  "
            f"{human_size(current)}/s  avg {human_size(average)}/s"
        )
        print(text.ljust(92), end="", flush=True)
        self.sample_time = now
        self.sample_bytes = done
        self.last_print = now
        if done == total:
            print()


def parse_log_date(value: str) -> date:
    compact = value.strip().replace("-", "")
    try:
        return datetime.strptime(compact, "%Y%m%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; use YYYYMMDD or YYYY-MM-DD"
        ) from exc


def folder_date(name: str) -> Optional[date]:
    if not DATE_FOLDER.fullmatch(name):
        return None
    try:
        return datetime.strptime(name, "%Y%m%d").date()
    except ValueError:
        return None


def join_remote(path: str, name: str) -> str:
    return path.rstrip("/") + "/" + name


def safe_entry_name(entry: Dict[str, Any]) -> str:
    name = str(entry["name"])
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(f"Unsafe SD-card entry name: {name!r}")
    return name


def resolve_date_range(
    root_entries: List[Dict[str, Any]], days: Optional[int], start: Optional[date],
    end: Optional[date],
) -> Tuple[Optional[date], Optional[date]]:
    if days is None and start is None and end is None:
        return None, None

    available = sorted(
        value for entry in root_entries
        if entry.get("is_dir")
        for value in [folder_date(str(entry["name"]))]
        if value is not None
    )
    if not available:
        raise ValueError("No YYYYMMDD log folders were found below the remote path")

    if days is not None:
        if days < 1:
            raise ValueError("--days must be at least 1")
        if start is not None:
            raise ValueError("--days cannot be combined with --start-date")
        end = end or available[-1]
        start = end - timedelta(days=days - 1)
    else:
        start = start or available[0]
        end = end or available[-1]

    if start > end:
        raise ValueError("start date must not be later than end date")
    return start, end


def scan_tree(
    sd: MiSmSDCard, root: str, days: Optional[int] = None,
    start: Optional[date] = None, end: Optional[date] = None,
) -> Tuple[List[str], List[Dict[str, Any]], Optional[date], Optional[date]]:
    root = "/" + root.strip("/")
    print(f"Listing {root}")
    root_entries = sd.listSD(root)
    start, end = resolve_date_range(root_entries, days, start, end)

    dirs = [root]
    files: List[Dict[str, Any]] = []
    pending: List[str] = []

    for entry in root_entries:
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
        current = pending.pop()
        print(f"Listing {current}")
        for entry in sd.listSD(current):
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


def relative_path(root: str, remote: str) -> Path:
    root_path = PurePosixPath("/" + root.strip("/"))
    remote_path = PurePosixPath("/" + remote.strip("/"))
    return Path(*remote_path.relative_to(root_path).parts)


def reconnect(plc: MiSmTCP) -> None:
    plc.close()
    time.sleep(0.25)
    plc.connect()


def download_file(
    plc: MiSmTCP, sd: MiSmSDCard, remote: str, local: Path, expected: int,
    retries: int, block_size: int, overwrite: bool,
) -> bool:
    if local.exists() and local.stat().st_size == expected and not overwrite:
        print(f"SKIP {remote} ({human_size(expected)})")
        return False

    local.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, retries + 1):
        print(f"GET  {remote}")
        try:
            progress = TransferProgress(local.name)
            sd.saveSD(
                remote, local_path=os.fspath(local), block_size=block_size,
                progress=progress,
            )
            actual = local.stat().st_size
            if actual != expected:
                raise IOError(f"size mismatch: expected {expected}, downloaded {actual}")
            return True
        except KeyboardInterrupt:
            partial = Path(os.fspath(local) + ".part")
            if partial.exists():
                print(f"\nPartial file retained: {partial} ({human_size(partial.stat().st_size)})")
            raise
        except Exception as exc:
            partial = Path(os.fspath(local) + ".part")
            suffix = ""
            if partial.exists():
                suffix = f"; partial retained at {partial} ({human_size(partial.stat().st_size)})"
            print(f"  attempt {attempt}/{retries} failed: {exc}{suffix}")
            if attempt == retries:
                raise
            reconnect(plc)
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=2101)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--block-size", type=lambda value: int(value, 0), default=0x5C0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument(
        "--days", type=int, metavar="N",
        help="download N calendar days ending at the newest PLC folder or --end-date",
    )
    parser.add_argument(
        "--start-date", type=parse_log_date, metavar="YYYYMMDD",
        help="first log-folder date to include, inclusive",
    )
    parser.add_argument(
        "--end-date", type=parse_log_date, metavar="YYYYMMDD",
        help="last log-folder date to include, inclusive",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(f"pull_sd_logs_native {VERSION}; MiSmSDCard {SD_VERSION}")
    output = Path(args.output)
    plc = MiSmTCP(args.host, port=args.port, timeout=args.timeout)
    sd = MiSmSDCard(plc, timeout=args.timeout, retries=args.retries)

    try:
        dirs, files, start, end = scan_tree(
            sd, args.remote, args.days, args.start_date, args.end_date,
        )
        if start is not None:
            print(f"\nDate range: {start:%Y%m%d} through {end:%Y%m%d}, inclusive")

        total = sum(int(item["size"]) for item in files)
        print(f"Found {len(dirs) - 1} folders and {len(files)} files, "
              f"{human_size(total)} total.")

        output.mkdir(parents=True, exist_ok=True)
        for remote_dir in dirs:
            local_dir = output / relative_path(args.remote, remote_dir)
            local_dir.mkdir(parents=True, exist_ok=True)

        if args.list_only:
            for item in files:
                print(f'{item["full_path"]}  {item["size"]} bytes')
            return 0

        downloaded = 0
        for item in files:
            remote = item["full_path"]
            local = output / relative_path(args.remote, remote)
            if download_file(
                plc, sd, remote, local, int(item["size"]), args.retries,
                args.block_size, args.overwrite,
            ):
                downloaded += 1

        print(f"\nDone. Downloaded {downloaded}; skipped {len(files) - downloaded}.")
        return 0
    finally:
        plc.close()


if __name__ == "__main__":
    raise SystemExit(main())
