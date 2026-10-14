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

# 7. Plausibility: 100m in 0.7 s rejected; floor applied consistently.
r = best([L("FREESTYLE", 0.175)] * 4, 100)
check("100m in 0.7 s rejected", r is None, str(r))
check("_swim_pr_pace_ok(100 m, 0.7 s) is False", pq._swim_pr_pace_ok(100.0, 0.7) is False)
check("30.0 s/100m exactly is allowed (100 m in 30.0 s)", pq._swim_pr_pace_ok(100.0, 30.0) is True)
check("29.9 s/100m rejected (100 m in 29.9 s)", pq._swim_pr_pace_ok(100.0, 29.9) is False)
check("same floor per length: 25 m in 7.5 s ok, 7.4 s not", pq._swim_pr_pace_ok(25.0, 7.5) and not pq._swim_pr_pace_ok(25.0, 7.4))
r = best([L("FREESTYLE", 7.4)] * 4, 100)
check("4 x 25m in 7.4 s each (29.6 s/100m) rejected", r is None, str(r))
r = best([L("FREESTYLE", 7.5)] * 4, 100)
check("4 x 25m in 7.5 s each (30.0 s/100m) accepted at the floor", r is not None and abs(r["time_seconds"] - 30.0) < 1e-9, str(r))

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

# Housekeeping edge cases.
check("empty splits -> None", pq._best_swim_distance({}, 50) is None)
check("None splits -> None", pq._best_swim_distance(None, 50) is None)
check("non-positive target -> None", pq._best_swim_distance(build(free(4)), 0) is None)
check("target not on a length boundary (60m) -> None", best(free(8), 60) is None)

failed = [n for n, ok in RESULTS if not ok]
print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
raise SystemExit(1 if failed else 0)
