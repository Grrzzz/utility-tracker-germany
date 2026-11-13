import importlib.util
from datetime import date

spec = importlib.util.spec_from_file_location(
    "calc", "custom_components/utility_tracker_germany/calc.py"
)
c = importlib.util.module_from_spec(spec)
import sys

sys.modules["calc"] = c
spec.loader.exec_module(c)

s = date(2026, 1, 1)
per = c.build_periods(s, 1000, 0.30, 60, 100, None)
mid = c.calc_ist(s, date(2026, 12, 31), 1500, "kWh", per)
after = c.calc_ist(s, date(2027, 6, 1), 2500, "kWh", per)
assert after > mid
end_r = c.calc_ist(s, date(2027, 6, 1), 2500, "kWh", per, 0.0, 12, 1600)
assert abs(end_r - (600 * 0.30 + 60)) < 0.02, end_r
assert c.calc_ist(s, date(2028, 1, 1), 9999, "kWh", per, 0.0, 12, 1600) == end_r
assert c.calc_ist(s, date(2026, 6, 1), 1200, "kWh", per, 0.0, 12, 1600) < end_r

f = c.calc_forecast(s, date(2026, 7, 2), 1000 + 182 * 2, "kWh", per)
assert f and abs(f["daily_consumption"] - 2) < 0.01, f
exp = 365 * 2 * 0.30 + 60
assert abs(f["ist_forecast"] - exp) < 2, (f, exp)
assert abs(f["accuracy"] - exp / 1200 * 100) < 0.5, f
assert c.calc_forecast(s, date(2026, 1, 5), 1010, "kWh", per) is None
fz = c.calc_forecast(s, date(2028, 1, 1), 9999, "kWh", per, 0, 0, 12, 1600)
assert abs(fz["ist_forecast"] - 240) < 0.02, fz
print("ok")
