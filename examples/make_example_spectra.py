"""
Make two synthetic test spectra (so you can try the GUI without real data).

Peaks are placed as if E = 0.002557 * channel + 0.054 MeV, roughly the alpha
calibration in ADC_Channel_0.ipynb, on top of a falling background.

  example_events.csv     -- 1 column: one ADC channel per event
  example_histogram.csv  -- 2 columns: ADC channel, counts
"""
from pathlib import Path

import numpy as np

M_TRUE, B_TRUE = 0.002557, 0.054
LEVELS = [9.656, 6.549, 5.958, 5.450, 5.261, 4.849, 4.708, 4.448]
AREAS = [4000, 2500, 1800, 1500, 2200, 1200, 1600, 1000]
SIGMA = 10.0  # channels

rng = np.random.default_rng(7)
events = [rng.normal((e - B_TRUE) / M_TRUE, SIGMA, size=a) for e, a in zip(LEVELS, AREAS)]
events.append(1000 + rng.exponential(900, size=15000))      # background
ch = np.round(np.concatenate(events)).astype(int)
ch = ch[(ch > 0) & (ch < 8192)]

here = Path(__file__).parent
np.savetxt(here / "example_events.csv", ch, fmt="%d")
channels, counts = np.unique(ch, return_counts=True)
np.savetxt(here / "example_histogram.csv", np.column_stack([channels, counts]), fmt="%d", delimiter=",")
print("wrote example_events.csv and example_histogram.csv")
print("true peak channels:", [round((e - B_TRUE) / M_TRUE, 2) for e in LEVELS])
