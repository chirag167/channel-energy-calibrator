"""
Start the Channel-to-Energy Calibrator.

    python run_gui.py                 # empty window, use File > Upload
    python run_gui.py my_spectrum.csv # open a file straight away
"""
import sys

import matplotlib

# The GUI uses its own keys (arrows, m, b, Enter, Backspace, ...). Switch off
# matplotlib's built-in keyboard shortcuts so they do not interfere.
for name in list(matplotlib.rcParams):
    if name.startswith("keymap."):
        matplotlib.rcParams[name] = []

from PySide6.QtWidgets import QApplication  # noqa: E402

from calibrator.main_window import MainWindow  # noqa: E402


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.load_file(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
