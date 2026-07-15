OpenDFM - FC6A SD Log Downloader GUI
====================================

Requirements
------------
Python 3 and PyQt5. On Linux Mint/Ubuntu:

    sudo apt install python3-pyqt5

Run
---

    ./OpenDFM.py

or:

    python3 OpenDFM.py

Workflow
--------
1. Enter the PLC IP address and remote SD log path.
2. Choose all dates, last N calendar days, or an inclusive date range.
3. Click Scan PLC.
4. Check the files to retrieve and select the output folder.
5. Click Download selected.

Downloads are sequential. STOP interrupts the active connection and retains the
current .part file. The current protocol implementation does not resume at a byte
offset, so a later attempt restarts that file.

Files
-----
OpenDFM.py             GUI and worker threads
OpenDFM.ui             Editable Qt Designer layout
open_dfm_backend.py    Transport-neutral scan/download workflow
MiSmSDCard.py          SD-card Maintenance Protocol library
MiSmTCP.py             TCP Maintenance Protocol transport
pull_sd_logs_native.py Existing command-line downloader

MiSmSDCard remains compatible with MiSmTCP and MiSmSerial-style objects. The
initial GUI connection page uses MiSmTCP because the supplied draft was IP based.
