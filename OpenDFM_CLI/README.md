# OpenDFM CLI

OpenDFM CLI recursively lists and downloads files from an SD card installed in
an IDEC PLC over the Ethernet Maintenance Protocol.

This is the original single-PLC command-line version of OpenDFM. It is useful for
manual collection, shell scripts, scheduled jobs, and systems where a graphical
desktop is not available.

> **Current CLI build:** `2026.07.14.2`

## What it does

- Connects to one IDEC PLC over TCP.
- Lists the selected remote SD-card directory.
- Recursively discovers files and subdirectories.
- Optionally filters direct child folders named `YYYYMMDD`.
- Downloads files while preserving the remote directory structure.
- Displays current and average transfer speed.
- Retries transient directory and file-transfer failures.
- Verifies the final downloaded file size.
- Retains interrupted or failed transfers as `.part` files.
- Skips complete local files unless `--overwrite` is used.
- Supports a listing-only mode for previewing a collection.

OpenDFM CLI only lists and downloads files. It does not upload files, delete
files, or modify the PLC program.

## Files

Keep these files together in the `OpenDFM_CLI` directory:

| File | Purpose |
| --- | --- |
| `OpenDFM.py` | Command-line application |
| `MiSmSDCard.py` | SD-card Maintenance Protocol helper |
| `MiSmTCP.py` | TCP Maintenance Protocol transport |
| `README.md` | This documentation |

## Requirements

- Python 3.
- Network access to the PLC.
- An IDEC PLC Ethernet connection configured for Maintenance Communication.
- An inserted and recognized PLC SD card.
- A valid remote directory on the PLC SD card.

The CLI uses Python's standard library and the included OpenDFM modules. It does
not require PyQt5.

## Installation

Clone the repository:

```bash
git clone https://github.com/FOSSBOSS/OpenDFM.git
cd OpenDFM/OpenDFM_CLI
```

The script can be run through Python:

```bash
python3 OpenDFM.py --help
```

Or made executable:

```bash
chmod +x OpenDFM.py
./OpenDFM.py --help
```

## Default configuration

Running the program without arguments uses:

| Setting | Default |
| --- | --- |
| PLC address | `192.168.1.61` |
| TCP port | `2101` |
| Remote path | `/FCDATA01/DATALOG/1-secLog` |
| Local output | `1-secLog` |
| Timeout | `5.0` seconds |
| Retries | `4` |
| File block size | `0x5C0` (`1472` bytes) |
| Date filter | None |
| Overwrite | Disabled |

Default run:

```bash
python3 OpenDFM.py
```

This recursively downloads every file below:

```text
/FCDATA01/DATALOG/1-secLog
```

into a local directory named:

```text
1-secLog
```

## Command-line syntax

```text
OpenDFM.py [-h] [--version] [--host HOST] [--port PORT]
           [--remote REMOTE] [--output OUTPUT] [--timeout TIMEOUT]
           [--retries RETRIES] [--block-size BLOCK_SIZE]
           [--overwrite] [--list-only] [--days N]
           [--start-date YYYYMMDD] [--end-date YYYYMMDD]
```

Display the built-in help:

```bash
python3 OpenDFM.py --help
```

Display the CLI version:

```bash
python3 OpenDFM.py --version
```

## Command-line arguments

| Argument | Default | Description |
| --- | --- | --- |
| `-h`, `--help` | — | Display the built-in help and exit. |
| `--version` | — | Display the CLI build version and exit. |
| `--host HOST` | `192.168.1.61` | PLC IPv4 address or resolvable hostname. |
| `--port PORT` | `2101` | PLC Maintenance Communication TCP port. |
| `--remote REMOTE` | `/FCDATA01/DATALOG/1-secLog` | Remote SD-card directory used as the scan root. |
| `--output OUTPUT` | `1-secLog` | Local output root. Relative paths are resolved from the current working directory. |
| `--timeout TIMEOUT` | `5.0` | TCP and SD-card operation timeout in seconds. |
| `--retries RETRIES` | `4` | Number of directory-listing and file-download attempts. Use a value of at least `1`. |
| `--block-size BLOCK_SIZE` | `0x5C0` | Requested file-transfer block size. Decimal and Python-style hexadecimal values are accepted. |
| `--overwrite` | Disabled | Download files again instead of skipping complete local files with the expected size. |
| `--list-only` | Disabled | List the files selected by the scan without downloading their contents. |
| `--days N` | None | Select an N-calendar-day window ending at the newest available date folder or at `--end-date`. |
| `--start-date YYYYMMDD` | None | First date-folder name to include, inclusive. |
| `--end-date YYYYMMDD` | None | Last date-folder name to include, inclusive. |

Dates may be entered with or without hyphens:

```text
20260704
2026-07-04
```

## Date filtering

### Important directory-layout requirement

The current CLI only applies date filtering to `YYYYMMDD` directories that are
**direct children of the selected `--remote` path**.

This layout works:

```text
/FCDATA01/DATALOG/1-secLog/
├── 20260723/
├── 20260724/
├── 20260725/
└── 20260726/
```

