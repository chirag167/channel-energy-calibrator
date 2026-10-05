"""
panels.py -- the three plot panels.

Each panel is a Qt widget holding one matplotlib figure plus its own zoom/pan
toolbar, so every plot can be zoomed on its own.

Class structure (inheritance):

    PlotPanel             shared set-up: figure, canvas, toolbar, helpers
      |-- SpectrumPanel   1D histogram + energy-level lines   (top left)
      |-- FitPanel        E vs channel points + straight-line fit (top right)
      |-- ResidualPanel   E_level - fit vs E_level          (bottom)

A subclass gets everything its parent defines and adds or overrides what it
needs. For example every panel inherits ``_keep_or_autoscale`` from PlotPanel.

How panels talk to the rest of the program
------------------------------------------
Each panel receives:
  * ``session``   -- the shared CalibrationSession (the data), and
  * ``on_change`` -- a function to call after it changes the session.
The main window passes a function that redraws *all* panels, so a change made
in one panel immediately shows up in the other two.
"""

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from matplotlib.transforms import blended_transform_factory
from PySide6 import QtCore
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .peaks import CHANNEL_RESOLUTION, peak_centroid

# ----------------------------------------------------------------------
# Colours (one place to change them)
# ----------------------------------------------------------------------
INK = "#0b0b0b"          # text
INK_2 = "#52514e"        # secondary text, axes
GRID = "#e4e3df"
HIST = "#2a78d6"         # histogram (blue)
LEVEL = "#eb6834"        # energy level, not yet recorded (orange)
RECORDED = "#008300"     # energy level recorded as a point (green)
SELECTED = "#4a3aa7"     # the selected level / point (violet)
FIT = "#2a78d6"          # fit line (blue)

PICK_PIXELS = 7          # how close (in screen pixels) a click must be to grab a line/point


def _shift_multiplier(key):
    """'shift+left' -> ('left', 10); 'left' -> ('left', 1)."""
    parts = key.split("+")
    return parts[-1], (10 if "shift" in parts[:-1] else 1)


class PlotPanel(QWidget):
    """Base class: a matplotlib figure, its canvas and a zoom/pan toolbar."""

    def __init__(self, session, on_change, status, parent=None):
        super().__init__(parent)
        self.session = session
        self.on_change = on_change   # call after changing the session
        self.status = status         # call with a message for the status bar

        self.figure = Figure(figsize=(6, 4), layout="constrained")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.ax = self.figure.add_subplot()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        self._auto_limits = None  # limits we set automatically last time

        self.canvas.mpl_connect("button_press_event", self._focus_on_click)
        self.canvas.mpl_connect("button_press_event", self.on_press)
        self.canvas.mpl_connect("motion_notify_event", self.on_motion)
        self.canvas.mpl_connect("button_release_event", self.on_release)
        self.canvas.mpl_connect("key_press_event", self._on_key_common)

    # ----- event hooks: subclasses override the ones they need -----
    def on_press(self, event): pass
    def on_motion(self, event): pass
    def on_release(self, event): pass
    def on_key(self, key, n): pass

    def refresh(self):
        """Redraw from the session. Subclasses implement this."""
        raise NotImplementedError

    # ----- shared helpers -----
    def _focus_on_click(self, event):
        self.canvas.setFocus()  # so the keyboard goes to the panel you clicked

    def toolbar_busy(self):
        """True while the zoom or pan tool is switched on (then clicks are for zooming)."""
        return bool(self.toolbar.mode)

    def _on_key_common(self, event):
        if event.key is None:
            return
        key, n = _shift_multiplier(event.key)
        if key == "r":
            self._auto_limits = None
            self.refresh()
            return
        self.on_key(key, n)

    def _keep_or_autoscale(self, previous_limits, force_keep=False):
        """Keep your zoom if you zoomed in; otherwise fit the view to the data.

        ``previous_limits`` are the limits just before redrawing. If they differ
        from the limits we chose automatically last time, you must have zoomed
        or panned, so we put them back.
        """
        if previous_limits is not None and (force_keep or (
                self._auto_limits is not None and previous_limits != self._auto_limits)):
            self.ax.set_xlim(previous_limits[0])
            self.ax.set_ylim(previous_limits[1])
        else:
            # (the axes were just cleared, so their data limits are fresh;
            #  relim() would skip scatter points, so we do not call it)
            self.ax.margins(0.08, 0.15)  # room so edge points are not cut in half
            self.ax.autoscale_view()
            self._auto_limits = (self.ax.get_xlim(), self.ax.get_ylim())
            self.toolbar.update()  # 'Home' button returns to this view

    def _limits(self):
        return (self.ax.get_xlim(), self.ax.get_ylim())

    def _nearest(self, event, xs, ys=None):
        """Index of the item closest to the mouse (within PICK_PIXELS), else None.

        With ys=None only horizontal distance counts (vertical lines).
        """
        if event.x is None or len(xs) == 0:
            return None
        if ys is None:
            px = self.ax.transData.transform(np.column_stack([xs, np.zeros(len(xs))]))[:, 0]
            dist = np.abs(px - event.x)
        else:
            pts = self.ax.transData.transform(np.column_stack([xs, ys]))
            dist = np.hypot(pts[:, 0] - event.x, pts[:, 1] - event.y)
        i = int(np.argmin(dist))
        return i if dist[i] <= PICK_PIXELS else None

    def _style_axes(self, ax):
        ax.grid(True, color=GRID, linewidth=0.8)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_color(INK_2)
        ax.tick_params(colors=INK_2)


