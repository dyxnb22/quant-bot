from datetime import date

from quantlab.windows import Window, add_months, build_windows


def test_add_months_normal():
    assert add_months(date(2023, 1, 1), 12) == date(2024, 1, 1)
    assert add_months(date(2023, 11, 15), 3) == date(2024, 2, 15)


def test_add_months_clamps_month_end():
    assert add_months(date(2023, 1, 31), 1) == date(2023, 2, 28)


def test_build_windows_alignment():
    ws = build_windows(date(2023, 1, 1), date(2026, 8, 1), 12, 3, 3)
    assert ws[0].is_timerange == "20230101-20240101"
    assert ws[0].oos_timerange == "20240101-20240401"
    assert ws[1].is_start == date(2023, 4, 1)
    assert all(w.oos_end <= date(2026, 8, 1) for w in ws)
    assert len(ws) == 10


def test_build_windows_empty_when_range_too_short():
    assert build_windows(date(2026, 1, 1), date(2026, 6, 1), 12, 3, 3) == []