Use:

```bash
python3 OpenDFM.py \
    --remote /FCDATA01/DATALOG/1-secLog \
    --days 4
```

This layout does not work when `--remote` is `/FCDATA01/DATALOG`:

```text
/FCDATA01/DATALOG/
└── 1-secLog/
    ├── 20260725/
    └── 20260726/
```

For that layout, set the remote root to the folder immediately above the dates:

```bash
python3 OpenDFM.py \
    --remote /FCDATA01/DATALOG/1-secLog \
    --days 2
```

The newer OpenDFM GUI can discover date folders below intermediate directories.
The current CLI cannot.

### No date arguments

With no date arguments, OpenDFM recursively lists and downloads every file and
directory below `--remote`.

```bash
python3 OpenDFM.py
```

### Last N calendar days

The end date defaults to the newest valid date folder directly below the remote
root.

```bash
python3 OpenDFM.py --days 5
```

If the newest PLC folder is `20260726`, this selects the inclusive calendar
window:

```text
20260722 through 20260726
```

Only date folders that actually exist are scanned. Missing calendar days do not
cause an error.

### Last N days ending on a specified date

`--days` may be combined with `--end-date`:

```bash
python3 OpenDFM.py \
    --days 5 \
    --end-date 20260704
```

This selects:

```text
20260630 through 20260704
```

### Inclusive date range

```bash
python3 OpenDFM.py \
    --start-date 20260630 \
    --end-date 20260704
```

Both endpoints are included.

### Open-ended date ranges

A start date without an end date continues through the newest available date
folder:

```bash
python3 OpenDFM.py --start-date 20260701
```

An end date without a start date begins at the oldest available date folder:

```bash
python3 OpenDFM.py --end-date 20260704
```

### Invalid combinations

`--days` cannot be combined with `--start-date`:

```bash
python3 OpenDFM.py --days 5 --start-date 20260701
```

Use either:

```bash
python3 OpenDFM.py --days 5 --end-date 20260705
```

or:

```bash
python3 OpenDFM.py \
    --start-date 20260701 \
    --end-date 20260705
```

The start date must not be later than the end date.

## Usage examples

### Preview all files

```bash
python3 OpenDFM.py --list-only
```

### Preview the last five days

```bash
python3 OpenDFM.py \
    --days 5 \
    --list-only
```

### Download from another PLC

```bash
python3 OpenDFM.py \
    --host 192.168.1.50
```

### Use another PLC port

```bash
python3 OpenDFM.py \
    --host 192.168.1.50 \
    --port 2102
```

### Select another log directory

```bash
python3 OpenDFM.py \
    --remote /FCDATA01/DATALOG/Alarms
```

### Choose a local output directory

```bash
python3 OpenDFM.py \
    --output /home/user/PLC-Logs/PLC-1
```

### Complete incident collection

```bash
python3 OpenDFM.py \
    --host 192.168.1.50 \
    --remote /FCDATA01/DATALOG/1-secLog \
    --output /home/user/incident-20260704 \
    --start-date 20260630 \
    --end-date 20260704
```

### Increase timeout and retries

```bash
python3 OpenDFM.py \
    --timeout 10 \
    --retries 6
```

### Change the transfer block size

Hexadecimal:

```bash
python3 OpenDFM.py --block-size 0x400
```

Decimal:

```bash
python3 OpenDFM.py --block-size 1024
```

The default is `0x5C0`, or `1472` bytes. Change this only when testing transfer
behavior or working around a known network or PLC limitation.

### Download complete files again

```bash
python3 OpenDFM.py --overwrite
```

## Local output layout

OpenDFM preserves the directory structure below the selected remote root.

Given:

```text
Remote root:
/FCDATA01/DATALOG/1-secLog

Remote file:
/FCDATA01/DATALOG/1-secLog/20260726/20260726_00.csv

Output root:
/home/user/PLC-Logs
```

the local file becomes:

```text
/home/user/PLC-Logs/20260726/20260726_00.csv
```

The remote root itself is not repeated below the output directory.

## Listing-only behavior

`--list-only` prevents file contents from being downloaded:

```bash
python3 OpenDFM.py --days 5 --list-only
```

The current implementation creates the selected local output directory and its
discovered subdirectories before printing the file list. It does not create the
actual downloaded files.

Example output:

```text
pull_sd_logs_native 2026.07.14.2; MiSmSDCard 2026.07.14.2
Listing /FCDATA01/DATALOG/1-secLog
Listing /FCDATA01/DATALOG/1-secLog/20260725
Listing /FCDATA01/DATALOG/1-secLog/20260726

Date range: 20260722 through 20260726, inclusive
Found 2 folders and 4 files, 12.8 MiB total.
/FCDATA01/DATALOG/1-secLog/20260725/20260725_00.csv  5242894 bytes
/FCDATA01/DATALOG/1-secLog/20260726/20260726_00.csv  5242894 bytes
```

The startup line still uses the earlier internal name
`pull_sd_logs_native`. The executable in the repository is `OpenDFM.py`.

