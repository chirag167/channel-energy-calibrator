"""
main_window.py -- the application window that ties everything together.

It owns:
  * one CalibrationSession (the data),
  * the header row (bins, energy levels, mode, trial m and b, file name),
  * the three plot panels,
  * the File menu (Upload / Export / Download) and the Help menu.

Whenever anything changes, ``refresh_all`` redraws every panel and updates the
header, so all views stay in step.
"""

import csv
from pathlib import Path

from PySide6 import QtCore
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from .calibration import CalibrationSession
from .panels import FitPanel, ResidualPanel, SpectrumPanel
from .spectrum import Spectrum, SpectrumLoadError

HELP_TEXT = """\
GETTING STARTED
 1. File > Upload a CSV spectrum (1 column of ADC channels, or 2 columns: channel, counts).
 2. Type the energy levels (MeV, comma-separated) and press Enter / Apply.
    The FIRST level is the anchor.
 3. Click the peak that belongs to the first level. The levels appear as lines.
 4. Press Enter to record the anchor as the first calibration point.

SPECTRUM PANEL (top left) - click it first so it has the keyboard
 b            mode b: Left/Right shift ALL unrecorded lines together (b +/- 0.01 MeV)
              dragging any line also shifts them all
 m            mode m: click a line to select it; Left/Right move only that line (0.25 ch)
              dragging a line moves only that line
              Up/Down change the slope m (Up spreads lines apart, Down squeezes)
 Shift+arrow  10x bigger step
 Enter        record the selected line as a (channel, E) point
 n / p        select next / previous level
 c            snap the selected line to the centre of the nearest peak
 Delete/Backspace  remove the selected level from the calibration
 a            re-anchor: next click places the first level (clears recorded points)
 Esc          deselect          r   reset the view (zoom out)

After 2 recorded points the line is fitted, and the lines you have not recorded yet
move to where the fit predicts - so the next levels are usually close already.

FIT PANEL (top right)
 Click a point to select it; drag it, or use the arrows:
 Left/Right   move its channel by 0.25 (Shift: 2.5)
 Up/Down      change its energy by 0.01 MeV (Shift: 0.1); a grey x marks the tabulated value
 Delete/Backspace  delete the point (the level stays in the list)

Every panel has its own zoom / pan toolbar. While zoom or pan is switched on,
clicks go to zooming; switch it off to select lines and points again.

FILE MENU
 Download  - saves all three plots (PNG) and a CSV of the points, m and b to a folder
 Export    - saves one plot as PNG or PDF
"""


