"""
calibration.py -- the calibration "model": energy levels, recorded points and the fit.

Nothing in this file knows about windows, buttons or plots. Keeping the physics
and bookkeeping separate from the GUI means you can test it on its own (see
tests/test_calibration.py) or reuse it in a notebook.

Convention used everywhere:   E = m * channel + b     (E in MeV)

Two calibrations are kept:

* the *trial* calibration (trial_m, trial_b) -- the current guess, used to
  place the energy-level lines on top of the histogram while you align them;
* the *fit* -- a straight-line fit through the (channel, E) points you have
  recorded. Once there are 2 or more points, the trial calibration is set
  to the fit, so the levels you have not yet recorded jump close to their peaks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .peaks import round_channel

ENERGY_STEP = 0.01  # MeV; smallest change of b or of a point's energy


# ----------------------------------------------------------------------
# Small data classes
# ----------------------------------------------------------------------
@dataclass
class Level:
    """One energy level used in the calibration.

    ``@dataclass`` writes the ``__init__`` for us from the fields listed below,
    so ``Level(energy_tab=9.656, energy=9.656)`` just works.

    Fields
    ------
    energy_tab : the value you typed (tabulated / literature energy, MeV).
    energy : the energy actually used in the fit. Normally equal to
        energy_tab; changes only if you move the point up/down in the fit panel.
    offset : extra channel shift for this line only ('m' mode moves), used
        while the level is not yet recorded.
    recorded_channel : channel stored when you pressed Enter; None if not recorded.
    """
    energy_tab: float
    energy: float
    offset: float = 0.0
    recorded_channel: float | None = None

    @property
    def is_recorded(self):
        return self.recorded_channel is not None

    @property
    def energy_modified(self):
        return abs(self.energy - self.energy_tab) > 1e-9


@dataclass
class LinearFit:
    """Result of fitting E = m*channel + b."""
    m: float
    b: float
    m_err: float | None  # standard errors; None when there are only 2 points
    b_err: float | None
    n_points: int

    def energy(self, channel):
        return self.m * np.asarray(channel) + self.b


def fit_line(channels, energies):
    """Least-squares straight line through the points. Returns LinearFit or None."""
    x = np.asarray(channels, dtype=float)
    y = np.asarray(energies, dtype=float)
    n = len(x)
    if n < 2:
        return None
    sxx = np.sum((x - x.mean()) ** 2)
    if sxx == 0:  # all points at the same channel: slope undefined
        return None
    m = np.sum((x - x.mean()) * (y - y.mean())) / sxx
    b = y.mean() - m * x.mean()
    m_err = b_err = None
    if n >= 3:
        s2 = np.sum((y - (m * x + b)) ** 2) / (n - 2)
        m_err = float(np.sqrt(s2 / sxx))
        b_err = float(np.sqrt(s2 * (1.0 / n + x.mean() ** 2 / sxx)))
    return LinearFit(float(m), float(b), m_err, b_err, n)


# ----------------------------------------------------------------------
# The session
# ----------------------------------------------------------------------
class CalibrationSession:
    """Everything about one calibration: levels, trial m and b, recorded points, fit.

    The GUI panels read from this object to draw themselves and call its
    methods when you click or press keys. After each change the main window
    redraws all panels, so they always agree with each other.
    """

    def __init__(self):
        self.levels: list[Level] = []
        self.trial_m: float | None = None
        self.trial_b: float | None = None
        self.selected: Level | None = None
        self.fit: LinearFit | None = None
        self.max_channel: float = 8192.0  # updated when a spectrum is loaded

    # ---------------- energy levels ----------------
    @staticmethod
    def parse_levels(text):
        """Turn '9.656, 6.557, 5.958' into [9.656, 6.557, 5.958]. Raises ValueError."""
        parts = [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
        if not parts:
            raise ValueError("Please type at least one energy level.")
        values = []
        for p in parts:
            try:
                values.append(float(p))
            except ValueError:
                raise ValueError(f"'{p}' is not a number.")
        if len(set(values)) != len(values):
            raise ValueError("The same energy is listed twice.")
        return values

    def set_levels(self, energies):
        """Replace the level list, keeping the work already done on levels that remain."""
        old = {lvl.energy_tab: lvl for lvl in self.levels}
        self.levels = [old.get(e, Level(energy_tab=e, energy=e)) for e in energies]
        if self.selected not in self.levels:
            self.selected = None
        self._refit()

    def levels_text(self):
        """The level list written back as text (for the header box)."""
        return ", ".join(f"{lvl.energy_tab:g}" for lvl in self.levels)

    def remove_level(self, level):
        """Drop a level from the calibration entirely (and its point, if recorded)."""
        idx = self.levels.index(level)
        self.levels.remove(level)
        if self.selected is level:
            # select a neighbour so you can keep working with the keyboard
            self.selected = self.levels[min(idx, len(self.levels) - 1)] if self.levels else None
        self._refit()

    # ---------------- anchor & trial calibration ----------------
    @property
    def is_anchored(self):
        return self.trial_m is not None

    def anchor(self, channel):
        """Start (or restart) the calibration: put the FIRST level at ``channel``.

        With a single point we cannot know both m and b, so we assume b = 0 and
        m = E_first / channel. Shift with 'b' mode and move single lines with
        'm' mode to line everything up.
        """
        if not self.levels:
            raise ValueError("Type the energy levels first.")
        if channel <= 0:
            raise ValueError("The anchor peak must be at a positive channel.")
        first = self.levels[0]
        self.trial_m = first.energy / channel
        self.trial_b = 0.0
        for lvl in self.levels:
            lvl.offset = 0.0
            lvl.recorded_channel = None
            lvl.energy = lvl.energy_tab
        self.selected = first
        self.fit = None

    def set_trial(self, m=None, b=None):
        """Type-in values from the header boxes."""
        if m is not None:
            if m == 0:
                raise ValueError("The slope m cannot be zero.")
            self.trial_m = m
        if b is not None:
            self.trial_b = b

    def position(self, level):
        """Channel at which a level's line is drawn on the histogram."""
        if level.is_recorded:
            return level.recorded_channel
        return (level.energy - self.trial_b) / self.trial_m + level.offset

    def shift_b(self, n_steps):
        """'b' mode: move every not-yet-recorded line together by n_steps * 0.01 MeV.

        Increasing b lowers the channel of every level, so lines move LEFT.
        The arrow keys call this with the sign flipped so that the right-arrow
        moves lines right.
        """
        self.trial_b = round(self.trial_b + n_steps * ENERGY_STEP, 6)

    @property
    def m_step(self):
        """Slope step chosen so the energy at the top channel changes by 0.01 MeV."""
        return ENERGY_STEP / self.max_channel

    def stretch_m(self, n_steps):
        """'m' mode, no level selected: change the slope (spreads lines apart or together)."""
        new_m = self.trial_m + n_steps * self.m_step
        if new_m > 0 or self.trial_m < 0:
            self.trial_m = new_m

    # ---------------- single-level moves ----------------
    def move_level(self, level, d_channels):
        """'m' mode: move one line by d_channels (only that line moves)."""
        self.set_level_channel(level, self.position(level) + d_channels)

    def set_level_channel(self, level, channel):
        """Put one line at an exact channel (used by mouse drags and peak snapping)."""
        channel = round_channel(channel)
        if level.is_recorded:
            level.recorded_channel = channel
            self._refit()
        else:
            level.offset = channel - (level.energy - self.trial_b) / self.trial_m

    def change_energy(self, level, n_steps):
        """Fit panel up/down arrows: change the energy used for this point by n*0.01 MeV."""
        level.energy = round(level.energy + n_steps * ENERGY_STEP, 6)
        if level.is_recorded:
            self._refit()

    # ---------------- recording points ----------------
    def record(self, level):
        """Enter: store (current channel, energy) as a calibration point."""
        level.recorded_channel = round_channel(self.position(level))
        level.offset = 0.0
        self._refit()

    def unrecord(self, level):
        """Delete the point from the fit (the level itself stays in the list)."""
        level.recorded_channel = None
        level.offset = 0.0
        level.energy = level.energy_tab
        self._refit()

    def recorded_levels(self):
        return [lvl for lvl in self.levels if lvl.is_recorded]

    def points(self):
        """Arrays (channels, energies) of the recorded points."""
        rec = self.recorded_levels()
        return (np.array([l.recorded_channel for l in rec], dtype=float),
                np.array([l.energy for l in rec], dtype=float))

    def residuals(self):
        """E_level - fit(channel) for each recorded point (empty if there is no fit)."""
        if self.fit is None:
            return np.array([])
        ch, e = self.points()
        return e - self.fit.energy(ch)

    def next_unrecorded(self, after=None):
        """The next level still to record, searching forward from ``after``."""
        if not self.levels:
            return None
        start = self.levels.index(after) + 1 if after in self.levels else 0
        order = self.levels[start:] + self.levels[:start]
        return next((l for l in order if not l.is_recorded), None)

    def _refit(self):
        """Refit whenever the recorded points change.

        With 2+ points the trial calibration follows the fit, and one-off
        shifts of unrecorded lines are cleared, so those lines land where the
        fit predicts.
        """
        ch, e = self.points()
        self.fit = fit_line(ch, e)
        if self.fit is not None:
            self.trial_m, self.trial_b = self.fit.m, self.fit.b
            for lvl in self.levels:
                if not lvl.is_recorded:
                    lvl.offset = 0.0

    # ---------------- export ----------------
    def points_table(self):
        """Rows for the CSV written by File > Download."""
        rows = []
        for lvl in self.recorded_levels():
            fit_e = self.fit.energy(lvl.recorded_channel) if self.fit else np.nan
            rows.append((lvl.recorded_channel, lvl.energy_tab, lvl.energy,
                         float(fit_e), float(lvl.energy - fit_e)))
        return rows
