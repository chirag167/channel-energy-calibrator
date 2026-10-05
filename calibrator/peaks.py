"""
peaks.py -- find the centre of a peak near a clicked channel.

When you click on a peak, the exact pixel you hit is a little arbitrary. We
fit a Gaussian plus a flat background to the counts in a small window around
the click and use the Gaussian's centre. If the fit fails (too few counts, no
clear peak), we fall back to the clicked position.
"""

import numpy as np
from scipy.optimize import curve_fit

CHANNEL_RESOLUTION = 0.25  # peak positions are stored to the nearest 0.25 channel


def round_channel(ch):
    """Round a channel value to the nearest 0.25 channel."""
    return round(ch / CHANNEL_RESOLUTION) * CHANNEL_RESOLUTION


def _gauss_plus_const(x, amp, mu, sigma, const):
    return amp * np.exp(-0.5 * ((x - mu) / sigma) ** 2) + const


def peak_centroid(bin_edges, counts, clicked_channel, half_window=None):
    """Return (centroid, fitted_ok).

    Parameters
    ----------
    bin_edges, counts : arrays from ``Spectrum.binned``.
    clicked_channel : float, where the user clicked.
    half_window : float, channels either side of the click to use.
        Defaults to the larger of 10 channels or 4 bins.
    """
    centres = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    bin_width = bin_edges[1] - bin_edges[0]
    if half_window is None:
        half_window = max(10.0, 4 * bin_width)

    in_window = np.abs(centres - clicked_channel) <= half_window
    x, y = centres[in_window], counts[in_window]
    if len(x) < 5 or y.max() <= 0:
        return round_channel(clicked_channel), False

    p0 = [y.max() - y.min(), x[np.argmax(y)], half_window / 4, y.min()]
    lower = [0, x.min(), bin_width / 4, 0]
    upper = [np.inf, x.max(), 2 * half_window, np.inf]
    try:
        popt, _ = curve_fit(_gauss_plus_const, x, y, p0=p0,
                            bounds=(lower, upper), maxfev=5000)
    except (RuntimeError, ValueError):
        return round_channel(clicked_channel), False

    mu = popt[1]
    # Reject fits whose centre ended up pinned to the window edge.
    if abs(mu - clicked_channel) > 0.95 * half_window:
        return round_channel(clicked_channel), False
    return round_channel(mu), True
