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
