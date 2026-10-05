# Channel-to-Energy Calibrator

An interactive tool for turning ADC channel numbers into energy. Load a 1D
spectrum, type the energy levels you expect, click the first peak, and line
the rest up while seeing the fit and residuals update as you go.

Convention used throughout:  **E = m * channel + b**  (E in MeV).

## 1. Setup (one time, any OS)

Needs Python 3.9 or newer. From inside this folder:

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows (PowerShell):

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Each later session only needs the `activate` line.

## 2. Input file

A `.csv` file with no header row, in either form:
- 1 column: one ADC channel per event (the tool counts them)
- 2 columns: ADC channel, counts in that channel

Any other file type is refused, with a message asking you to convert it to CSV.
The polygon gating on the ADC vs TDC plot is done before this step.

## 3. Run

```bash
python run_gui.py                                  # empty window, use File > Upload
python run_gui.py examples/example_events.csv      # open a file straight away
```

### Example: try it on manufactured data

The `examples/` folder has two small test spectra. They are **made up, not
measured**: `examples/make_example_spectra.py` generates them. It places eight
Gaussian peaks (10 channels wide) at the channels you would get if the
calibration were exactly E = 0.002557 * channel + 0.054 MeV, and adds a falling
background. A fixed random seed means the script always writes the same files.

| File | Format |
|---|---|
| `example_events.csv` | 1 column: one ADC channel per event |
| `example_histogram.csv` | 2 columns: ADC channel, counts (the same spectrum, already counted) |

Because the true calibration is known, you can check that the tool recovers it:

1. Open the file:

   ```bash
   python run_gui.py examples/example_events.csv
   ```

2. Leave the binning at 1 channel per bin and type these energy levels (MeV),
   then press Enter:

   ```text
   9.656, 6.549, 5.958, 5.450, 5.261, 4.849, 4.708, 4.448
   ```

3. Click the tall peak near channel 3755. This anchors 9.656 MeV.
4. Press Enter to record the anchor.
5. For each remaining level, press `c` (snap the selected line to its peak),
   then Enter (record it). The next level is selected automatically.

After all eight levels are recorded, the fit panel should show
m ≈ 0.002557 MeV/channel and b ≈ 0.055 MeV, and the residual panel an RMS of
about 1 keV.

To recreate the two files:

```bash
python examples/make_example_spectra.py
```

## 4. How a calibration goes

1. File > Upload the spectrum.
2. Type the energy levels (MeV, comma-separated) and press Enter. The first
   level is the anchor.
3. Click the anchor's peak. The position snaps to the peak centre (a small
   Gaussian fit), and all levels appear as vertical lines using a first guess
   of m = E_first / channel and b = 0.
4. Press Enter to record the anchor as the first point.
5. Line up the next level:
   - press `b`, then use Left/Right to slide all the lines together, or
   - press `m`, click one line, and move just that line (arrows or drag),
     or press `c` to snap it to the nearest peak centre.
   Then press Enter to record it.
6. Once 2 points are recorded, the straight-line fit appears, and the lines not
   yet recorded jump to where the fit puts them. Usually each remaining level
   is then just `c` and Enter away. The residual panel appears at the bottom.
7. Fine-tune in the fit panel if needed, then File > Download.

Line colours: orange dashed = not recorded yet, green = recorded,
violet = selected.

## 5. Controls

Click a panel first so it receives the keyboard.

**Spectrum panel (top left)**

| Key | Action |
|---|---|
| `b` | mode b: Left/Right shift ALL unrecorded lines (b by 0.01 MeV); dragging any line also shifts them all |
| `m` | mode m: Left/Right move only the selected line (0.25 channel); dragging a line moves only that line; Up/Down change the slope (Up spreads lines apart) |
| `Shift` + arrow | step 10 times larger |
| `Enter` | record the selected line as a (channel, E) point |
| `n` / `p` | select next / previous level |
| `c` | snap the selected line to the nearest peak centre |
| `Delete` / `Backspace` | remove the selected level from the calibration |
| `a` | re-anchor: the next click places the first level again (this clears the recorded points) |
| `Esc` | deselect |
| `r` | reset the view |

**Fit panel (top right):** click a point to select it, then drag it, or use
Left/Right (channel, 0.25 steps) and Up/Down (energy, 0.01 MeV steps). A grey x
marks the tabulated energy if you have changed it. `Delete`/`Backspace`
removes the point; the level stays in the list.

Every panel has its own zoom/pan toolbar. While zoom or pan is switched on,
clicks zoom the plot; switch it off to select lines and points again.
The trial m and b can also be typed into the header boxes (press Enter).
Recorded points never move when you shift or stretch the trial m and b.

**File menu**

| Item | Action |
|---|---|
| Upload | open a CSV spectrum |
| Export | save one plot as PNG or PDF |
| Download | save all three plots (PNG, 300 dpi) and `<name>_calibration_points.csv` (m, b with errors; channel, tabulated E, E used, fit E, residual) |

Fit errors on m and b are ordinary least-squares standard errors and appear
once there are 3 or more points.

## 6. How the code is organised (a short guide to the classes)