# ======================================================================
class SpectrumPanel(PlotPanel):
    """Top-left panel: the histogram with the energy levels drawn on top.

    Modes (press the key while this panel has focus):
      'b'  -- shift ALL not-yet-recorded lines together (changes b)
      'm'  -- move ONE selected line at a time; up/down arrows change the slope m
    """

    def __init__(self, session, on_change, status, parent=None):
        super().__init__(session, on_change, status, parent)
        self.mode = "b"
        self.awaiting_anchor = True
        self.spectrum = None
        self.edges = self.counts = None
        self.log_y = True
        self._drag = None           # what is being dragged, if anything
        self._overlay_artists = []
        self._top_axis = None
        self._hist_artist = None
        self._style_axes(self.ax)
        self._draw_empty()

    # ----- data -----
    def set_spectrum(self, spectrum, channels_per_bin, log_y, keep_view=False):
        xlim = self.ax.get_xlim() if keep_view and self.spectrum is not None else None
        self.spectrum = spectrum
        self.log_y = log_y
        self.edges, self.counts = spectrum.binned(channels_per_bin)
        self.ax.cla()
        self._overlay_artists = []
        self._top_axis = None
        self._style_axes(self.ax)
        width = self.edges[1] - self.edges[0]
        label = "counts / channel" if width == 1 else f"counts / {width:g} channels"
        self._hist_artist = self.ax.stairs(self.counts, self.edges, color=HIST, linewidth=1.0)
        self.ax.set_xlabel("ADC channel", color=INK)
        self.ax.set_ylabel(label, color=INK)
        self.ax.set_yscale("log" if log_y else "linear")
        positive = self.counts[self.counts > 0]
        if log_y and len(positive):
            self.ax.set_ylim(0.5 * positive.min(), 2.0 * positive.max())
        if xlim is not None:
            self.ax.set_xlim(xlim)
        else:
            self.ax.set_xlim(self.edges[0], self.edges[-1])
        self.toolbar.update()
        self.refresh()

    def _draw_empty(self):
        self.ax.text(0.5, 0.5, "File > Upload a CSV spectrum to begin",
                     transform=self.ax.transAxes, ha="center", va="center", color=INK_2)
        self.ax.set_xlabel("ADC channel")
        self.canvas.draw_idle()

    # ----- drawing -----
    def refresh(self):
        if self.spectrum is None:
            return
        for artist in self._overlay_artists:
            artist.remove()
        self._overlay_artists = []
        if self._top_axis is not None:
            self._top_axis.remove()
            self._top_axis = None

        s = self.session
        if s.is_anchored and s.levels:
            text_tf = blended_transform_factory(self.ax.transData, self.ax.transAxes)
            for lvl in s.levels:
                x = s.position(lvl)
                is_sel = lvl is s.selected
                color = SELECTED if is_sel else (RECORDED if lvl.is_recorded else LEVEL)
                line = self.ax.axvline(x, color=color, linewidth=2.2 if is_sel else 1.4,
                                       linestyle="-" if lvl.is_recorded or is_sel else "--",
                                       zorder=3)
                label = f"{lvl.energy:g}"
                txt = self.ax.text(x, 0.985, " " + label, transform=text_tf, rotation=90,
                                   ha="right", va="top", fontsize=8, color=INK,
                                   fontweight="bold" if is_sel else "normal", zorder=4,
                                   clip_on=True)
                self._overlay_artists += [line, txt]

            # Top axis: energy from the current trial calibration E = m*ch + b.
            m, b = s.trial_m, s.trial_b
            self._top_axis = self.ax.secondary_xaxis(
                "top", functions=(lambda ch: m * ch + b, lambda e: (e - b) / m))
            self._top_axis.set_xlabel(f"E (MeV)   [trial: m = {m:.6g} MeV/ch, b = {b:.3f} MeV]",
                                      color=INK)
            self._top_axis.tick_params(colors=INK_2)
        self.canvas.draw_idle()

    # ----- mouse -----
    def _level_positions(self):
        return np.array([self.session.position(l) for l in self.session.levels])

    def on_press(self, event):
        if self.spectrum is None or event.inaxes is None or event.button != 1 \
                or self.toolbar_busy() or event.xdata is None:
            return
        s = self.session

        if self.awaiting_anchor:
            if not s.levels:
                self.status("Type the energy levels in the header first, then click the first peak.")
                return
            centre, ok = peak_centroid(self.edges, self.counts, event.xdata)
            try:
                s.anchor(centre)
            except ValueError as err:
                self.status(str(err))
                return
            self.awaiting_anchor = False
            how = "Gaussian centroid" if ok else "clicked position (no clear peak to fit)"
            self.status(f"Anchor: {s.levels[0].energy:g} MeV at channel {centre:g} ({how}). "
                        "Press Enter to record it. 'b' shifts all lines, 'm' moves one line.")
            self.on_change()
            return

        if not s.is_anchored:
            return
        i = self._nearest(event, self._level_positions())
        if i is None:
            return
        lvl = s.levels[i]
        s.selected = lvl
        if self.mode == "m":
            self._drag = ("one", lvl)
        else:
            self._drag = ("all", event.xdata, s.trial_b)
        self.on_change()

    def on_motion(self, event):
        if self._drag is None or event.xdata is None:
            return
        s = self.session
        if self._drag[0] == "one":
            s.set_level_channel(self._drag[1], event.xdata)
        else:
            _, x0, b0 = self._drag
            # moving right by d channels = lowering b by m*d
            s.trial_b = round(b0 - s.trial_m * (event.xdata - x0), 2)
        self.on_change()

    def on_release(self, event):
        self._drag = None

    # ----- keyboard -----
    def on_key(self, key, n):
        s = self.session
        if key in ("m", "b"):
            self.mode = key
            self.status("Mode m: select a line and move it on its own with the left/right arrows "
                        "(up/down change the slope)." if key == "m" else
                        "Mode b: left/right arrows shift all unrecorded lines together.")
            self.on_change()
            return
        if key == "a":
            self.awaiting_anchor = True
            self.status("Click the peak of the FIRST energy level to re-anchor "
                        "(this clears the recorded points).")
            return
        if not s.is_anchored:
            return
        sel = s.selected

        if key in ("left", "right"):
            sign = 1 if key == "right" else -1
            if self.mode == "b":
                s.shift_b(-sign * n)
            elif sel is not None:
                s.move_level(sel, sign * n * CHANNEL_RESOLUTION)
            else:
                self.status("Mode m: click a line first to select it.")
                return
        elif key in ("up", "down") and self.mode == "m":
            s.stretch_m(-n if key == "up" else n)   # up spreads lines apart
        elif key == "enter" and sel is not None:
            s.record(sel)
            nxt = s.next_unrecorded(after=sel)
            self.status(f"Recorded {sel.energy:g} MeV at channel {sel.recorded_channel:g}."
                        + (f" Next: {nxt.energy:g} MeV." if nxt else " All levels recorded."))
            s.selected = nxt or sel
        elif key in ("n", "p") and s.levels:
            i = s.levels.index(sel) if sel in s.levels else -1
            s.selected = s.levels[(i + (1 if key == "n" else -1)) % len(s.levels)]
        elif key == "c" and sel is not None:
            centre, ok = peak_centroid(self.edges, self.counts, s.position(sel))
            if ok:
                s.set_level_channel(sel, centre)
                self.status(f"Snapped {sel.energy:g} MeV to the peak centroid at channel {centre:g}.")
            else:
                self.status("No clear peak near this line to snap to.")
                return
        elif key in ("backspace", "delete") and sel is not None:
            s.remove_level(sel)
            self.status(f"Removed {sel.energy_tab:g} MeV from the calibration.")
        elif key == "escape":
            s.selected = None
        else:
            return
        self.on_change()


