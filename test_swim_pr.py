"""Focused SYNTHETIC tests for swim PR logic in performance_queries.py.

These use hand-built Garmin-shaped splits (not real Garmin data). Run:
    python test_swim_pr.py
"""
from datetime import datetime, timedelta, timezone

import performance_queries as pq

BASE = datetime(2026, 8, 4, 17, 0, 0, tzinfo=timezone.utc)


def L(stroke, dur, dist=25.0, strokes=9):
    """Active length."""
    return {"kind": "L", "stroke": stroke, "dur": dur, "dist": dist, "strokes": strokes}


def R(dur):
    """Rest record (Garmin: no distance, no stroke)."""
    return {"kind": "R", "dur": dur}


def BAD(dist=25.0):
    """Malformed length: has distance and stroke but no usable duration."""
    return {"kind": "BAD", "dist": dist}


def GAP(seconds):
    """Hidden gap: time passes and a lengthIndex is consumed, but NO record is emitted."""
    return {"kind": "GAP", "dur": seconds}


def build(items, with_index=True, with_time=True):
    """Build Garmin-style splits: rests are their own zero-distance lap."""
    clock = 0.0
    idx = 0
    laps = []
    cur = None

    def stamp(rec):
        if with_time:
            rec["startTimeGMT"] = (BASE + timedelta(seconds=int(clock))).strftime("%Y-%m-%dT%H:%M:%S.0")

    for it in items:
        idx += 1
        if it["kind"] == "GAP":
            clock += it["dur"]
            continue
        rec = {}
        if with_index:
            rec["lengthIndex"] = idx
        stamp(rec)
        if it["kind"] == "R":
            rec["duration"] = it["dur"]
            laps.append({"distance": 0.0, "duration": it["dur"], "lengthDTOs": [rec]})
            cur = None
        else:
            rec["distance"] = it["dist"]
            rec["swimStroke"] = it.get("stroke", "FREESTYLE")
            if it["kind"] == "L":
                rec["duration"] = it["dur"]
                rec["totalNumberOfStrokes"] = it["strokes"]
            if cur is None:
                cur = {"distance": 0.0, "duration": 0.0, "lengthDTOs": []}
                laps.append(cur)
            cur["lengthDTOs"].append(rec)
            cur["distance"] += it["dist"]
            cur["duration"] += it.get("dur", 0.0)
        clock += it.get("dur", 0.0)
    return {"lapDTOs": laps}


def free(n, dur=22.0):
    return [L("FREESTYLE", dur) for _ in range(n)]


RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))


def best(items, target, stroke=None, **kw):
    return pq._best_swim_distance(build(items, **kw), target, stroke)


# 1. 50m + 1 s rest + 50m must not make a 100m PR.
r = best(free(2) + [R(1.0)] + free(2), 100)
check("1s rest between 50m+50m -> no 100m PR", r is None, str(r))
check("  ...but each 50m side is still a valid 50m", best(free(2) + [R(1.0)] + free(2), 50) is not None)

# 2. Longer rest: same result.
r = best(free(2) + [R(45.0)] + free(2), 100)
check("45s rest between 50m+50m -> no 100m PR", r is None, str(r))

# 3. Invalid record between lengths breaks continuity.
r = best([L("FREESTYLE", 22.0), BAD(), L("FREESTYLE", 22.0)], 50)
check("malformed length between two lengths -> no 50m PR", r is None, str(r))
r = best([L("FREESTYLE", 22.0), L("FREESTYLE", 0.0), L("FREESTYLE", 22.0)], 50)
check("zero-duration length between two lengths -> no 50m PR", r is None, str(r))
r = best(free(2) + [GAP(5.0)] + free(2), 100)
check("dropped record (index+time gap, no rest row) -> no 100m PR", r is None, str(r))
r = best(free(2) + [GAP(5.0)] + free(2), 100, with_index=False)
check("dropped record detected by timestamps alone", r is None, str(r))
r = best(free(2) + [GAP(1.0)] + free(2), 100, with_time=False)
check("dropped record detected by lengthIndex alone", r is None, str(r))
r = best(free(4), 100, with_index=False, with_time=False)
check("no index and no timestamps -> continuity unprovable -> rejected", r is None, str(r))
r = best(free(4), 100, with_index=False)
check("timestamps alone can prove continuity", r is not None, str(r))

# 4. Partial lengths cannot form a full-distance PR.
r = best(free(3) + [L("FREESTYLE", 10.0, dist=10.0)], 85)
check("85m nominal from 3x25m + 10m partial -> rejected", r is None, str(r))
r = best([L("FREESTYLE", 11.0, dist=12.5), L("FREESTYLE", 11.0, dist=12.5)] + free(4), 25)
check("two 12.5m partials never make a 25m length", r is not None and abs(r["time_seconds"] - 22.0) < 1e-9, str(r))
r = best(free(3) + [L("FREESTYLE", 10.0, dist=10.0)] + free(1), 100)
check("partial length in the middle breaks 100m", r is None, str(r))