```text
run_gui.py                 starts the app
calibrator/
  spectrum.py    Spectrum            reads the CSV and does the binning
                 SpectrumLoadError   our own error type for bad files
  peaks.py       peak_centroid()     Gaussian fit around a click
  calibration.py Level               one energy level (a @dataclass)
                 LinearFit           fit result: m, b, errors
                 CalibrationSession  levels, trial m/b, recorded points, fit
  panels.py      PlotPanel           base class: figure + canvas + toolbar
                   SpectrumPanel     histogram and level lines (inherits PlotPanel)
                   FitPanel          E vs channel and the fit line
                   ResidualPanel     residuals
  main_window.py MainWindow          header, menus, layout; connects everything
tests/           test_calibration.py (run: python -m pytest tests)
                 gui_smoke.py        drives the GUI with simulated clicks
```

The main idea: the data lives in one object (`CalibrationSession`), and the
panels only draw it. When a panel changes something (a key press or a drag),
it calls the session's method (for example `session.record(level)`) and then
`on_change()`. The main window then redraws all three panels, so they always
agree. `calibration.py` never imports anything from Qt, so you can also use it
on its own in a notebook:

```python
from calibrator.calibration import CalibrationSession
s = CalibrationSession()
s.set_levels([9.656, 5.958, 4.448])
s.anchor(3755.0); s.record(s.levels[0])
...
s.fit.m, s.fit.b
```

## 7. Current limitations

- Linear calibration only: E = m * channel + b. There is no quadratic or other
  non-linear option.
- One spectrum and one list of energy levels at a time. You cannot yet combine
  points from two spectra (for example alphas and protons from the same
  detector) into one fit. **This is changing soon, once the testing phase is
  done.**
- All points count equally in the fit. Peak-position uncertainties are not used
  as weights, and the errors on m and b come only from how much the points
  scatter around the line (so they need 3 or more points).
- The gating step (drawing a polygon around a band in the ADC vs TDC plot) is
  not part of the tool. Gate the data first, then load the 1D spectrum.
- Input must be a .csv file with 1 column (ADC channel per event) or 2 columns
  (ADC channel, counts), and no header row.
- Bin widths are whole numbers of channels (1, 2, 3, ...).
- Peak snapping ('c' and the anchor click) fits a single Gaussian on a flat
  background. It can fail or be pulled off-centre when a peak has few counts,
  sits on a sloped background, or is an unresolved doublet. In those cases place
  the line by hand. For a doublet, type the average energy of the two levels.
- No undo, and a session cannot be saved and reopened. File > Download writes
  the points and the fit to a CSV, but the GUI cannot load that CSV back in.
- No corrections for energy loss (for example in a detector dead layer) are
  applied.
- Large event files (around a million rows) take a few seconds to load.

## 8. Putting it on GitHub

One-time setup: install git (macOS: run `xcode-select --install`), make a
free account at github.com, and tell git who you are:

```bash
git config --global user.name  "Your Name"
git config --global user.email "you@example.com"
```

**Real data stays out of the repository:** the .gitignore file excludes the
measured spectra in examples/ (files starting with `li7`), so only the
manufactured example data is uploaded. Check with your group before you ever
add measured data to a public repository.

Step 1 - create an empty repository on the website.
On github.com click "+" (top right) > "New repository". Give it a name such as
`channel-energy-calibrator`, choose Public or Private, and leave "Add a README",
".gitignore" and "license" unticked (this folder already has them).
Click "Create repository".

Step 2 - turn this folder into a git repository and upload it.
In a terminal, inside this folder:

```bash
git init
git add .
git status                  # check the list: no .venv, no __pycache__
git commit -m "First version of the channel-to-energy calibrator"
git branch -M main
git remote add origin git@github.com:<your-username>/<repo-name>.git
git push -u origin main
```

Replace `<your-username>` and `<repo-name>` with your own; the exact address
is under the green "Code" button > "SSH" on the repository page. This uses SSH,
which needs an SSH key added to your GitHub account (github.com > Settings >
SSH and GPG keys); `ssh -T git@github.com` should reply "Hi <your-username>!".

If you set the wrong address, change it with:

```bash
git remote set-url origin git@github.com:<your-username>/<repo-name>.git
git remote -v               # shows the address now in use
```

"Repository not found" when pushing usually means the address is wrong (a typo,
or a placeholder left in) or the repository has not been created on github.com.

Step 3 - later changes.

```bash
git add .
git commit -m "Describe what you changed"
git push
```

The .gitignore file in this folder keeps the virtual environment (.venv),
Python caches and test output out of the repository. Optional: add a LICENSE
file (MIT is a common choice for research code) so others know how they may use it.

## 9. Measuring how long the GUI takes to start

`time python run_gui.py` does not measure start-up. It keeps counting until you
close the window, so it measures your whole session. Instead, run this from
this folder. It builds the window, prints the time as soon as the window is
ready, and quits:

```bash
python -c "
import time; t = time.perf_counter()
import run_gui
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
app = QApplication([]); w = run_gui.MainWindow(); w.show()
QTimer.singleShot(0, lambda: (print(f'GUI ready in {time.perf_counter() - t:.2f} s'), app.quit()))
app.exec()"
```

The first run after installing is slower (Python compiles the libraries and
matplotlib builds its font cache), so time it two or three times. You can put
`time` in front of the command above to include Python's own start-up too.
