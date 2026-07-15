#!/usr/bin/env python3
"""Qt GUI for downloading IDEC FC6A SD-card logs."""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import Event
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt5 import QtCore, QtWidgets, uic
except ImportError as exc:
    raise SystemExit(
        "PyQt5 is required. On Linux Mint/Ubuntu run:\n"
        "  sudo apt install python3-pyqt5"
    ) from exc

from MiSmSDCard import MiSmSDCard
from MiSmTCP import MiSmTCP
from open_dfm_backend import (
    TransferCancelled, download_file, human_size, relative_path, scan_tree,
)

VERSION = "2026.07.14.1"
DEFAULT_REMOTE = "/FCDATA01/DATALOG/1-secLog"


@dataclass(frozen=True)
class ConnectionConfig:
    host: str
    port: int
    timeout: float
    retries: int
    remote: str


@dataclass(frozen=True)
class DateFilter:
    days: Optional[int] = None
    start: Optional[date] = None
    end: Optional[date] = None


class ScanWorker(QtCore.QObject):
    status = QtCore.pyqtSignal(str)
    result = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)
    cancelled = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()

    def __init__(self, config: ConnectionConfig, date_filter: DateFilter):
        super().__init__()
        self.config = config
        self.date_filter = date_filter
        self.stop_event = Event()
        self.plc: Optional[MiSmTCP] = None

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            self.plc = MiSmTCP(
                self.config.host, port=self.config.port,
                timeout=self.config.timeout,
            )
            sd = MiSmSDCard(
                self.plc, timeout=self.config.timeout,
                retries=self.config.retries,
            )
            dirs, files, start, end = scan_tree(
                sd, self.config.remote, days=self.date_filter.days,
                start=self.date_filter.start, end=self.date_filter.end,
                status=self.status.emit, cancel=self.stop_event,
            )
            self.result.emit({
                "dirs": dirs, "files": files, "start": start, "end": end,
            })
        except TransferCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if self.plc is not None:
                self.plc.close()
            self.finished.emit()

    def request_stop(self) -> None:
        self.stop_event.set()
        if self.plc is not None:
            self.plc.close()


class DownloadWorker(QtCore.QObject):
    status = QtCore.pyqtSignal(str)
    file_started = QtCore.pyqtSignal(str, int, int)
    file_progress = QtCore.pyqtSignal(str, int, int, float, float)
    file_finished = QtCore.pyqtSignal(str, str)
    overall_progress = QtCore.pyqtSignal(int, int)
    result = QtCore.pyqtSignal(int, int, int)
    failed = QtCore.pyqtSignal(str)
    cancelled = QtCore.pyqtSignal()
    finished = QtCore.pyqtSignal()

    def __init__(
        self, config: ConnectionConfig, files: List[Dict[str, Any]],
        output: Path, overwrite: bool, block_size: int = 0x5C0,
    ):
        super().__init__()
        self.config = config
        self.files = files
        self.output = output
        self.overwrite = overwrite
        self.block_size = block_size
        self.stop_event = Event()
        self.plc: Optional[MiSmTCP] = None

    @QtCore.pyqtSlot()
    def run(self) -> None:
        downloaded = skipped = failed = 0
        total_files = len(self.files)
        try:
            self.plc = MiSmTCP(
                self.config.host, port=self.config.port,
                timeout=self.config.timeout,
            )
            sd = MiSmSDCard(
                self.plc, timeout=self.config.timeout,
                retries=self.config.retries,
            )
            self.output.mkdir(parents=True, exist_ok=True)

            for index, item in enumerate(self.files, 1):
                if self.stop_event.is_set():
                    raise TransferCancelled

                remote = str(item["full_path"])
                expected = int(item["size"])
                local = self.output / relative_path(self.config.remote, remote)
                self.file_started.emit(remote, index, total_files)

                def progress(
                    done: int, total: int, current: float, average: float,
                ) -> None:
                    self.file_progress.emit(
                        remote, done, total, current, average,
                    )

                try:
                    state = download_file(
                        self.plc, sd, remote, local, expected,
                        retries=self.config.retries,
                        block_size=self.block_size,
                        overwrite=self.overwrite,
                        progress=progress,
                        status=self.status.emit,
                        cancel=self.stop_event,
                    )
                    if state == "downloaded":
                        downloaded += 1
                    else:
                        skipped += 1
                    self.file_finished.emit(remote, state)
                except TransferCancelled:
                    raise
                except Exception as exc:
                    failed += 1
                    self.file_finished.emit(remote, "failed")
                    self.status.emit(f"FAILED {remote}: {exc}")
                    reconnect = getattr(self.plc, "reconnect", None)
                    if callable(reconnect):
                        try:
                            reconnect()
                        except Exception:
                            pass

                self.overall_progress.emit(index, total_files)

            self.result.emit(downloaded, skipped, failed)
        except TransferCancelled:
            self.cancelled.emit()
        except Exception:
            self.failed.emit(traceback.format_exc())
        finally:
            if self.plc is not None:
                self.plc.close()
            self.finished.emit()

    def request_stop(self) -> None:
        self.stop_event.set()
        if self.plc is not None:
            self.plc.close()


class OpenDFMDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        ui_path = Path(__file__).with_name("OpenDFM.ui")
        uic.loadUi(os.fspath(ui_path), self)

        self.settings = QtCore.QSettings("OpenDFM", "OpenDFM")
        self.thread: Optional[QtCore.QThread] = None
        self.worker: Optional[QtCore.QObject] = None
        self.operation = ""
        self.scan_signature: Optional[Tuple[Any, ...]] = None
        self.files: List[Dict[str, Any]] = []
        self.file_items: Dict[str, QtWidgets.QTreeWidgetItem] = {}

        self.setWindowTitle(f"OpenDFM {VERSION} - PLC SD Log Downloader")
        self.startDateEdit.setDate(QtCore.QDate.currentDate().addDays(-10))
        self.endDateEdit.setDate(QtCore.QDate.currentDate())
        self.outputEdit.setText(os.fspath(Path.cwd() / "1-secLog"))
        self.mainSplitter.setSizes([610, 490])
        self._configure_tree()
        self._connect_signals()
        self._restore_settings()
        self._update_date_controls()
        self._update_selection_summary()

    def _configure_tree(self) -> None:
        header = self.fileTree.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

    def _connect_signals(self) -> None:
        self.scanButton.clicked.connect(self.start_scan)
        self.downloadButton.clicked.connect(self.start_download)
        self.stopButton.clicked.connect(self.stop_operation)
        self.browseButton.clicked.connect(self.browse_output)
        self.selectAllButton.clicked.connect(lambda: self.set_all_checked(True))
        self.clearAllButton.clicked.connect(lambda: self.set_all_checked(False))
        self.helpButton.clicked.connect(self.show_help)
        self.closeButton.clicked.connect(self.close)
        self.fileTree.itemChanged.connect(self._update_selection_summary)

        for radio in (
            self.allDatesRadio, self.lastDaysRadio, self.dateRangeRadio,
        ):
            radio.toggled.connect(self._update_date_controls)

    def _connection_config(self) -> ConnectionConfig:
        host = self.hostEdit.text().strip()
        remote = self.remoteEdit.text().strip()
        if not host:
            raise ValueError("IP address is required")
        if not remote:
            raise ValueError("Remote path is required")
        if not remote.startswith("/"):
            remote = "/" + remote
            self.remoteEdit.setText(remote)
        return ConnectionConfig(
            host=host, port=self.portSpin.value(),
            timeout=self.timeoutSpin.value(),
            retries=self.retriesSpin.value(), remote=remote,
        )

    def _date_filter(self) -> DateFilter:
        if self.lastDaysRadio.isChecked():
            return DateFilter(days=self.daysSpin.value())
        if self.dateRangeRadio.isChecked():
            return DateFilter(
                start=self.startDateEdit.date().toPyDate(),
                end=self.endDateEdit.date().toPyDate(),
            )
        return DateFilter()

    def _current_signature(self) -> Tuple[Any, ...]:
        config = self._connection_config()
        date_filter = self._date_filter()
        return (
            config.host, config.port, config.timeout, config.retries,
            config.remote, date_filter.days, date_filter.start,
            date_filter.end,
        )

    def _update_date_controls(self) -> None:
        self.daysSpin.setEnabled(self.lastDaysRadio.isChecked())
        enabled = self.dateRangeRadio.isChecked()
        self.startDateEdit.setEnabled(enabled)
        self.endDateEdit.setEnabled(enabled)

    def browse_output(self) -> None:
        start = self.outputEdit.text().strip() or os.fspath(Path.cwd())
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output folder", start,
        )
        if chosen:
            self.outputEdit.setText(chosen)

    def start_scan(self) -> None:
        if self.thread is not None:
            return
        try:
            config = self._connection_config()
            date_filter = self._date_filter()
            signature = self._current_signature()
        except Exception as exc:
            self._show_error(str(exc))
            return

        self.fileTree.clear()
        self.files = []
        self.file_items = {}
        self.scan_signature = None
        self.logEdit.clear()
        self._append_log(f"Connecting to {config.host}:{config.port}")
        self.statusLabel.setText("Scanning PLC...")

        worker = ScanWorker(config, date_filter)
        worker.status.connect(self._append_log)
        worker.result.connect(lambda result: self._scan_complete(result, signature))
        worker.failed.connect(self._worker_error)
        worker.cancelled.connect(self._worker_cancelled)
        self._start_worker(worker, "scan")

    def _scan_complete(
        self, result: Dict[str, Any], signature: Tuple[Any, ...],
    ) -> None:
        self.files = list(result["files"])
        self.scan_signature = signature
        self.fileTree.blockSignals(True)
        try:
            for entry in self.files:
                remote = str(entry["full_path"])
                item = QtWidgets.QTreeWidgetItem([
                    remote, human_size(int(entry["size"])), "Ready",
                ])
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(0, QtCore.Qt.Checked)
                item.setData(0, QtCore.Qt.UserRole, entry)
                self.fileTree.addTopLevelItem(item)
                self.file_items[remote] = item
        finally:
            self.fileTree.blockSignals(False)

        start = result.get("start")
        end = result.get("end")
        if start is not None:
            self._append_log(
                f"Date range: {start:%Y%m%d} through {end:%Y%m%d}, inclusive"
            )
        total = sum(int(item["size"]) for item in self.files)
        folders = max(len(result["dirs"]) - 1, 0)
        self._append_log(
            f"Found {folders} folders and {len(self.files)} files, "
            f"{human_size(total)} total."
        )
        self.statusLabel.setText("Scan complete.")
        self._update_selection_summary()

    def selected_files(self) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        for index in range(self.fileTree.topLevelItemCount()):
            item = self.fileTree.topLevelItem(index)
            if item.checkState(0) == QtCore.Qt.Checked:
                selected.append(item.data(0, QtCore.Qt.UserRole))
        selected.sort(key=lambda entry: str(entry["full_path"]))
        return selected

    def set_all_checked(self, checked: bool) -> None:
        state = QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked
        self.fileTree.blockSignals(True)
        try:
            for index in range(self.fileTree.topLevelItemCount()):
                self.fileTree.topLevelItem(index).setCheckState(0, state)
        finally:
            self.fileTree.blockSignals(False)
        self._update_selection_summary()

    def _update_selection_summary(self, *_args: Any) -> None:
        selected = self.selected_files()
        total = sum(int(item["size"]) for item in selected)
        count = self.fileTree.topLevelItemCount()
        self.fileSummaryLabel.setText(
            f"{len(selected)} / {count} selected, {human_size(total)}"
        )
        self.downloadButton.setEnabled(
            bool(selected) and self.thread is None and self.scan_signature is not None
        )

    def start_download(self) -> None:
        if self.thread is not None:
            return
        try:
            config = self._connection_config()
            signature = self._current_signature()
            output_text = self.outputEdit.text().strip()
            if not output_text:
                raise ValueError("Output folder is required")
            output = Path(output_text).expanduser()
        except Exception as exc:
            self._show_error(str(exc))
            return

        if signature != self.scan_signature:
            self._show_error("PLC or date settings changed. Scan the PLC again.")
            return

        files = self.selected_files()
        if not files:
            self._show_error("Select at least one file")
            return

        self.currentProgressBar.setValue(0)
        self.overallProgressBar.setMaximum(len(files))
        self.overallProgressBar.setValue(0)
        self._append_log(f"Downloading {len(files)} selected files to {output}")
        self.statusLabel.setText("Downloading...")

        worker = DownloadWorker(
            config, files, output, self.overwriteCheck.isChecked(),
        )
        worker.status.connect(self._append_log)
        worker.file_started.connect(self._file_started)
        worker.file_progress.connect(self._file_progress)
        worker.file_finished.connect(self._file_finished)
        worker.overall_progress.connect(self._overall_progress)
        worker.result.connect(self._download_complete)
        worker.failed.connect(self._worker_error)
        worker.cancelled.connect(self._worker_cancelled)
        self._start_worker(worker, "download")

    def _file_started(self, remote: str, index: int, total: int) -> None:
        self.currentFileLabel.setText(f"{index}/{total}: {remote}")
        self.currentProgressBar.setValue(0)
        self.speedLabel.setText("Current: 0 B/s    Average: 0 B/s")
        item = self.file_items.get(remote)
        if item is not None:
            item.setText(2, "Downloading")
            self.fileTree.scrollToItem(item)

    def _file_progress(
        self, _remote: str, done: int, total: int,
        current: float, average: float,
    ) -> None:
        value = int(done * 1000 / total) if total else 1000
        self.currentProgressBar.setValue(min(value, 1000))
        self.currentProgressBar.setFormat(
            f"{done * 100.0 / total if total else 100.0:.1f}% - "
            f"{human_size(done)} / {human_size(total)}"
        )
        self.speedLabel.setText(
            f"Current: {human_size(current)}/s    "
            f"Average: {human_size(average)}/s"
        )

    def _file_finished(self, remote: str, state: str) -> None:
        labels = {
            "downloaded": "Downloaded", "skipped": "Already present",
            "failed": "Failed",
        }
        item = self.file_items.get(remote)
        if item is not None:
            item.setText(2, labels.get(state, state))

    def _overall_progress(self, done: int, total: int) -> None:
        self.overallProgressBar.setMaximum(max(total, 1))
        self.overallProgressBar.setValue(done)

    def _download_complete(self, downloaded: int, skipped: int, failed: int) -> None:
        self.currentFileLabel.setText("No active transfer")
        self.statusLabel.setText("Download complete.")
        self._append_log(
            f"Done. Downloaded {downloaded}; skipped {skipped}; failed {failed}."
        )

    def _start_worker(self, worker: QtCore.QObject, operation: str) -> None:
        thread = QtCore.QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._thread_finished)

        self.thread = thread
        self.worker = worker
        self.operation = operation
        self._set_busy(True)
        thread.start()

    def _thread_finished(self) -> None:
        self.thread = None
        self.worker = None
        self.operation = ""
        self._set_busy(False)
        self._update_selection_summary()

    def _set_busy(self, busy: bool) -> None:
        self.scanButton.setEnabled(not busy)
        self.stopButton.setEnabled(busy)
        self.closeButton.setEnabled(not busy)
        self.downloadButton.setEnabled(
            not busy and bool(self.selected_files())
            and self.scan_signature is not None
        )

    def stop_operation(self) -> None:
        worker = self.worker
        if worker is None:
            return
        self.statusLabel.setText("Stopping...")
        self._append_log("Stop requested. The current .part file will be retained.")
        request_stop = getattr(worker, "request_stop", None)
        if callable(request_stop):
            request_stop()
        self.stopButton.setEnabled(False)

    def _worker_cancelled(self) -> None:
        self.statusLabel.setText("Stopped.")
        self._append_log("Operation stopped. Any current .part file was retained.")
        self.currentFileLabel.setText("No active transfer")

    def _worker_error(self, details: str) -> None:
        self.statusLabel.setText("Operation failed.")
        self._append_log(details.rstrip())
        last_line = details.strip().splitlines()[-1] if details.strip() else details
        self._show_error(last_line)

    def _append_log(self, text: str) -> None:
        self.logEdit.appendPlainText(text)
        bar = self.logEdit.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _show_error(self, text: str) -> None:
        QtWidgets.QMessageBox.critical(self, "OpenDFM", text)

    def show_help(self) -> None:
        text = (
            "1. Enter the PLC IP address and SD log path.\n"
            "2. Choose all dates, the last N calendar days, or an inclusive range.\n"
            "3. Click List Files, then select the files to download.\n"
            "4. Choose an output folder and click Download selected.\n\n"
            "Files download one at a time. STOP closes the active connection and "
            "retains the current filename.part file. A later download currently "
            "restarts that file; byte-offset resume is not yet implemented.\n\n"
            "The last-N-days filter is anchored to the newest YYYYMMDD folder on "
            "the PLC, not the computer's current date."
        )
        QtWidgets.QMessageBox.information(self, "OpenDFM Help", text)

    def _restore_settings(self) -> None:
        value = self.settings.value("geometry")
        if value is not None:
            self.restoreGeometry(value)

        self.hostEdit.setText(self.settings.value("host", "192.168.1.61"))
        self.portSpin.setValue(int(self.settings.value("port", 2101)))
        self.remoteEdit.setText(self.settings.value("remote", DEFAULT_REMOTE))
        self.outputEdit.setText(
            self.settings.value("output", os.fspath(Path.cwd() / "1-secLog"))
        )
        self.timeoutSpin.setValue(float(self.settings.value("timeout", 5.0)))
        self.retriesSpin.setValue(int(self.settings.value("retries", 4)))
        self.daysSpin.setValue(int(self.settings.value("days", 4)))
        self.overwriteCheck.setChecked(
            self.settings.value("overwrite", False, type=bool)
        )

        mode = self.settings.value("date_mode", "all")
        self.allDatesRadio.setChecked(mode == "all")
        self.lastDaysRadio.setChecked(mode == "days")
        self.dateRangeRadio.setChecked(mode == "range")

        start = QtCore.QDate.fromString(
            self.settings.value("start_date", ""), QtCore.Qt.ISODate,
        )
        end = QtCore.QDate.fromString(
            self.settings.value("end_date", ""), QtCore.Qt.ISODate,
        )
        if start.isValid():
            self.startDateEdit.setDate(start)
        if end.isValid():
            self.endDateEdit.setDate(end)

    def _save_settings(self) -> None:
        mode = "all"
        if self.lastDaysRadio.isChecked():
            mode = "days"
        elif self.dateRangeRadio.isChecked():
            mode = "range"

        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("host", self.hostEdit.text().strip())
        self.settings.setValue("port", self.portSpin.value())
        self.settings.setValue("remote", self.remoteEdit.text().strip())
        self.settings.setValue("output", self.outputEdit.text().strip())
        self.settings.setValue("timeout", self.timeoutSpin.value())
        self.settings.setValue("retries", self.retriesSpin.value())
        self.settings.setValue("days", self.daysSpin.value())
        self.settings.setValue("overwrite", self.overwriteCheck.isChecked())
        self.settings.setValue("date_mode", mode)
        self.settings.setValue(
            "start_date", self.startDateEdit.date().toString(QtCore.Qt.ISODate),
        )
        self.settings.setValue(
            "end_date", self.endDateEdit.date().toString(QtCore.Qt.ISODate),
        )

    def closeEvent(self, event: Any) -> None:
        if self.thread is not None:
            answer = QtWidgets.QMessageBox.question(
                self, "OpenDFM", "Stop the active operation before closing?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )
            if answer == QtWidgets.QMessageBox.Yes:
                self.stop_operation()
            event.ignore()
            return
        self._save_settings()
        event.accept()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("OpenDFM")
    dialog = OpenDFMDialog()
    dialog.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