## Existing files

Before downloading a file, OpenDFM compares the local file size with the size
reported by the PLC.

When both sizes match and `--overwrite` is not enabled, the file is skipped:

```text
SKIP /FCDATA01/DATALOG/1-secLog/20260726/20260726_00.csv (5.0 MiB)
```

If the local file is missing or has another size, OpenDFM downloads it again.

## Partial files

During a transfer, data is written to:

```text
filename.csv.part
```

The `.part` file is renamed to the final filename only after the complete file
has been received.

If a transfer fails or is interrupted with `Ctrl+C`, the `.part` file is
retained and its path and size are reported.

The current protocol implementation does not resume from an existing byte
offset. Retrying the file starts its transfer from the beginning.

## Retries and reconnection

`--retries` controls both:

- Directory-list attempts performed by `MiSmSDCard`.
- File-download attempts performed by the CLI.

After a failed file attempt, OpenDFM closes the TCP connection, waits briefly,
reconnects, and tries the file again.

A file that still fails on its final attempt terminates the command. Files later
in the list are not processed.

Use at least one retry:

```bash
python3 OpenDFM.py --retries 1
```

The default is four attempts:

```bash
python3 OpenDFM.py --retries 4
```

## Transfer progress

For each file, OpenDFM displays:

- Completion percentage.
- Bytes received and total bytes.
- Current transfer rate.
- Average transfer rate.

Example:

```text
GET  /FCDATA01/DATALOG/1-secLog/20260726/20260726_00.csv
   42.73%  2.1 MiB / 5.0 MiB  31.8 KiB/s  avg 30.9 KiB/s
```

After the transfer, OpenDFM verifies that the local file size matches the size
reported by the PLC.

## Exit behavior

A successful listing or download returns exit status `0`.

Argument errors, connection failures, invalid paths, protocol failures, and
exhausted retries return a nonzero status through Python's exception handling.

Pressing `Ctrl+C` stops the operation, retains the active `.part` file, and
closes the PLC connection.

## Troubleshooting

### Connection refused or timed out

Verify:

- The PLC IP address.
- The computer's network interface and subnet.
- The Maintenance Communication TCP port.
- That the PLC is powered and reachable.
- That another application is not using the PLC endpoint.
- That the timeout is long enough for the network.

Useful checks:

```bash
ping -c 3 192.168.1.61
```

```bash
nc -vz 192.168.1.61 2101
```

### No date folders were found

The current CLI expects valid `YYYYMMDD` folders directly below `--remote`.

Inspect the unfiltered root first:

```bash
python3 OpenDFM.py \
    --remote /FCDATA01/DATALOG \
    --list-only
```

Then set `--remote` to the directory immediately above the date folders.

### Remote path error

Verify:

- The SD card is inserted and recognized by the PLC.
- The path exists.
- The path uses forward slashes.
- The selected directory is the correct logging root.

Example:

```text
/FCDATA01/DATALOG/1-secLog
```

### Permission denied locally

Choose an output directory writable by the current user:

```bash
python3 OpenDFM.py \
    --output "$HOME/PLC-Logs"
```

### Transfer repeatedly fails

Try a longer timeout and more attempts:

```bash
python3 OpenDFM.py \
    --timeout 10 \
    --retries 6
```

A smaller block size may also be useful for testing:

```bash
python3 OpenDFM.py \
    --block-size 0x400
```

## Current limitations

- The CLI handles one PLC per process.
- Date folders must be direct children of `--remote`.
- Date-folder names must use the `YYYYMMDD` format.
- A failed file on its final attempt stops the entire run.
- Interrupted downloads cannot resume at the previous byte offset.
- `--list-only` still creates the local output directory tree.
- Transfer speed is limited by the PLC and its SD-card protocol.
- The CLI uses Ethernet through `MiSmTCP`.
- It does not provide the GUI's multi-PLC tabs or progressive folder browser.

For interactive browsing, date discovery below intermediate directories, and
concurrent operations against different PLCs, use the
[OpenDFM GUI](../OpenDFM_GUI/README.md).



<pre>
MiSmSDCard native SD log downloader
Build: 2026.07.14.2

Verify the extracted build:
    ./pull_sd_logs_native.py --version

Expected:
    2026.07.14.2

Last five calendar days ending at newest PLC date folder:
    ./pull_sd_logs_native.py --days 5

Inclusive incident range:
    ./pull_sd_logs_native.py --start-date 20260630 --end-date 20260704

Five-day window ending July 4, 2026:
    ./pull_sd_logs_native.py --days 5 --end-date 20260704

Preview selected files only:
    ./pull_sd_logs_native.py --days 5 --list-only

Default PLC and path:
    192.168.1.61:2101
    /FCDATA01/DATALOG/1-secLog

MiSmSDCard remains transport-neutral and supports MiSmTCP persistent sockets and
MiSmSerial-style objects exposing _ser. Directory listings restart from the
open-directory command after an empty, truncated, or otherwise transient reply.
The command-line --retries setting applies to listings and file downloads.
</pre>
