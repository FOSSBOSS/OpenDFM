# OpenDFM GUI

OpenDFM GUI is a tabbed PyQt5 application for browsing and downloading files from
SD cards installed in IDEC PLCs.

Each tab represents one PLC. Different PLCs can be scanned or downloaded
concurrently, while files within each tab transfer sequentially.

![OpenDFM GUI with two PLC tabs](../imgs/UI_Help.png)

## Main features

- Multiple independent PLC tabs.
- Concurrent operations against different PLC endpoints.
- Breadth-first remote folder discovery.
- A hierarchical folder and file tree.
- Date-folder filtering at any depth below the selected remote path.
- Selectable files and preserved directory structure.
- Per-file and overall transfer progress.
- Current and average transfer-rate displays.
- Configurable timeout and retry count.
- `.part` files for interrupted or failed downloads.
- Immediate STOP behavior that aborts the active TCP socket.
- Saved window, tab, connection, date-filter, and output settings.

## Requirements

- Python 3.
- PyQt5.
- Network access to the PLC.
- An IDEC PLC with Ethernet connection configured for Maintenance Communication.
- An inserted and recognized PLC SD card.
- A valid remote SD-card path.

On Linux Mint or Ubuntu:

```bash
sudo apt install python3-pyqt5
```

Keep the included Python modules and `.ui` files together in the
`OpenDFM_GUI` directory.

## Run

From the repository root:

```bash
cd OpenDFM_GUI
python3 OpenDFM.py
```

The script is also executable:

```bash
./OpenDFM.py
```

## Basic workflow

1. Enter the PLC IP address.
2. Verify the Maintenance Communication port. The default is `2101`.
3. Enter a valid remote SD-card directory.
4. Choose a date-selection mode.
5. Click **Scan PLC**.
6. Expand the folder tree and select the files to retrieve.
7. Choose a local output folder.
8. Click **Download selected**.

## PLC tabs

Click **Add a PLC** to create another tab.

Each tab has its own:

- PLC IP address and port.
- Timeout and retry settings.
- Remote path.
- Date filter.
- Output folder.
- File selection.
- Progress and status log.
- STOP control.

Different PLC tabs may operate at the same time. OpenDFM blocks a second active
operation against the same IP address and port, preventing two tabs from
interfering with the same PLC session.

New PLC tabs start with a blank IP address and a separate output directory.

## Connection settings

### IP address

Enter the address of the IDEC PLC containing the SD card.

Example:

```text
192.168.1.61
```

### Port

The default Maintenance Communication TCP port is:

```text
2101
```

Change this only when the PLC project uses another configured port.

### Timeout

The timeout controls how long OpenDFM waits for a PLC network operation.

A longer timeout may help on a slow or unreliable network, but it also increases
the time before an unavailable PLC is reported.

### Retries

The retry count applies to transient directory-listing and download failures.

Protocol errors, such as an invalid remote path, are reported immediately rather
than repeatedly reopening the same invalid directory.

## Remote path browsing

The **Remote path** field is the root of the current scan. It does not have to be
the final data-log directory.

The default is:

```text
/FCDATA01/DATALOG
```

Other valid project layouts may include:

```text
/FCDATA01/DATALOG/Alarms/YYYYMMDD
/FCDATA01/DATALOG/runlogs/YYYYMMDD
/FCDATA01/DATALOG/1-secLog/YYYYMMDD
```

OpenDFM discovers folders breadth-first. Top-level folders appear before the
program descends into older or deeper log directories.

Double-click a discovered folder to:

1. Stop the current broad scan.
2. Put that folder's complete path into the **Remote path** field.
3. Continue scanning from the selected folder.

This is useful when the PLC's exact logging path is not known in advance.

## Date selection

OpenDFM provides three modes.

### All dates

Scans and displays all files below the selected remote path.

### Last N calendar days

Uses the newest discovered `YYYYMMDD` folder as the end date and includes the
requested number of calendar days.

For example, a four-day selection ending at `20260726` covers:

```text
20260723 through 20260726
```

Folders do not have to exist for every calendar day.

### Date range

Uses an inclusive start and end date.

Date folders are recognized by an eight-digit `YYYYMMDD` name. They may exist at
any depth below the entered remote path.

When a date filter is selected but no `YYYYMMDD` folder is found below a valid
path, OpenDFM still displays the discovered directory tree and loose files. Loose
files start unchecked because the date filter could not be applied to them.

## File selection

After a successful scan, files appear with:

- A checkbox.
- Their remote name and folder location.
- Their size.
- Their current status.

Use **Select all** or **Clear all** to change the entire selection.

OpenDFM shows the number of selected files and their combined size before the
download starts.

## Output folder

Choose the local root folder where the selected files will be stored.

OpenDFM preserves the directory structure below the selected remote root.

For example, with:

```text
Remote root:
/FCDATA01/DATALOG

Remote file:
/FCDATA01/DATALOG/1-secLog/20260726/20260726_00.csv

Output folder:
/home/user/PLC-1/DATALOG
```

the local file becomes:

```text
/home/user/PLC-1/DATALOG/1-secLog/20260726/20260726_00.csv
```

## Existing and partial files

### Completed files

When a local file already exists with the expected size, OpenDFM marks it as
already present and skips it.

Enable **Overwrite completed files** to download it again.

### Partial files

A file is first written as:

```text
filename.csv.part
```

The `.part` suffix is removed only after the complete expected file size has been
received.

If the operation fails or is stopped, the partial file is retained. The current
protocol implementation cannot resume at a byte offset, so a later retry restarts
that file from the beginning.

## Download progress

During a download, OpenDFM displays:

- The current remote filename.
- File number and total selected file count.
- Current file percentage and byte count.
- Overall file progress.
- Current transfer rate.
- Average transfer rate.
- Per-file status in the file tree.
- Detailed operation messages in the log pane.

A downloaded file is checked against the size reported by the PLC. A size
mismatch is treated as a failed attempt.

## STOP behavior

Click **STOP** to interrupt the active operation in that tab.

OpenDFM:

- Sets the cancellation request.
- Shuts down and closes the active TCP socket.
- Prevents an automatic reconnect after the explicit abort.
- Stops directory-list retries and retry delays.
- Retains the current `.part` file.

Stopping one PLC tab does not stop operations running in other tabs.

Closing a busy tab or closing OpenDFM prompts before stopping active operations.

## Common errors

### Remote SD path does not exist

```text
Remote SD path does not exist: /FCDATA01/DATALOG
Verify the SD Card is inserted. (PLC code 22)
```

Check both possibilities:

- The SD card is missing or is not recognized by the PLC.
- The entered directory does not exist on that SD card.

### Connection refused or timed out

Verify:

- The PLC IP address.
- The computer's network interface and subnet.
- The configured Maintenance Communication port.
- That another program is not holding the PLC connection.
- That the PLC is powered and reachable.

### Endpoint already active

OpenDFM does not allow two active tabs to use the same IP address and port.

Wait for the first operation to finish or press **STOP** in the active tab.

### PLC or date settings changed

A download is tied to the settings used for the completed scan. Scan the PLC again
after changing the IP address, port, remote path, timeout, retry count, or date
filter.

### Output error

Verify that the selected output directory is writable and that the local disk has
enough free space.

## Saved settings

OpenDFM saves its window geometry and PLC tab settings when the application closes
normally.

Saved tab settings include:

- IP address and port.
- Remote path.
- Output folder.
- Timeout and retries.
- Date-selection mode and values.
- Overwrite setting.

OpenDFM restores those tabs and settings at the next launch. Confirm the PLC and
output paths before starting a new operation.

## Application safety

The GUI exposes SD-card listing and downloading only. It does not provide controls
for deleting or uploading PLC SD-card files, and it does not modify the PLC
program.

## Files

| File | Purpose |
| --- | --- |
| `OpenDFM.py` | Main window, PLC tabs, worker threads, settings, progress, and error handling |
| `OpenDFM.ui` | Editable Qt Designer main-window layout |
| `OpenDFMTab.ui` | Editable Qt Designer layout used by each PLC tab |
| `open_dfm_backend.py` | Shared directory discovery, date filtering, and download logic |
| `MiSmSDCard.py` | SD-card Maintenance Protocol helper |
| `MiSmTCP.py` | TCP Maintenance Protocol transport |
| `pull_sd_logs_native.py` | Command-line downloader using the same backend |
| `CHANGELOG.txt` | Release history |

## Current limitations

- Transfer speed is limited by the PLC and SD-card protocol.
- Interrupted downloads cannot resume from the previous byte offset.
- Files within one PLC tab download sequentially.
- The GUI currently communicates over Ethernet through `MiSmTCP`.
- Date filtering recognizes folders named `YYYYMMDD`.
- The default remote path is only an example; PLC projects may use another
  directory structure.

## Changelog

See [CHANGELOG.txt](CHANGELOG.txt) for release-specific changes.
