"""
spectrum.py -- loading and binning the uncalibrated 1D ADC spectrum.

The GUI accepts two kinds of CSV file (no header row):

    1 column :  one ADC channel number per detected event (an "event list").
                The counting is done here.
    2 columns:  ADC channel, counts in that channel (already a histogram).

Internally both are stored the same way: an array of channel numbers and an
array of counts in each channel. Rebinning then sums neighbouring channels.
"""

from pathlib import Path

import numpy as np


class SpectrumLoadError(Exception):
    """Raised when a file cannot be used as a spectrum.

    Defining our own exception class lets the GUI catch *only* the problems
    we expect (wrong format, bad numbers) and show a friendly message.
    """


class Spectrum:
    """An uncalibrated 1D spectrum: counts versus ADC channel.

    Attributes
    ----------
    path : Path
        The file the data came from.
    channels : np.ndarray
        Channel numbers (one entry per distinct channel), sorted.
    counts : np.ndarray
        Counts in each channel (same length as ``channels``).
    input_kind : str
        "event list" or "histogram" -- what the file contained.
    """

    def __init__(self, path, channels, counts, input_kind):
        self.path = Path(path)
        self.channels = np.asarray(channels, dtype=float)
        self.counts = np.asarray(counts, dtype=float)
        self.input_kind = input_kind

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------
    @classmethod
    def from_csv(cls, path):
        """Read a CSV file and return a new Spectrum.

        A ``classmethod`` receives the class itself (``cls``) instead of an
        instance, so it can build and return a new object. It is the usual
        way to write "alternative constructors" such as "make a Spectrum
        from a file".
        """
        path = Path(path)
        if path.suffix.lower() != ".csv":
            raise SpectrumLoadError(
                f"'{path.name}' is not a CSV file.\n\n"
                "Please convert it to CSV format (comma-separated, no header;\n"
                "either one column of ADC channels, or two columns of\n"
                "ADC channel, counts) and upload it again."
            )

        rows = cls._read_numeric_rows(path)
        n_cols = rows.shape[1]

        if n_cols == 1:
            # Event list: count how many times each channel occurs.
            channels, counts = np.unique(rows[:, 0], return_counts=True)
            kind = "event list"
        elif n_cols == 2:
            # Already a histogram. Merge any repeated channels, just in case.
            channels, inverse = np.unique(rows[:, 0], return_inverse=True)
            counts = np.bincount(inverse, weights=rows[:, 1])
            kind = "histogram"
        else:
            raise SpectrumLoadError(
                f"'{path.name}' has {n_cols} columns. Expected 1 column "
                "(ADC channels) or 2 columns (ADC channel, counts)."
            )

        if len(channels) < 2:
            raise SpectrumLoadError(f"'{path.name}' has fewer than two channels of data.")
        return cls(path, channels, counts, kind)

    @staticmethod
    def _read_numeric_rows(path):
        """Return the file's numbers as a 2D array (rows x columns).

        A header row is not expected, but if the first line is not numeric we
        skip it rather than fail. Blank lines are ignored.
        """
        lines = [ln.strip() for ln in path.read_text().splitlines() if ln.strip()]
        if not lines:
            raise SpectrumLoadError(f"'{path.name}' is empty.")

        def parse(line):
            return [float(v) for v in line.replace(";", ",").split(",") if v.strip() != ""]

        try:
            parse(lines[0])
        except ValueError:
            lines = lines[1:]  # looks like a header row; skip it

        try:
            rows = [parse(ln) for ln in lines]
        except ValueError as err:
            raise SpectrumLoadError(f"'{path.name}' contains non-numeric values ({err}).")

        widths = {len(r) for r in rows}
        if len(widths) != 1:
            raise SpectrumLoadError(f"'{path.name}' has rows with different numbers of columns.")
        return np.array(rows, dtype=float)

    # ------------------------------------------------------------------
    # Binning
    # ------------------------------------------------------------------
    def binned(self, channels_per_bin=1):
        """Return (bin_edges, counts) with ``channels_per_bin`` channels summed per bin.

        Bins are centred on whole channels: with 1 channel per bin, channel 100
        is the bin from 99.5 to 100.5.
        """
        width = max(1, int(channels_per_bin))
        start = np.floor(self.channels.min()) - 0.5
        stop = np.ceil(self.channels.max()) + 0.5
        n_bins = int(np.ceil((stop - start) / width))
        edges = start + width * np.arange(n_bins + 1)
        counts, _ = np.histogram(self.channels, bins=edges, weights=self.counts)
        return edges, counts

    @property
    def max_channel(self):
        """Largest channel in the data (used to size the slope step)."""
        return float(self.channels.max())

    @property
    def total_counts(self):
        return float(self.counts.sum())
