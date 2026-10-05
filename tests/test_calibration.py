"""Tests for the non-GUI parts. Run with:  python -m pytest tests"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calibrator.calibration import CalibrationSession, fit_line  # noqa: E402
from calibrator.peaks import peak_centroid  # noqa: E402
from calibrator.spectrum import Spectrum, SpectrumLoadError  # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_fit_recovers_line():
    ch = np.array([1000.0, 2000.0, 3000.0])
    f = fit_line(ch, 0.0025 * ch + 0.05)
    assert f.m == pytest.approx(0.0025)
    assert f.b == pytest.approx(0.05)
    assert f.m_err == pytest.approx(0.0, abs=1e-12)


def test_two_formats_give_same_spectrum():
    a = Spectrum.from_csv(EXAMPLES / "example_events.csv")
    b = Spectrum.from_csv(EXAMPLES / "example_histogram.csv")
    assert a.input_kind == "event list" and b.input_kind == "histogram"
    assert np.array_equal(a.channels, b.channels) and np.array_equal(a.counts, b.counts)


def test_rebin_conserves_counts():
    s = Spectrum.from_csv(EXAMPLES / "example_histogram.csv")
    for w in (1, 3, 8):
        edges, counts = s.binned(w)
        assert counts.sum() == s.total_counts
        assert edges[1] - edges[0] == w


def test_non_csv_rejected(tmp_path):
    p = tmp_path / "data.txt"
    p.write_text("1,2\n3,4\n")
    with pytest.raises(SpectrumLoadError, match="convert"):
        Spectrum.from_csv(p)


def test_centroid_finds_peak():
    s = Spectrum.from_csv(EXAMPLES / "example_histogram.csv")
    edges, counts = s.binned(1)
    c, ok = peak_centroid(edges, counts, 3748)   # click 7 channels off
    assert ok and abs(c - 3755.18) < 1.0


def test_workflow_anchor_shift_record_fit():
    s = CalibrationSession()
    s.max_channel = 8000
    s.set_levels(CalibrationSession.parse_levels("9.656, 5.958, 4.448"))
    s.anchor(3755.0)
    assert s.position(s.levels[0]) == pytest.approx(3755.0)
    s.record(s.levels[0])

    # b mode: shift all unrecorded lines; the recorded one must not move
    before = s.position(s.levels[1])
    s.shift_b(-5)                        # lines move right
    assert s.position(s.levels[1]) > before
    assert s.position(s.levels[0]) == 3755.0

    # m mode: move one line only
    other = s.position(s.levels[2])
    s.set_level_channel(s.levels[1], 2309.0)
    assert s.position(s.levels[2]) == pytest.approx(other)
    s.record(s.levels[1])
    assert s.fit is not None and s.fit.n_points == 2
    # with a fit, the unrecorded line lands where the fit predicts
    assert s.position(s.levels[2]) == pytest.approx((4.448 - s.fit.b) / s.fit.m)

    s.set_level_channel(s.levels[2], 1718.5)
    s.record(s.levels[2])
    assert s.fit.m == pytest.approx(0.002557, rel=0.01)
    assert len(s.residuals()) == 3

    # deleting a point keeps the level; removing a level drops it
    s.unrecord(s.levels[2])
    assert len(s.levels) == 3 and s.fit.n_points == 2
    s.remove_level(s.levels[1])
    assert s.levels_text() == "9.656, 4.448" and s.fit is None


def test_changing_levels_keeps_recorded_work():
    s = CalibrationSession()
    s.set_levels([9.656, 5.958])
    s.anchor(3755.0)
    s.record(s.levels[0])
    s.set_levels([9.656, 5.958, 4.448])
    assert s.levels[0].is_recorded
