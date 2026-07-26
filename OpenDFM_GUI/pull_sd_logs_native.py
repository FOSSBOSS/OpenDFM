#!/usr/bin/env python3
"""Recursively download selected FC6A SD-card logs through Maintenance Protocol."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Optional

from MiSmSDCard import MiSmSDCard, VERSION as SD_VERSION
from MiSmTCP import MiSmTCP
from open_dfm_backend import (
    download_file, human_size, parse_log_date, relative_path, scan_tree,
)

DEFAULT_HOST = "192.168.1.61"
DEFAULT_REMOTE = "/FCDATA01/DATALOG"
DEFAULT_OUTPUT = "DATALOG"
VERSION = "2026.07.16.1"


class TransferProgress:
    def __init__(self):
        self.last_print = 0.0

    def __call__(
        self, done: int, total: int, current: float, average: float,
    ) -> None:
        now = time.monotonic()
        if done != total and now - self.last_print < 0.5:
            return
        percent = done * 100.0 / total if total else 100.0
        text = (
            f"\r  {percent:6.2f}%  {human_size(done)} / {human_size(total)}  "
            f"{human_size(current)}/s  avg {human_size(average)}/s"
        )
        print(text.ljust(92), end="", flush=True)
        self.last_print = now
        if done == total:
            print()


def cli_date(value: str):
    try:
        return parse_log_date(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; use YYYYMMDD or YYYY-MM-DD"
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=2101)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument(
        "--block-size", type=lambda value: int(value, 0), default=0x5C0,
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--list-only", action="store_true")
    parser.add_argument(
        "--days", type=int, metavar="N",
        help="download N calendar days ending at the newest folder or --end-date",
    )
    parser.add_argument(
        "--start-date", type=cli_date, metavar="YYYYMMDD",
        help="first log-folder date to include, inclusive",
    )
    parser.add_argument(
        "--end-date", type=cli_date, metavar="YYYYMMDD",
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
            status=print,
        )
        if start is not None:
            print(f"\nDate range: {start:%Y%m%d} through {end:%Y%m%d}, inclusive")

        total = sum(int(item["size"]) for item in files)
        print(
            f"Found {len(dirs) - 1} folders and {len(files)} files, "
            f"{human_size(total)} total."
        )

        if args.list_only:
            for remote_dir in dirs[1:]:
                print(f"[DIR]  {remote_dir}")
            for item in files:
                marker = "FILE" if item.get("default_selected", True) else "INFO"
                print(f'[{marker}] {item["full_path"]}  {item["size"]} bytes')
            return 0

        selected = [item for item in files if item.get("default_selected", True)]
        if not selected:
            print("No date-filtered files were selected. Use --list-only or another path.")
            return 0

        output.mkdir(parents=True, exist_ok=True)
        for remote_dir in dirs:
            (output / relative_path(args.remote, remote_dir)).mkdir(
                parents=True, exist_ok=True,
            )

        downloaded = skipped = failed = 0
        for item in selected:
            remote = str(item["full_path"])
            local = output / relative_path(args.remote, remote)
            print(f"GET  {remote}")
            try:
                state = download_file(
                    plc, sd, remote, local, int(item["size"]),
                    retries=args.retries, block_size=args.block_size,
                    overwrite=args.overwrite, progress=TransferProgress(),
                    status=print,
                )
                if state == "downloaded":
                    downloaded += 1
                else:
                    skipped += 1
            except KeyboardInterrupt:
                print("\nStopped. The current .part file was retained.")
                return 130
            except Exception as exc:
                failed += 1
                print(f"FAILED {remote}: {exc}")

        print(
            f"\nDone. Downloaded {downloaded}; skipped {skipped}; failed {failed}."
        )
        return 1 if failed else 0
    finally:
        plc.close()


if __name__ == "__main__":
    raise SystemExit(main())