# 5. 6.05 s / 25 m zero-stroke drill is excluded (real-data pattern).
drill = L("DRILL", 6.053, strokes=0)
r = best([L("FREESTYLE", 18.34), R(13.712), drill], 50)
check("free 18.34 + rest + 6.05s drill -> no 50m PR (old bug)", r is None, str(r))
r = best([drill], 25)
check("6.05s zero-stroke drill alone -> no 25m PR", r is None, str(r))
r = best([L("FREESTYLE", 18.34), drill], 50)
check("drill adjacent to freestyle with NO rest still not joined", r is None, str(r))
r = best([L("FREESTYLE", 20.0, strokes=0), L("FREESTYLE", 20.0)], 50)
check("non-drill length with 0 strokes is malformed -> excluded", r is None, str(r))

# 6. Butterfly and freestyle never combine.
mixed = [L("BUTTERFLY", 26.0), L("FREESTYLE", 22.0)]
check("fly + free continuous -> no 50m", best(mixed, 50) is None)
two = [L("BUTTERFLY", 26.0), L("BUTTERFLY", 27.0), L("FREESTYLE", 22.0), L("FREESTYLE", 23.0)]
c = pq._swim_pr_candidates(build(two), 50)
check("no filter: best 50m is within ONE stroke", {x["stroke"] for x in c} == {"BUTTERFLY", "FREESTYLE"} and len(c) == 2, str(c))
r = best(two, 50)
check("no filter: fastest single-stroke 50m picked (free 45.0)", r is not None and abs(r["time_seconds"] - 45.0) < 1e-9, str(r))
r = best(two, 50, "fly")
check("stroke filter 'fly' honored (53.0)", r is not None and abs(r["time_seconds"] - 53.0) < 1e-9, str(r))
r = best(two, 50, "breast")
check("stroke filter with no matching stroke -> none", r is None, str(r))
r = best([L("FREESTYLE", 22.0)] * 2 + [L("BUTTERFLY", 26.0)] * 2, 100, "free")
check("filter 'free' cannot absorb adjacent butterfly", r is None, str(r))

# 7. Plausibility: 100m in 0.7 s rejected. ONE floor (36.0 s/100m) is applied to
#    individual lengths AND complete efforts, in meters / seconds.
r = best([L("FREESTYLE", 0.175)] * 4, 100)
check("100m in 0.7 s rejected", r is None, str(r))
check("_swim_pr_pace_ok(100 m, 0.7 s) is False", pq._swim_pr_pace_ok(100.0, 0.7) is False)
check("floor constant is 36.0 s/100m", pq._SWIM_PR_MIN_PACE_S_PER_100M == 36.0)
# individual lengths
check("length: 25 m in 9.0 s (36.0/100m) ok", pq._swim_pr_pace_ok(25.0, 9.0))
check("length: 25 m in 8.9 s (35.6/100m) rejected", not pq._swim_pr_pace_ok(25.0, 8.9))
check("length: 25 m in 6.053 s (24.2/100m) rejected", not pq._swim_pr_pace_ok(25.0, 6.053))
r = best([L("FREESTYLE", 9.0)] * 2, 50)
check("50m = 2 x 9.0 s lengths accepted at floor (18.0 s)", r is not None and abs(r["time_seconds"] - 18.0) < 1e-9, str(r))
r = best([L("FREESTYLE", 8.9)] * 2, 50)
check("50m = 2 x 8.9 s lengths rejected (implausible lengths are barriers)", r is None, str(r))
r = best([L("FREESTYLE", 9.0), L("FREESTYLE", 8.9), L("FREESTYLE", 9.0)], 50)
check("one implausible length splits an otherwise-valid run", r is None, str(r))
# complete efforts
for d, t, ok in ((50, 18.0, True), (50, 17.9, False), (100, 36.0, True), (100, 35.9, False), (400, 144.0, True), (400, 143.9, False)):
    check(f"effort: {d} m in {t} s -> {'ok' if ok else 'rejected'}", pq._swim_pr_pace_ok(float(d), t) is ok)
r = best([L("FREESTYLE", 9.0)] * 4, 100)
check("100m = 4 x 9.0 s accepted at floor (36.0 s)", r is not None and abs(r["time_seconds"] - 36.0) < 1e-9, str(r))
# property: no returned effort is ever faster than the floor
import random
random.seed(7)
worst = 1e9
for _ in range(200):
    seq = [L(random.choice(["FREESTYLE", "BUTTERFLY"]), random.uniform(5.0, 40.0)) for _ in range(random.randint(2, 24))]
    for tgt in (50, 100, 200, 250, 400):
        rr = best(seq, tgt)
        if rr:
            worst = min(worst, rr["pace_seconds_per_100m"])