class ExportDialog(QDialog):
    """Small dialog: which plot, which format."""

    def __init__(self, parent, fit_available):
        super().__init__(parent)
        self.setWindowTitle("Export a plot")
        self.plot_box = QComboBox()
        self.plot_box.addItems(["Spectrum", "Calibration fit"]
                               + (["Residuals"] if fit_available else []))
        self.format_box = QComboBox()
        self.format_box.addItems(["png", "pdf"])
        form = QFormLayout(self)
        form.addRow("Plot:", self.plot_box)
        form.addRow("Format:", self.format_box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Channel-to-Energy Calibrator")
        self.resize(1400, 900)

        self.session = CalibrationSession()
        self.spectrum = None

        self._build_panels()
        self._build_header()
        self._build_layout()
        self._build_menus()
        self.statusBar().showMessage("File > Upload a CSV spectrum to begin.  (Help > Controls lists all keys.)")
        self.refresh_all()

    # ------------------------------------------------------------------
    # Building the window
    # ------------------------------------------------------------------
    def _build_panels(self):
        args = (self.session, self.refresh_all, self.show_status)
        self.spectrum_panel = SpectrumPanel(*args)
        self.fit_panel = FitPanel(*args)
        self.residual_panel = ResidualPanel(*args)

    def _build_header(self):
        self.bins_box = QSpinBox()
        self.bins_box.setRange(1, 4096)
        self.bins_box.setValue(1)
        self.bins_box.setSuffix(" ch/bin")
        self.bins_box.setToolTip("Channels summed into each histogram bin")
        self.bins_box.valueChanged.connect(self.on_bins_changed)

        self.levels_edit = QLineEdit()
        self.levels_edit.setPlaceholderText("e.g. 9.656, 6.557, 5.958, 5.261  (first = anchor)")
        self.levels_edit.returnPressed.connect(self.on_levels_entered)
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.on_levels_entered)

        self.m_edit = QLineEdit()
        self.b_edit = QLineEdit()
        for box, tip in ((self.m_edit, "Trial slope m (MeV/channel). Type a value and press Enter."),
                         (self.b_edit, "Trial intercept b (MeV). Type a value and press Enter.")):
            box.setFixedWidth(110)
            box.setToolTip(tip)
            box.returnPressed.connect(self.on_trial_typed)

        self.mode_label = QLabel()
        self.log_box = QCheckBox("log y")
        self.log_box.setChecked(True)
        self.log_box.toggled.connect(self.on_bins_changed)

        self.file_label = QLabel("No file loaded")
        self.file_label.setStyleSheet("font-weight: bold;")
        self.file_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight
                                     | QtCore.Qt.AlignmentFlag.AlignVCenter)

        row = QHBoxLayout()
        row.addWidget(QLabel("Binning:"))
        row.addWidget(self.bins_box)
        row.addWidget(self.log_box)
        row.addSpacing(12)
        row.addWidget(QLabel("Energy levels (MeV):"))
        row.addWidget(self.levels_edit, stretch=3)
        row.addWidget(apply_btn)
        row.addSpacing(12)
        row.addWidget(self.mode_label)
        row.addSpacing(12)
        row.addWidget(QLabel("m:"))
        row.addWidget(self.m_edit)
        row.addWidget(QLabel("b:"))
        row.addWidget(self.b_edit)
        row.addSpacing(12)
        row.addWidget(self.file_label, stretch=1)
        self.header = QWidget()
        self.header.setLayout(row)

    def _build_layout(self):
        top = QSplitter(QtCore.Qt.Orientation.Horizontal)
        top.addWidget(self.spectrum_panel)
        top.addWidget(self.fit_panel)
        top.setSizes([900, 500])

        self.vertical = QSplitter(QtCore.Qt.Orientation.Vertical)
        self.vertical.addWidget(top)
        self.vertical.addWidget(self.residual_panel)
        self.vertical.setSizes([620, 260])
        self.residual_panel.setVisible(False)  # appears once there is a fit

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.header)
        layout.addWidget(self.vertical, stretch=1)
        self.setCentralWidget(central)

    def _build_menus(self):
        file_menu = self.menuBar().addMenu("&File")
        for text, shortcut, slot in (
            ("&Upload…", QKeySequence.StandardKey.Open, self.on_upload),
            ("&Export…", "Ctrl+E", self.on_export),
            ("&Download…", QKeySequence.StandardKey.Save, self.on_download),
        ):
            action = QAction(text, self)
            action.setShortcut(shortcut)
            action.triggered.connect(slot)
            file_menu.addAction(action)
        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = self.menuBar().addMenu("&Help")
        controls = QAction("&Controls", self)
        controls.triggered.connect(self.on_help)
        help_menu.addAction(controls)

    # ------------------------------------------------------------------
    # Keeping everything in step
    # ------------------------------------------------------------------
    def refresh_all(self):
        """Redraw all panels and update the header from the session."""
        s = self.session
        self.spectrum_panel.refresh()
        self.fit_panel.refresh()
        self.residual_panel.setVisible(s.fit is not None)
        self.residual_panel.refresh()

        mode = self.spectrum_panel.mode
        self.mode_label.setText("Mode: <b>b</b> (shift all)" if mode == "b"
                                else "Mode: <b>m</b> (move one)")
        if not self.levels_edit.hasFocus():
            self.levels_edit.setText(s.levels_text())
        self.m_edit.setText("" if s.trial_m is None else f"{s.trial_m:.7g}")
        self.b_edit.setText("" if s.trial_b is None else f"{s.trial_b:.4f}")

    def show_status(self, message):
        self.statusBar().showMessage(message)

    # ------------------------------------------------------------------
    # Header actions
    # ------------------------------------------------------------------
    def on_levels_entered(self):
        try:
            energies = CalibrationSession.parse_levels(self.levels_edit.text())
        except ValueError as err:
            QMessageBox.warning(self, "Energy levels", str(err))
            return
        self.session.set_levels(energies)
        self.levels_edit.clearFocus()
        if self.session.is_anchored:
            self.show_status(f"{len(energies)} levels applied.")
        else:
            self.show_status(f"{len(energies)} levels set. Now click the peak for "
                             f"{energies[0]:g} MeV (the anchor) in the spectrum.")
        self.refresh_all()
        self.spectrum_panel.canvas.setFocus()

    def on_trial_typed(self):
        if not self.session.is_anchored:
            self.show_status("Anchor the calibration first (click the first peak).")
            return
        try:
            self.session.set_trial(m=float(self.m_edit.text()), b=float(self.b_edit.text()))
        except ValueError as err:
            QMessageBox.warning(self, "Trial calibration", f"Could not use that value: {err}")
        self.refresh_all()

    def on_bins_changed(self, *_):
        if self.spectrum is None:
            return
        self.spectrum_panel.set_spectrum(self.spectrum, self.bins_box.value(),
                                         self.log_box.isChecked(), keep_view=True)

    # ------------------------------------------------------------------
    # File menu
    # ------------------------------------------------------------------
    def on_upload(self):
        path, _ = QFileDialog.getOpenFileName(self, "Upload spectrum", "",
                                              "CSV files (*.csv);;All files (*)")
        if path:
            self.load_file(path)

    def load_file(self, path):
        """Load a spectrum (also used by the command line and the tests)."""
        try:
            spectrum = Spectrum.from_csv(path)
        except SpectrumLoadError as err:
            QMessageBox.critical(self, "Cannot use this file", str(err))
            return False
        self.spectrum = spectrum
        self.session.max_channel = spectrum.max_channel
        # a new file starts a new calibration, but keeps the typed levels
        self.session.set_levels([l.energy_tab for l in self.session.levels])
        self.session.trial_m = self.session.trial_b = None
        self.session.fit = None
        for lvl in self.session.levels:
            lvl.recorded_channel, lvl.offset, lvl.energy = None, 0.0, lvl.energy_tab
        self.spectrum_panel.awaiting_anchor = True
        self.spectrum_panel.set_spectrum(spectrum, self.bins_box.value(), self.log_box.isChecked())
        self.file_label.setText(Path(path).name)
        self.setWindowTitle(f"Channel-to-Energy Calibrator — {Path(path).name}")
        self.show_status(f"Loaded {Path(path).name}: {spectrum.input_kind}, "
                         f"{spectrum.total_counts:.0f} counts. Type the energy levels, "
                         "then click the peak of the first level.")
        self.refresh_all()
        return True

    def _figures(self):
        figs = {"Spectrum": self.spectrum_panel.figure,
                "Calibration fit": self.fit_panel.figure}
        if self.session.fit is not None:
            figs["Residuals"] = self.residual_panel.figure
        return figs

    def on_export(self):
        dialog = ExportDialog(self, self.session.fit is not None)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, fmt = dialog.plot_box.currentText(), dialog.format_box.currentText()
        stem = self.spectrum.path.stem if self.spectrum else "calibration"
        suggested = f"{stem}_{name.lower().replace(' ', '_')}.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "Export plot", suggested, f"{fmt.upper()} (*.{fmt})")
        if path:
            if not path.lower().endswith("." + fmt):
                path += "." + fmt
            self._figures()[name].savefig(path, dpi=300, bbox_inches="tight")
            self.show_status(f"Saved {path}")

    def on_download(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the plots")
        if folder:
            saved = self.download_to(folder)
            self.show_status("Saved: " + ", ".join(saved))

    def download_to(self, folder):
        """Save all plots as PNG plus a CSV of the points. Returns the file names."""
        folder = Path(folder)
        stem = self.spectrum.path.stem if self.spectrum else "calibration"
        saved = []
        for name, fig in self._figures().items():
            out = folder / f"{stem}_{name.lower().replace(' ', '_')}.png"
            fig.savefig(out, dpi=300, bbox_inches="tight")
            saved.append(out.name)

        out = folder / f"{stem}_calibration_points.csv"
        with open(out, "w", newline="") as fh:
            w = csv.writer(fh)
            f = self.session.fit
            w.writerow(["# E = m*channel + b"])
            if f is not None:
                w.writerow(["# m (MeV/ch)", f.m, "m_err", "" if f.m_err is None else f.m_err])
                w.writerow(["# b (MeV)", f.b, "b_err", "" if f.b_err is None else f.b_err])
            w.writerow(["channel", "E_tabulated_MeV", "E_used_MeV", "E_fit_MeV", "residual_MeV"])
            w.writerows(self.session.points_table())
        saved.append(out.name)
        return saved

    def on_help(self):
        box = QMessageBox(self)
        box.setWindowTitle("Controls")
        box.setText("<pre>" + HELP_TEXT + "</pre>")
        box.exec()