# ======================================================================
class FitPanel(PlotPanel):
    """Top-right panel: recorded (channel, E) points and the straight-line fit."""

    def __init__(self, session, on_change, status, parent=None):
        super().__init__(session, on_change, status, parent)
        self._drag = None
        self.refresh()

    def refresh(self):
        before = self._limits() if self._auto_limits is not None else None
        ax = self.ax
        ax.cla()
        self._style_axes(ax)
        ax.set_xlabel("ADC channel", color=INK)
        ax.set_ylabel("E (MeV)", color=INK)
        s = self.session
        rec = s.recorded_levels()
        if not rec:
            ax.text(0.5, 0.5, "Recorded points appear here\n(align a level, then press Enter)",
                    transform=ax.transAxes, ha="center", va="center", color=INK_2)
            self._auto_limits = None
            self.canvas.draw_idle()
            return

        ch, e = s.points()
        colors = [SELECTED if l is s.selected else RECORDED for l in rec]
        ax.scatter(ch, e, s=[70 if l is s.selected else 40 for l in rec], c=colors,
                   edgecolors="white", linewidths=1.5, zorder=4, label="recorded points")
        # a grey cross where a point's tabulated energy is, if you moved it up/down
        mod = [l for l in rec if l.energy_modified]
        if mod:
            ax.scatter([l.recorded_channel for l in mod], [l.energy_tab for l in mod],
                       marker="x", color=INK_2, s=30, zorder=3, label="tabulated energy")

        if s.fit is not None:
            f = s.fit
            pad = 0.05 * (ch.max() - ch.min())
            xs = np.array([ch.min() - pad, ch.max() + pad])
            m_txt = f"m = {f.m:.6g}" + (f" ± {f.m_err:.2g}" if f.m_err is not None else "") + " MeV/ch"
            b_txt = f"b = {f.b:.4f}" + (f" ± {f.b_err:.2g}" if f.b_err is not None else "") + " MeV"
            ax.plot(xs, f.energy(xs), color=FIT, linewidth=2,
                    label=f"E = m·ch + b\n{m_txt}\n{b_txt}", zorder=2)
        ax.legend(loc="upper left", fontsize=8, frameon=True)
        # while you drag a point, hold the view still so the point follows the mouse
        self._keep_or_autoscale(before, force_keep=self._drag is not None)
        self.canvas.draw_idle()

    def on_press(self, event):
        if event.inaxes is None or event.button != 1 or self.toolbar_busy():
            return
        rec = self.session.recorded_levels()
        ch, e = self.session.points()
        i = self._nearest(event, ch, e)
        if i is None:
            return
        self.session.selected = rec[i]
        self._drag = rec[i]
        self.on_change()

    def on_motion(self, event):
        if self._drag is None or event.xdata is None:
            return
        lvl, s = self._drag, self.session
        # energy moves in 0.01 MeV steps away from the tabulated value
        steps = round((event.ydata - lvl.energy_tab) / 0.01)
        lvl.energy = round(lvl.energy_tab + steps * 0.01, 6)
        s.set_level_channel(lvl, event.xdata)   # also refits
        self.on_change()

    def on_release(self, event):
        self._drag = None

    def on_key(self, key, n):
        s = self.session
        sel = s.selected
        if sel is None or not sel.is_recorded:
            return
        if key in ("left", "right"):
            s.move_level(sel, (1 if key == "right" else -1) * n * CHANNEL_RESOLUTION)
        elif key in ("up", "down"):
            s.change_energy(sel, n if key == "up" else -n)
        elif key in ("backspace", "delete"):
            s.unrecord(sel)
            self.status(f"Removed the point for {sel.energy_tab:g} MeV (the level stays in the list).")
        elif key == "escape":
            s.selected = None
        else:
            return
        self.on_change()


