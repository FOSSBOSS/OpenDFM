OpenDFM Multi-PLC - FC6A SD Log Downloader GUI
================================================

Version
-------
2026.07.16.1

Requirements
------------
Python 3 and PyQt5. On Linux Mint/Ubuntu:

    sudo apt install python3-pyqt5

Run
---

    ./OpenDFM.py

or:

    python3 OpenDFM.py

Remote path browsing
--------------------
The remote path is now a browse root. The default for new tabs is:

    /FCDATA01/DATALOG

Scan PLC displays folders breadth-first while the scan is still running. This
means top-level paths appear before OpenDFM descends into months of log folders.
Double-click a discovered folder at any time to stop the broad scan, put its full
path into the Remote path field, and automatically continue from that folder.

This supports PLC projects whose logging path is not known in advance, including:

    /FCDATA01/DATALOG/Alarms/YYYYMMDD
    /FCDATA01/DATALOG/runlogs/YYYYMMDD
    /FCDATA01/DATALOG/1-secLog/YYYYMMDD

Date filters no longer require YYYYMMDD folders to be directly below the entered
remote path. OpenDFM explores intermediate non-date folders, discovers date folders
at any depth, and downloads only files below dates in the selected range.

When a date filter is selected but no YYYYMMDD folder exists anywhere below a valid
path, the scan still succeeds. The directory tree and loose files are displayed;
those loose files start unchecked because the date filter could not be applied.

PLC ACK/NG code 22 during a directory-open request is reported as:

    Remote SD path does not exist or is not a directory

Multiple PLCs
-------------
Click "Add a PLC" to open another independent PLC tab. Different PLCs can scan or
download concurrently. Files within one PLC tab still download one at a time.

OpenDFM prevents two active tabs from connecting to the same IP address and port.
New PLC tabs intentionally start with a blank IP address and a separate output
folder.

Workflow
--------
1. Enter the PLC IP address and any valid SD-card directory.
2. Choose all dates, last N calendar days, or an inclusive date range.
3. Click Scan PLC.
4. Expand folders, or double-click a folder to use it as the new browse root.
5. Check the files to retrieve and select an output folder.
6. Click Download selected.

Partial files
-------------
STOP closes only that tab's active connection and retains the current .part file.
The protocol does not currently resume at a byte offset, so retrying restarts that
individual file.

Transport compatibility
-----------------------
MiSmSDCard remains compatible with MiSmTCP and MiSmSerial-style objects. The GUI
uses MiSmTCP because each tab represents an Ethernet PLC endpoint.

Files
-----
OpenDFM.py             Main window, PLC tabs, browsing tree, worker threads
OpenDFM.ui             Editable Qt Designer main-window layout
OpenDFMTab.ui          Editable Qt Designer layout used by every PLC tab
open_dfm_backend.py    Transport-neutral discovery, date filtering, downloads
MiSmSDCard.py          SD-card Maintenance Protocol library
MiSmTCP.py             TCP Maintenance Protocol transport
pull_sd_logs_native.py Command-line downloader using the same browse logic

Immediate STOP behavior
-----------------------
STOP aborts the active TCP socket and suppresses automatic reconnect and
directory-list retries. A blocked scan or download should stop immediately,
and interrupted downloads retain their .part file.
