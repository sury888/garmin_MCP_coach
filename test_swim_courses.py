"""Synthetic tests for course-aware (yard / meter) swim PRs.

Hand-built Garmin-shaped splits and fake activities; no real Garmin data.
Run with:  uv run python test_swim_courses.py
"""
from datetime import datetime, timedelta, timezone

import performance_queries as pq

BASE = datetime(2026, 8, 4, 17, 0, 0, tzinfo=timezone.utc)
M25 = 25.0      # recorded length distance (meters) in a 25 m pool
YD25 = 22.86    # recorded length distance (meters) in a 25-yard pool
YARD_CM = 2286.000064509876   # pool_length Garmin actually stored for a 25-yard pool


def L(stroke, dur, dist, strokes=9):
    return {"kind": "L", "stroke": stroke, "dur": dur, "dist": dist, "strokes": strokes}


def R(dur):
    return {"kind": "R", "dur": dur}


def ylens(n, dur=20.0, stroke="FREESTYLE"):
    return [L(stroke, dur, YD25) for _ in range(n)]


def mlens(n, dur=22.0, stroke="FREESTYLE", dist=M25):
    return [L(stroke, dur, dist) for _ in range(n)]


def build(items):
    """Garmin-style splits: lengths carry lengthIndex + whole-second start times; rests are zero-distance laps."""
    clock, idx, laps, cur = 0.0, 0, [], None
    for it in items:
        idx += 1
        rec = {"lengthIndex": idx, "startTimeGMT": (BASE + timedelta(seconds=int(clock))).strftime("%Y-%m-%dT%H:%M:%S.0")}
        if it["kind"] == "R":
            rec["duration"] = it["dur"]
            laps.append({"distance": 0.0, "duration": it["dur"], "lengthDTOs": [rec]})
            cur = None
        else:
            rec.update(distance=it["dist"], duration=it["dur"], swimStroke=it["stroke"], totalNumberOfStrokes=it["strokes"])
            if cur is None:
                cur = {"distance": 0.0, "duration": 0.0, "lengthDTOs": []}
                laps.append(cur)
            cur["lengthDTOs"].append(rec)
            cur["distance"] += it["dist"]
            cur["duration"] += it["dur"]
        clock += it["dur"]
    return {"lapDTOs": laps}