check("property: 200 random swims, no returned PR pace below 36.0 s/100m", worst >= 36.0 - 1e-9, f"fastest returned {worst:.2f}")

# 8. Discoverability of 50/100/200/250/400 in one continuous 400 m effort.
items = free(16, 22.0)
for tgt, n in ((50, 2), (100, 4), (200, 8), (250, 10), (400, 16)):
    r = best(items, tgt)
    check(f"continuous {tgt}m found", r is not None and abs(r["time_seconds"] - 22.0 * n) < 1e-9, str(r))
varied = [L("FREESTYLE", d) for d in (30, 30, 24, 23, 24, 23, 30, 30)]
r = best(varied, 100)
check("fastest window chosen (middle 100m = 94.0)", r is not None and abs(r["time_seconds"] - 94.0) < 1e-9, str(r))
check("schema unchanged: only time_seconds/pace_seconds_per_100m", set(r) == {"time_seconds", "pace_seconds_per_100m"})
check("pace derived from exact target distance", abs(r["pace_seconds_per_100m"] - 94.0) < 1e-9)

# 9. Continuity: lengthIndex must NEVER override an observed timestamp gap (and
#    vice versa); rest / invalid records are hard barriers.
def raw(rows):
    """rows: (lengthIndex, start_offset_seconds, duration). One lap of 25 m freestyle lengths."""
    def stamp(off):
        whole = int(off // 1)
        frac = int(round((off - whole) * 10))
        return (BASE + timedelta(seconds=whole)).strftime("%Y-%m-%dT%H:%M:%S") + f".{frac}"
    lens = [{"lengthIndex": i, "startTimeGMT": stamp(s), "distance": 25.0, "duration": d,
             "swimStroke": "FREESTYLE", "totalNumberOfStrokes": 9} for i, s, d in rows]
    return {"lapDTOs": [{"distance": 25.0 * len(lens), "duration": sum(r[2] for r in rows), "lengthDTOs": lens}]}


def two(gap, i2=2):
    return raw([(1, 100.0, 22.0), (i2, 122.0 + gap, 22.0)])


def found50(splits):
    return pq._best_swim_distance(splits, 50) is not None


check("idx consecutive + 5.0 s timestamp gap -> REJECTED (index cannot override time)", not found50(two(5.0)))
check("idx consecutive + 1.5 s timestamp gap -> REJECTED", not found50(two(1.5)))
check("idx consecutive + 0.9 s gap (whole-second truncation noise) -> accepted", found50(two(0.9)))
check("idx consecutive + 0.9 s overlap (truncation noise) -> accepted", found50(two(-0.9)))
check("idx consecutive + 3.0 s overlap -> REJECTED", not found50(two(-3.0)))
check("timestamps aligned but lengthIndex skips 1->3 -> REJECTED (time cannot override index)", not found50(two(0.0, i2=3)))
check("timestamps aligned + consecutive lengthIndex -> accepted", found50(two(0.0)))

a_lap = raw([(1, 100.0, 22.0)])["lapDTOs"]
b_lap = raw([(2, 122.0, 22.0)])["lapDTOs"]
rest_empty = {"distance": 0.0, "duration": 0.5, "lengthDTOs": []}
rest_tagged = {"distance": 25.0, "duration": 0.5, "intensityType": "REST",
               "lengthDTOs": [{"lengthIndex": 99, "distance": 25.0, "duration": 22.0, "swimStroke": "FREESTYLE",
                               "totalNumberOfStrokes": 9, "startTimeGMT": "2026-08-04T17:00:00.0"}]}
check("rest lap (no length records) between index-consecutive, time-aligned lengths -> barrier",
      not found50({"lapDTOs": a_lap + [rest_empty] + b_lap}))
check("lap tagged REST is a barrier between lengths",
      not found50({"lapDTOs": a_lap + [rest_tagged] + b_lap}))
check("lap tagged REST: its own length records are not used as a PR",
      pq._best_swim_distance({"lapDTOs": [rest_tagged]}, 25) is None)

# 10. 25-yard pool (Garmin lengths of 22.86 m): meter-target PRs are impossible by design.
yd = [L("FREESTYLE", 20.0, dist=22.86) for _ in range(24)]
for tgt in (25, 50, 100, 200, 250, 400):
    check(f"25-yd pool lengths (22.86 m): {tgt} m PR not constructible", best(yd, tgt) is None)
r = best(yd, 91.44)
check("25-yd pool: exact 100 yd (91.44 m) effort IS constructible (reported in meters only)",
      r is not None and abs(r["time_seconds"] - 80.0) < 1e-9, str(r))

# Housekeeping edge cases.
check("empty splits -> None", pq._best_swim_distance({}, 50) is None)
check("None splits -> None", pq._best_swim_distance(None, 50) is None)
check("non-positive target -> None", pq._best_swim_distance(build(free(4)), 0) is None)
check("target not on a length boundary (60m) -> None", best(free(8), 60) is None)

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
