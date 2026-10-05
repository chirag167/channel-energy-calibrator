"""Drive the GUI with simulated clicks and keys (no screen needed)."""
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
for k in list(matplotlib.rcParams):
    if k.startswith("keymap."): matplotlib.rcParams[k] = []
from matplotlib.backend_bases import MouseEvent, KeyEvent
from PySide6.QtWidgets import QApplication
from calibrator.main_window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
app = QApplication([])
w = MainWindow(); w.show(); app.processEvents()
ex = Path(__file__).resolve().parents[1] / "examples"

def pump(): app.processEvents(); 
def draw(panel): panel.canvas.draw(); pump()

def click(panel, xdata, ydata=None, name="button_press_event"):
    draw(panel)
    ax = panel.ax
    if ydata is None: ydata = sum(ax.get_ylim())/2 if ax.get_yscale()=="linear" else (ax.get_ylim()[0]*ax.get_ylim()[1])**0.5
    x, y = ax.transData.transform((xdata, ydata))
    ev = MouseEvent(name, panel.canvas, x, y, button=1)
    panel.canvas.callbacks.process(name, ev); pump()

def key(panel, k):
    ev = KeyEvent("key_press_event", panel.canvas, k)
    panel.canvas.callbacks.process("key_press_event", ev); pump()

# bad file type
bad = OUT / "x.txt"; bad.write_text("1,2\n")
from PySide6.QtWidgets import QMessageBox
QMessageBox.critical = staticmethod(lambda *a, **k: print("ERROR DIALOG:", a[2].splitlines()[0]))
w.load_file(str(bad))

assert w.load_file(str(ex / "example_events.csv"))
w.levels_edit.setText("9.656, 6.549, 5.958, 5.450, 5.261, 4.849, 4.708, 4.448")
w.on_levels_entered()
sp, fp, rp = w.spectrum_panel, w.fit_panel, w.residual_panel
s = w.session
click(sp, 3748)                     # anchor near first peak
print("anchor ->", s.position(s.levels[0]), "m", s.trial_m)
key(sp, "enter")                    # record anchor
w.grab().save(str(OUT / "1_anchored.png"))

# b mode: shift all lines, then m mode: move 6.549 line onto its peak with arrows
print("6.549 line before:", s.position(s.levels[1]))
key(sp, "shift+right"); key(sp, "right")
print("after b shift:", s.position(s.levels[1]), "b", s.trial_b)
key(sp, "m")
s.selected = s.levels[1]
# drag it to near the peak, then snap with c
click(sp, s.position(s.levels[1])); 
ev_x = 2536
draw(sp); x, y = sp.ax.transData.transform((ev_x, 10))
sp.canvas.callbacks.process("motion_notify_event", MouseEvent("motion_notify_event", sp.canvas, x, y, button=1))
sp.canvas.callbacks.process("button_release_event", MouseEvent("button_release_event", sp.canvas, x, y, button=1)); pump()
print("dragged to:", s.position(s.levels[1]))
key(sp, "c"); print("snapped:", s.position(s.levels[1]), w.statusBar().currentMessage())
key(sp, "enter")
print("fit after 2:", s.fit)
# now remaining levels should sit near their peaks; snap+record each
while s.selected is not None and not s.selected.is_recorded:
    key(sp, "c"); key(sp, "enter")
print("final fit:", s.fit)
print("residuals keV:", (s.residuals()*1000).round(1))
print("residual panel visible:", rp.isVisible())
w.grab().save(str(OUT / "2_all_recorded.png"))

# fit panel: select a point, move it, delete it
lvl = s.levels[3]
click(fp, lvl.recorded_channel, lvl.energy)
print("fit panel selected:", s.selected.energy)
key(fp, "shift+up"); print("energy now", lvl.energy, "modified", lvl.energy_modified)
key(fp, "shift+left"); print("channel now", lvl.recorded_channel)
w.grab().save(str(OUT / "3_moved_point.png"))
key(fp, "delete"); print("points:", s.fit.n_points)
# remove a level from spectrum panel
s.selected = s.levels[-1]; key(sp, "backspace"); print("levels text:", w.levels_edit.text())
# rebin + linear
w.bins_box.setValue(4); w.log_box.setChecked(False); pump()
w.grab().save(str(OUT / "4_rebinned.png"))
print(w.download_to(OUT))
