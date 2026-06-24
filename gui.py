"""Qt GUI for TPI-1005-A signal generator.

Runs standalone — connects directly to the device (no server needed).
Usage:  .venv/bin/python gui.py [/dev/ttyUSBx]
"""

import sys
import threading
import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QStatusBar, QVBoxLayout, QWidget,
)

from tpi import TPI1005A, TPIError, find_device


# ---------------------------------------------------------------------------
# Background poller — reads device state every 500 ms
# ---------------------------------------------------------------------------

class DevicePoller(QThread):
    state_updated = pyqtSignal(float, int, bool)   # freq_mhz, level_dbm, rf_on
    error_occurred = pyqtSignal(str)

    def __init__(self, device: TPI1005A, parent=None):
        super().__init__(parent)
        self._dev = device
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            try:
                freq = self._dev.get_freq()
                level = self._dev.get_level()
                rf = self._dev.get_rf()
                self.state_updated.emit(freq, level, rf)
            except TPIError as e:
                self.error_occurred.emit(str(e))
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, device: TPI1005A):
        super().__init__()
        self._dev = device
        self._rf_on = False
        self._setup_ui()
        self._start_polling()

    def _setup_ui(self):
        self.setWindowTitle("TPI-1005-A Signal Generator")
        self.setMinimumWidth(400)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        mono = QFont("Monospace", 14)

        # --- Device info ---
        self._info_label = QLabel("Connecting…")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._info_label)

        # --- Frequency ---
        freq_row = QHBoxLayout()
        freq_row.addWidget(QLabel("Frequency (MHz):"))
        self._freq_edit = QLineEdit()
        self._freq_edit.setValidator(QDoubleValidator(35.0, 4400.0, 3))
        self._freq_edit.setFont(mono)
        self._freq_edit.setPlaceholderText("e.g. 433.920")
        freq_row.addWidget(self._freq_edit)
        self._set_freq_btn = QPushButton("Set")
        self._set_freq_btn.clicked.connect(self._on_set_freq)
        freq_row.addWidget(self._set_freq_btn)
        layout.addLayout(freq_row)

        self._freq_display = QLabel("— MHz")
        self._freq_display.setFont(mono)
        self._freq_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._freq_display)

        # --- Level ---
        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("Output level (dBm):"))
        self._level_edit = QLineEdit()
        self._level_edit.setValidator(QIntValidator(-90, 10))
        self._level_edit.setFont(mono)
        self._level_edit.setPlaceholderText("e.g. -10")
        level_row.addWidget(self._level_edit)
        self._set_level_btn = QPushButton("Set")
        self._set_level_btn.clicked.connect(self._on_set_level)
        level_row.addWidget(self._set_level_btn)
        layout.addLayout(level_row)

        self._level_display = QLabel("— dBm")
        self._level_display.setFont(mono)
        self._level_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._level_display)

        # --- RF on/off ---
        self._rf_btn = QPushButton("RF ON")
        self._rf_btn.setCheckable(True)
        self._rf_btn.setFont(QFont("Monospace", 14, QFont.Weight.Bold))
        self._rf_btn.setMinimumHeight(56)
        self._rf_btn.clicked.connect(self._on_toggle_rf)
        layout.addWidget(self._rf_btn)

        self.statusBar().showMessage("Ready")

        # Show device info
        try:
            info = f"{self._dev.get_model()}  ·  S/N {self._dev.get_serial()}  ·  FW {self._dev.get_firmware()}"
            self._info_label.setText(info)
        except TPIError:
            pass

    def _start_polling(self):
        self._poller = DevicePoller(self._dev, self)
        self._poller.state_updated.connect(self._on_state_updated)
        self._poller.error_occurred.connect(self._on_error)
        self._poller.start()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_state_updated(self, freq_mhz: float, level_dbm: int, rf_on: bool):
        self._freq_display.setText(f"{freq_mhz:.3f} MHz")
        self._level_display.setText(f"{level_dbm:+d} dBm")
        self._rf_on = rf_on
        self._rf_btn.setChecked(rf_on)
        self._rf_btn.setText("RF ON  ●" if rf_on else "RF OFF  ○")
        color = "#cc2200" if rf_on else "#444444"
        self._rf_btn.setStyleSheet(f"background-color: {color}; color: white;")

    def _on_error(self, msg: str):
        self.statusBar().showMessage(f"Error: {msg}")

    def _on_set_freq(self):
        text = self._freq_edit.text().strip()
        if not text:
            return
        try:
            mhz = float(text)
            self._dev.set_freq(mhz)
            self.statusBar().showMessage(f"Frequency set to {mhz:.3f} MHz")
        except (ValueError, TPIError) as e:
            self.statusBar().showMessage(f"Error: {e}")

    def _on_set_level(self):
        text = self._level_edit.text().strip()
        if not text:
            return
        try:
            dbm = int(text)
            self._dev.set_level(dbm)
            self.statusBar().showMessage(f"Level set to {dbm:+d} dBm")
        except (ValueError, TPIError) as e:
            self.statusBar().showMessage(f"Error: {e}")

    def _on_toggle_rf(self, checked: bool):
        try:
            self._dev.set_rf(checked)
            self.statusBar().showMessage("RF ON" if checked else "RF OFF")
        except TPIError as e:
            self._rf_btn.setChecked(not checked)
            self.statusBar().showMessage(f"Error: {e}")

    def closeEvent(self, event):
        self._poller.stop()
        self._poller.wait(1000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_device()
    if not port:
        print("ERROR: TPI-1005-A not found. Connect the device or pass port as argument.",
              file=sys.stderr)
        sys.exit(1)

    print(f"Using device: {port}")
    app = QApplication(sys.argv)
    app.setApplicationName("TPI-1005-A")

    try:
        device = TPI1005A(port).open()
    except Exception as e:
        print(f"ERROR: Failed to open device: {e}", file=sys.stderr)
        sys.exit(1)

    win = MainWindow(device)
    win.show()
    ret = app.exec()
    device.close()
    sys.exit(ret)


if __name__ == "__main__":
    main()
