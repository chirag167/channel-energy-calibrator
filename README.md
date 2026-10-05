# Channel-to-Energy Calibrator

An interactive tool for turning ADC channel numbers into energy. Load a 1D
spectrum, type the energy levels you expect, click the first peak, and line
the rest up while seeing the fit and residuals update as you go.

Convention used throughout:  **E = m * channel + b**  (E in MeV).

## 1. Setup (one time, any OS)

Needs Python 3.9 or newer. From inside this folder:

macOS / Linux
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

Windows (PowerShell)
    py -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt

Each later session only needs the `activate` line.

## 2. Run

    python run_gui.py
    python run_gui.py examples/example_events.csv     # open a file straight away

To try it without real data, run `python examples/make_example_spectra.py`
(the two example files are already included). The example peaks follow
E = 0.002557*ch + 0.054, so a good calibration should land close to that.

Real data from detector 0, disk 22 (taken from DISK_22/adc_tdc_0_disk22.txt):

    li7_ca48_adc_ch0.csv          all ADC channels, no gate (6217 events)
    li7_ca48_adc_ch0_alpha.csv    alpha gate, first 50 points of coordinates_0.txt (3556 events)
    li7_ca48_adc_ch0_proton.csv   proton gate, remaining points (1103 events)

These have few counts per peak, so use 8 or more channels per bin.

Example level list for the example files:
    9.656, 6.549, 5.958, 5.450, 5.261, 4.849, 4.708, 4.448

## 3. Input file

A `.csv` file with no header row, in either form:
- 1 column: one ADC channel per event (the tool counts them)
- 2 columns: ADC channel, counts in that channel

Any other file type is refused, with a message asking you to convert it to CSV.
The polygon gating on the ADC vs TDC plot is done before this step.

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

Spectrum panel (top left)
    b             mode b: Left/Right shift ALL unrecorded lines (b by 0.01 MeV);
                  dragging any line also shifts them all
    m             mode m: Left/Right move only the selected line (0.25 channel);
                  dragging a line moves only that line;
                  Up/Down change the slope (Up spreads lines apart)
    Shift+arrow   step 10 times larger
    Enter         record the selected line as a (channel, E) point
    n / p         select next / previous level
    c             snap selected line to the nearest peak centre
    Delete/Backspace   remove the selected level from the calibration
    a             re-anchor: the next click places the first level again
                  (this clears the recorded points)
    Esc           deselect
    r             reset the view

Fit panel (top right): click a point to select it, then
    drag, or Left/Right (channel, 0.25 steps) and Up/Down (energy, 0.01 MeV steps).
    A grey x marks the tabulated energy if you have changed it.
    Delete/Backspace removes the point; the level stays in the list.

Every panel has its own zoom/pan toolbar. While zoom or pan is switched on,
clicks zoom the plot; switch it off to select lines and points again.
The trial m and b can also be typed into the header boxes (press Enter).
Recorded points never move when you shift or stretch the trial m and b.

File menu
    Upload     open a CSV spectrum
    Export     save one plot as PNG or PDF
    Download   save all three plots (PNG, 300 dpi) and <name>_calibration_points.csv
               (m, b with errors; channel, tabulated E, E used, fit E, residual)

Fit errors on m and b are ordinary least-squares standard errors and appear
once there are 3 or more points.

## 6. How the code is organised (a short guide to the classes)

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

The main idea: the data lives in one object (`CalibrationSession`), and the
panels only draw it. When a panel changes something (a key press or a drag),
it calls the session's method (for example `session.record(level)`) and then
`on_change()`. The main window then redraws all three panels, so they always
agree. `calibration.py` never imports anything from Qt, so you can also use it
on its own in a notebook:

    from calibrator.calibration import CalibrationSession
    s = CalibrationSession()
    s.set_levels([9.656, 5.958, 4.448])
    s.anchor(3755.0); s.record(s.levels[0])
    ...
    s.fit.m, s.fit.b

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

    git config --global user.name  "Your Name"
    git config --global user.email "you@example.com"

**Before you make the repository public:** the examples/ folder holds real
experimental data (the li7_ca48_*.csv files). Check with your group that it can
be shared. If not, make the repository private, or remove those files from
examples/ before the first commit.

Step 1 - create an empty repository on the website.
On github.com click "+" (top right) > "New repository". Give it a name such as
`channel-energy-calibrator`, choose Public or Private, and leave "Add a README",
".gitignore" and "license" unticked (this folder already has them).
Click "Create repository".

Step 2 - turn this folder into a git repository and upload it.
In a terminal, inside this folder:

    git init
    git add .
    git status                  # check the list: no .venv, no __pycache__
    git commit -m "First version of the channel-to-energy calibrator"
    git branch -M main
    git remote add origin https://github.com/<your-username>/channel-energy-calibrator.git
    git push -u origin main

When git asks for a password, GitHub needs a "personal access token" instead
of your account password: github.com > Settings > Developer settings >
Personal access tokens. (Or install the GitHub CLI, run `gh auth login` once,
and git will use that.)

Step 3 - later changes.

    git add .
    git commit -m "Describe what you changed"
    git push

The .gitignore file in this folder keeps the virtual environment (.venv),
Python caches and test output out of the repository. Optional: add a LICENSE
file (MIT is a common choice for research code) so others know how they may use it.

## 9. Measuring how long the GUI takes to start

`time python run_gui.py` does not measure start-up. It keeps counting until you
close the window, so it measures your whole session. Instead, run this from
this folder. It builds the window, prints the time as soon as the window is
ready, and quits:

    python -c "
    import time; t = time.perf_counter()
    import run_gui
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    app = QApplication([]); w = run_gui.MainWindow(); w.show()
    QTimer.singleShot(0, lambda: (print(f'GUI ready in {time.perf_counter() - t:.2f} s'), app.quit()))
    app.exec()"

The first run after installing is slower (Python compiles the libraries and
matplotlib builds its font cache), so time it two or three times. You can put
`time` in front of the command above to include Python's own start-up too.