# ======================================================================
class ResidualPanel(PlotPanel):
    """Bottom panel: residual E_level - fit(channel) against E_level."""

    def __init__(self, session, on_change, status, parent=None):
        super().__init__(session, on_change, status, parent)
        self.figure.set_size_inches(10, 2.5)
        self.refresh()

    def refresh(self):
        before = self._limits() if self._auto_limits is not None else None
        ax = self.ax
        ax.cla()
        self._style_axes(ax)
        ax.set_xlabel("E level (MeV)", color=INK)
        ax.set_ylabel("E − fit (MeV)", color=INK)
        ax.axhline(0, color=INK_2, linestyle="--", linewidth=1)
        s = self.session
        if s.fit is not None:
            rec = s.recorded_levels()
            _, e = s.points()
            res = s.residuals()
            ax.scatter(e, res, c=[SELECTED if l is s.selected else RECORDED for l in rec],
                       s=[70 if l is s.selected else 40 for l in rec],
                       edgecolors="white", linewidths=1.5, zorder=4)
            rms = float(np.sqrt(np.mean(res ** 2)))
            ax.set_title(f"RMS residual = {rms * 1000:.1f} keV", fontsize=9, color=INK_2, loc="right")
            self._keep_or_autoscale(before)
        self.canvas.draw_idle()

    def on_press(self, event):
        if event.inaxes is None or event.button != 1 or self.toolbar_busy() \
                or self.session.fit is None:
            return
        rec = self.session.recorded_levels()
        _, e = self.session.points()
        i = self._nearest(event, e, self.session.residuals())
        if i is not None:
            self.session.selected = rec[i]
            self.on_change()