def raw(rows, dist):
    """rows: (lengthIndex, start_offset_seconds, duration); one lap, freestyle lengths of `dist` meters."""
    def stamp(off):
        whole = int(off // 1)
        return (BASE + timedelta(seconds=whole)).strftime("%Y-%m-%dT%H:%M:%S") + f".{int(round((off - whole) * 10))}"
    lens = [{"lengthIndex": i, "startTimeGMT": stamp(s), "distance": dist, "duration": d,
             "swimStroke": "FREESTYLE", "totalNumberOfStrokes": 9} for i, s, d in rows]
    return {"lapDTOs": [{"distance": dist * len(lens), "duration": sum(r[2] for r in rows), "lengthDTOs": lens}]}


class Act:
    def __init__(self, aid, pool_length, name="Pool Swim"):
        self.activity_id = aid
        self.activity_date = "2026-08-04"
        self.activity_name = name
        self.activity_type = "lap_swimming"
        self.raw_data = None
        self.pool_length = pool_length


class Client:
    def __init__(self, splits):
        self.splits = splits

    def get_activity_splits(self, aid):
        return self.splits[aid]


def install(pairs):
    acts = [a for a, _ in pairs]
    pq._activity_query = lambda sport, window_days=30, period=None: acts
    pq.get_garmin_client = lambda: Client({a.activity_id: s for a, s in pairs})


RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


Y_COURSE = pq._swim_declared_course(YARD_CM)
M_COURSE = pq._swim_declared_course(2500.0)


def yeff(items, target, stroke=None):
    return pq._best_swim_effort(build(items), target, "yards", stroke, Y_COURSE)


def meff(items, target, stroke=None):
    return pq._best_swim_effort(build(items), target, "meters", stroke, M_COURSE)


def one(result):
    return result["results"][0]


# 1. Course classification from pool_length metadata (stored in centimeters)
for cm, unit, size in ((2500.0, "meters", 25.0), (5000.0, "meters", 50.0), (YARD_CM, "yards", 25.0), (4572.0, "yards", 50.0)):
    c = pq._swim_declared_course(cm)
    check(f"pool_length {cm:.1f} -> {size:g} {unit}", c is not None and c["unit"] == unit and c["pool_size"] == size)
for cm in (None, 0, -5, 1800.0, 3333.0, 2400.0, "abc"):
    check(f"pool_length {cm!r} -> missing/unsupported -> no course", pq._swim_declared_course(cm) is None)

# 2. Metadata is validated against the recorded length distances
c, why = pq._swim_course(2500.0, build(mlens(4)))
check("25 m metadata + 25.0 m lengths -> meters", c and c["unit"] == "meters" and why == "ok")
c, why = pq._swim_course(YARD_CM, build(ylens(4)))
check("25 yd metadata + 22.86 m lengths -> yards", c and c["unit"] == "yards" and why == "ok")
c, why = pq._swim_course(2286.0, build(mlens(4)))
check("yard metadata but 25.0 m lengths -> rejected", c is None and why == "pool_length_conflicts_with_lengths", why)
c, why = pq._swim_course(2500.0, build(ylens(4)))
check("meter metadata but 22.86 m lengths -> rejected", c is None and why == "pool_length_conflicts_with_lengths", why)
c, why = pq._swim_course(None, build(ylens(8)))
check("NO metadata + 22.86 m lengths is NOT assumed to be yards", c is None and why == "no_pool_length", why)
c, why = pq._swim_course(1800.0, build(mlens(4)))
check("unsupported pool size -> no course", c is None and why == "unsupported_pool_length", why)
c, why = pq._swim_course(2500.0, build([R(10.0)]))
check("metadata but no length records -> no course", c is None and why == "no_length_records", why)

# 3. Exact target construction, in the course's own unit
splits_y = build(ylens(70, 20.0))
for tgt in pq.SWIM_PR_TARGETS["yards"]:
    e = pq._best_swim_effort(splits_y, tgt, "yards", None, Y_COURSE)
    n = tgt // 25
    check(f"yard pool: {tgt} yd constructible -> {20.0 * n:g} s, 80.0 s/100yd",
          e and abs(e["time_seconds"] - 20.0 * n) < 1e-6 and abs(e["pace_seconds_per_100_unit"] - 80.0) < 1e-6, str(e))
splits_m = build(mlens(160, 22.0))
for tgt in pq.SWIM_PR_TARGETS["meters"]:
    e = pq._best_swim_effort(splits_m, tgt, "meters", None, M_COURSE)
    n = tgt // 25
    check(f"meter pool: {tgt} m constructible -> {22.0 * n:g} s, 88.0 s/100m",
          e and abs(e["time_seconds"] - 22.0 * n) < 1e-6 and abs(e["pace_seconds_per_100_unit"] - 88.0) < 1e-6, str(e))
# Garmin may round recorded length distances by a few centimeters. Course
# metadata is validated with a 5 cm tolerance, so exact targets must be based
# on complete validated pool lengths rather than accumulating that rounding.
s_y_round = build(ylens(4, 20.0))
for lap in s_y_round["lapDTOs"]:
    for length in lap.get("lengthDTOs", []):
        length["distance"] = 22.90
c, why = pq._swim_course(YARD_CM, s_y_round)
e = pq._best_swim_effort(s_y_round, 100, "yards", None, c) if c else None
check("rounded 25 yd length distances still construct exact 100 yd",
      c is not None and why == "ok" and e is not None and abs(e["time_seconds"] - 80.0) < 1e-9, str((why, e)))

s_m_round = build(mlens(4, 22.0, dist=25.04))
c, why = pq._swim_course(2500.0, s_m_round)
e = pq._best_swim_effort(s_m_round, 100, "meters", None, c) if c else None
check("rounded 25 m length distances still construct exact 100 m",
      c is not None and why == "ok" and e is not None and abs(e["time_seconds"] - 88.0) < 1e-9, str((why, e)))


# A continuous 200 m swim must also yield the shorter 100 m effort.
long_swim = build(mlens(8, 22.0, dist=25.04))
c_long, why_long = pq._swim_course(2500.0, long_swim)
e_short = (
    pq._best_swim_effort(long_swim, 100, "meters", None, c_long)
    if c_long else None
)
check(
    "shorter 100 m PR is found inside a continuous 200 m swim",
    c_long is not None
    and why_long == "ok"
    and e_short is not None
    and abs(e_short["time_seconds"] - 88.0) < 1e-9,
    str((why_long, e_short)),
)


check("25 yd pool: 30 yd is not on a length boundary", pq._best_swim_effort(splits_y, 30, "yards", None, Y_COURSE) is None)
check("25 m pool: 100 yd (91.44 m) is not constructible as a yard effort",
      pq._best_swim_effort(build(mlens(8)), 100, "yards", None, M_COURSE) is None)
c50 = pq._swim_declared_course(5000.0)
splits_50 = build(mlens(8, 45.0, dist=50.0))
check("50 m pool: 25 m not constructible", pq._best_swim_effort(splits_50, 25, "meters", None, c50) is None)
e = pq._best_swim_effort(splits_50, 100, "meters", None, c50)
check("50 m pool: 100 m = 2 lengths", e and abs(e["time_seconds"] - 90.0) < 1e-9, str(e))

# 4. Plausibility uses the correct unit and distance (floor is judged on meters)
e = yeff([L("FREESTYLE", 8.3, YD25) for _ in range(4)], 100)
check("100 yd as 4 x 8.3 s (33.2 s/100yd = 36.3 s/100m) accepted: not judged as 33.2 s/100m-unit",
      e and abs(e["time_seconds"] - 33.2) < 1e-9, str(e))
check("100 yd as 4 x 8.2 s (35.9 s/100m) rejected", yeff([L("FREESTYLE", 8.2, YD25) for _ in range(4)], 100) is None)
check("100 yd in 0.7 s rejected", yeff([L("FREESTYLE", 0.175, YD25) for _ in range(4)], 100) is None)
check("meters: 25 m in 9.0 s accepted, 8.9 s rejected",
      meff([L("FREESTYLE", 9.0, M25)], 25) is not None and meff([L("FREESTYLE", 8.9, M25)], 25) is None)

# 5. A yard effort is never a meter effort, and units are never compared
check("yard splits: 100 m target not constructible", pq._swim_pr_candidates(build(ylens(8)), 100, None, "meters") == [])
A, B = Act(1, YARD_CM), Act(2, 2500.0)
sA, sB = build(ylens(8, 20.0)), build(mlens(8, 22.0))
install([(A, sA), (B, sB)])
ry = one(pq.get_best_swim_performance("yards", 100))
check("yards/100 -> yard-pool activity, 80.0 s", ry["found"] and ry["activity_id"] == 1 and ry["time_seconds"] == 80.0, str(ry))
check("yards/100 reports distance_yards + pace_seconds_per_100yd only",
      ry["distance_yards"] == 100 and ry["pace_seconds_per_100yd"] == 80.0 and ry["pace_per_100yd"] == "1:20/100yd"
      and not any(k in ry for k in ("distance_meters", "distance_m", "pace_seconds_per_100m", "pace_per_100m")), str(sorted(ry)))
rm = one(pq.get_best_swim_performance("meters", 100))
check("meters/100 -> meter-pool activity, 88.0 s", rm["found"] and rm["activity_id"] == 2 and rm["time_seconds"] == 88.0, str(rm))
check("meters/100 reports distance_meters + pace_seconds_per_100m only",
      rm["distance_meters"] == 100 and rm["pace_seconds_per_100m"] == 88.0 and rm["pace_per_100m"] == "1:28/100m"
      and not any(k in rm for k in ("distance_yards", "pace_seconds_per_100yd", "pace_per_100yd")), str(sorted(rm)))
legacy = pq.get_best_performance("swim", 100, window_days=30)
LEGACY_KEYS = {"sport", "target", "target_units", "window_days", "period", "period_start", "period_end", "found",
               "activity_id", "date", "activity_name", "surface", "pace_source", "distance_m", "time_seconds",
               "pace_per_100m", "stroke_filter"}
check("legacy get_best_performance(swim, 100): meter activity, schema unchanged",
      legacy["found"] and legacy["activity_id"] == 2 and legacy["time_seconds"] == 88.0 and set(legacy) == LEGACY_KEYS, str(sorted(legacy)))
check("legacy pace is still /100m", legacy["pace_per_100m"] == "1:28/100m" and legacy["target_units"] == "meters")

install([(Act(1, YARD_CM), build(ylens(8, 15.0))), (Act(2, 2500.0), build(mlens(8, 22.0)))])
check("yard 100 yd in 60 s does not beat the 100 m query (88 s still wins)",
      one(pq.get_best_swim_performance("meters", 100))["activity_id"] == 2 and
      pq.get_best_performance("swim", 100, window_days=30)["activity_id"] == 2)
install([(Act(1, YARD_CM), build(ylens(8, 22.5))), (Act(2, 2500.0), build(mlens(8, 22.0)))])
r = one(pq.get_best_swim_performance("yards", 100))
check("meter 100 m in 88 s does not beat a slower 90 s 100 yd on the yard query",
      r["activity_id"] == 1 and r["time_seconds"] == 90.0, str(r))

install([(A, sA)])
check("YARD-ONLY data: legacy 100 m query finds nothing (a 100 yd PR is never a 100 m PR)",
      pq.get_best_performance("swim", 100, window_days=30)["found"] is False)
check("YARD-ONLY data: legacy query for 91.44 m (= 100 yd) finds nothing",
      pq.get_best_performance("swim", 91.44, window_days=30)["found"] is False)
check("YARD-ONLY data: strict meters/100 finds nothing", not one(pq.get_best_swim_performance("meters", 100))["found"])
check("YARD-ONLY data: strict meters/91.44 finds nothing", not one(pq.get_best_swim_performance("meters", 91.44))["found"])
r = pq.get_best_swim_performance("meters", 100)
check("yard session is counted as excluded (other course unit), not silently dropped",
      r["activities_excluded"]["other_course_unit"] == 1 and r["activities_in_course"] == 0, str(r["activities_excluded"]))
install([(B, sB)])
r = pq.get_best_swim_performance("yards", 100)
check("METER-ONLY data: yards/100 finds nothing", not one(r)["found"] and r["activities_excluded"]["other_course_unit"] == 1)

# 6. Incorrect course classification
install([(Act(3, None), build(ylens(8, 20.0)))])
r = pq.get_best_swim_performance("yards", 100)
check("no metadata + 22.86 m lengths: not classified as yards",
      not one(r)["found"] and r["activities_excluded"]["unclassified"] == {"no_pool_length": 1}, str(r["activities_excluded"]))
check("...and not a meter PR (strict query, legacy 100 m, legacy 91.44 m)",
      not one(pq.get_best_swim_performance("meters", 91.44))["found"]
      and not pq.get_best_performance("swim", 100, window_days=30)["found"]
      and not pq.get_best_performance("swim", 91.44, window_days=30)["found"])
install([(Act(4, 2286.0), build(mlens(8, 22.0)))])
r = pq.get_best_swim_performance("yards", 100)
check("yard metadata but 25.0 m lengths: excluded from yards, meters and legacy",
      not one(r)["found"] and r["activities_excluded"]["unclassified"] == {"pool_length_conflicts_with_lengths": 1}
      and not one(pq.get_best_swim_performance("meters", 100))["found"]
      and not pq.get_best_performance("swim", 100, window_days=30)["found"])
install([(Act(5, 2500.0), build(ylens(8, 20.0)))])
check("meter metadata but 22.86 m lengths: excluded everywhere",
      not one(pq.get_best_swim_performance("yards", 100))["found"]
      and not one(pq.get_best_swim_performance("meters", 91.44))["found"]
      and not pq.get_best_performance("swim", 91.44, window_days=30)["found"])
install([(Act(6, None), build(mlens(8, 22.0)))])
check("legacy compat: no metadata + standard 25.0 m lengths still counts for the legacy meter query",
      pq.get_best_performance("swim", 100, window_days=30)["found"] is True)
check("...but the strict queries require verified metadata",
      not one(pq.get_best_swim_performance("meters", 100))["found"] and not one(pq.get_best_swim_performance("yards", 100))["found"])

# 7. Stroke handling in yards
mix = [L("BUTTERFLY", 22.0, YD25), L("BUTTERFLY", 23.0, YD25), L("FREESTYLE", 20.0, YD25), L("FREESTYLE", 21.0, YD25)]
e = yeff(mix, 50)
check("yards, no filter: best 50 yd is single-stroke freestyle (41.0 s)", e and e["stroke"] == "FREESTYLE" and abs(e["time_seconds"] - 41.0) < 1e-9, str(e))
e = yeff(mix, 50, "fly")
check("yards, filter fly: 45.0 s butterfly", e and e["stroke"] == "BUTTERFLY" and abs(e["time_seconds"] - 45.0) < 1e-9, str(e))
check("yards, filter breast: nothing", yeff(mix, 50, "breast") is None)
check("yards: fly + free never combine into a 50 yd", yeff([L("BUTTERFLY", 22.0, YD25), L("FREESTYLE", 20.0, YD25)], 50) is None)
check("yards: filter free cannot absorb adjacent fly", yeff(ylens(2) + ylens(2, 22.0, "BUTTERFLY"), 100, "free") is None)
install([(A, build(mix))])
r = one(pq.get_best_swim_performance("yards", 50, swim_stroke="fly"))
check("tool: stroke filter honored and echoed", r["found"] and r["stroke"] == "BUTTERFLY" and r["stroke_filter"] == "fly", str(r))

# 8. Rest / gap / drill / partial handling in yards
check("yards: 2x25 + 1 s rest + 2x25 -> no 100 yd", yeff(ylens(2) + [R(1.0)] + ylens(2), 100) is None)
check("...but 50 yd is found on each side", yeff(ylens(2) + [R(1.0)] + ylens(2), 50) is not None)
check("yards: longer rest (45 s) -> no 100 yd", yeff(ylens(2) + [R(45.0)] + ylens(2), 100) is None)
check("yards: malformed length between lengths breaks continuity",
      yeff([L("FREESTYLE", 20.0, YD25), L("FREESTYLE", 0.0, YD25), L("FREESTYLE", 20.0, YD25)], 50) is None)
check("yards: zero-stroke drill length excluded (and not joined to freestyle)",
      yeff([L("FREESTYLE", 18.0, YD25), R(13.7), L("DRILL", 6.05, YD25, strokes=0)], 50) is None
      and yeff([L("DRILL", 6.05, YD25, strokes=0)], 25) is None)
check("yards: partial length cannot complete a distance", yeff(ylens(3) + [L("FREESTYLE", 10.0, YD25 / 2)], 87.5) is None)
check("yards: a length recorded as 25.0 m in a yard pool is non-standard -> barrier",
      yeff(ylens(2) + [L("FREESTYLE", 20.0, M25)] + ylens(2), 100) is None)
for gap, i2, name, expect in ((5.0, 2, "5 s timestamp gap with consecutive lengthIndex", False),
                              (0.9, 2, "0.9 s timestamp noise with consecutive lengthIndex", True),
                              (0.0, 3, "aligned timestamps but lengthIndex skips", False)):
    s = raw([(1, 100.0, 20.0), (i2, 120.0 + gap, 20.0)], YD25)
    e = pq._best_swim_effort(s, 50, "yards", None, Y_COURSE)
    check(f"yards: {name} -> {'accepted' if expect else 'rejected'}", (e is not None) is expect, str(e))

# 9. Response shape, units, defaults
install([(A, build(ylens(70, 20.0))), (B, sB)])
r = pq.get_best_swim_performance("YD")
check("unit aliases accepted (YD -> yards)", r.get("course_unit") == "yards" and len(r["results"]) == 9, str(r.get("error")))
check("default yard targets are the common set, all constructible with 70 lengths",
      [x["target"] for x in r["results"]] == list(pq.SWIM_PR_TARGETS["yards"]) and all(x["found"] for x in r["results"]))
check("top-level keys",
      set(r) == {"sport", "course_unit", "target_units", "window_days", "period", "period_start", "period_end", "found",
                 "activities_considered", "activities_in_course", "activities_excluded", "results"}, str(sorted(r)))
check("found-row keys (yards)",
      set(r["results"][0]) == {"target", "found", "activity_id", "date", "activity_name", "surface", "pace_source", "pool_length",
                               "pool_length_unit", "distance_yards", "time_seconds", "pace_seconds_per_100yd", "pace_per_100yd",
                               "stroke", "stroke_filter"}, str(sorted(r["results"][0])))
check("pool_length reported in yards", r["results"][0]["pool_length"] == 25.0 and r["results"][0]["pool_length_unit"] == "yards")
install([(A, build(ylens(8, 20.0)))])
r = pq.get_best_swim_performance("yards")
check("only constructible targets are found (8 lengths = 200 yd)",
      [x["target"] for x in r["results"] if x["found"]] == [25, 50, 100, 200] and r["found"] is True, str([x["target"] for x in r["results"] if x["found"]]))
install([(B, build(mlens(160, 22.0)))])
r = pq.get_best_swim_performance("meters")
check("default meter targets preserved (25..3800, incl. 250/1500/1900)",
      [x["target"] for x in r["results"]] == [25, 50, 100, 200, 250, 400, 800, 1000, 1500, 1900, 3800] and all(x["found"] for x in r["results"]))
check("found-row keys (meters)",
      set(r["results"][0]) == {"target", "found", "activity_id", "date", "activity_name", "surface", "pace_source", "pool_length",
                               "pool_length_unit", "distance_meters", "time_seconds", "pace_seconds_per_100m", "pace_per_100m",
                               "stroke", "stroke_filter"})
check("bad unit -> error", "error" in pq.get_best_swim_performance("furlongs", 100))
check("bad target -> error", "error" in pq.get_best_swim_performance("yards", 0))
install([])
r = pq.get_best_swim_performance("yards", 100)
check("no activities -> found False, empty results", r["found"] is False and r["results"] == [])
check("pace label units", pq._swim_pace_label(80.0, "yards") == "1:20/100yd" and pq._swim_pace_label(88.0, "meters") == "1:28/100m")

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
