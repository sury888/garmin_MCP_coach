"""Table-oriented athlete-specific coaching analytics.

The module is deliberately conservative: it compares today's Garmin-native
laps with historical records that actually exist in the local database and
never invents interval boundaries.
"""
from __future__ import annotations

from datetime import date
import json
from statistics import mean, median, pstdev

from database import get_session, Activity, PerformanceRecord, ActivityAnnotation

INTERVAL_BANDS = {
    "bike": {"short": (0, 360), "medium": (360, 720), "long": (720, 1260), "ultra": (1260, float("inf"))},
    "run": {"short": (0, 240), "medium": (240, 600), "long": (600, 1320), "ultra": (1320, float("inf"))},
}


def classify_interval(sport, duration_seconds):
    if duration_seconds is None:
        return None
    d=float(duration_seconds)
    bands=INTERVAL_BANDS.get(sport)
    if not bands:
        return None
    for label,(lo,hi) in bands.items():
        if d > lo and d <= hi:
            return label
    # 0-second/very short Garmin laps are short by convention.
    return "short" if d <= 360 and sport == "bike" else "short" if d <= 240 and sport == "run" else None


def _cv(values):
    v=[float(x) for x in values if x is not None]
    if len(v)<2 or mean(v)==0: return None
    return round(pstdev(v)/abs(mean(v))*100,2)


def _parse_json(value):
    try: return json.loads(value) if value else {}
    except Exception: return {}


def _extract_note_fields(raw):
    """Find likely Garmin note/description fields without assuming one API shape."""
    found=[]
    def walk(obj,path=""):
        if isinstance(obj,dict):
            for k,v in obj.items():
                lk=str(k).lower()
                if lk in {"note","notes","activitynote","activitynotes","description","activitydescription"} and isinstance(v,str) and v.strip():
                    found.append({"path":f"{path}.{k}".strip('.'),"value":v})
                walk(v,f"{path}.{k}".strip('.'))
        elif isinstance(obj,list):
            for i,v in enumerate(obj): walk(v,f"{path}[{i}]")
    walk(raw)
    # de-duplicate values
    out=[]; seen=set()
    for x in found:
        if x["value"] not in seen:
            out.append(x); seen.add(x["value"])
    return out


def _position_from_note(note):
    if not note: return None
    n=note.lower()
    if any(x in n for x in ("non-aero","not aero","upright","base bar","hoods")): return "non_aero"
    if any(x in n for x in ("aero","tt position","aerobars","aero bars")): return "aero"
    return None


def get_annotation(activity_id):
    s=get_session()
    try:
        row=s.query(ActivityAnnotation).filter_by(activity_id=activity_id).first()
        if not row: return None
        return {"activity_id": activity_id, "note": row.note,
                "bike_position": row.bike_position,
                "interval_positions": _parse_json(row.interval_positions),
                "swim_subtype": row.swim_subtype,
                "swim_set_description": row.swim_set_description,
                "swim_lap_indices": _parse_json(row.swim_lap_indices),
                "manual_treadmill_intervals": _parse_json(row.manual_treadmill_intervals),
                "source": row.source, "updated_at": row.updated_at}
    finally: s.close()


def save_annotation(activity_id,note=None,bike_position=None,interval_positions=None,swim_subtype=None,swim_set_description=None,swim_lap_indices=None,source="user"):
    from datetime import datetime
    s=get_session()
    try:
        row=s.query(ActivityAnnotation).filter_by(activity_id=activity_id).first()
        if not row:
            row=ActivityAnnotation(activity_id=activity_id); s.add(row)
        row.note=note
        row.bike_position=bike_position or _position_from_note(note)
        row.interval_positions=json.dumps(interval_positions or {})
        row.swim_subtype=swim_subtype
        row.swim_set_description=swim_set_description
        row.swim_lap_indices=json.dumps(swim_lap_indices or [])
        row.source=source
        row.updated_at=datetime.now().isoformat()
        s.commit()
        # Build the response from the same committed session. Opening a
        # second session here can block behind SQLite locks when another MCP
        # request is syncing or reading the database.
        return {"activity_id": activity_id, "note": row.note,
                "bike_position": row.bike_position,
                "interval_positions": _parse_json(row.interval_positions),
                "swim_subtype": row.swim_subtype,
                "swim_set_description": row.swim_set_description,
                "swim_lap_indices": _parse_json(row.swim_lap_indices),
                "manual_treadmill_intervals": _parse_json(row.manual_treadmill_intervals),
                "source": row.source, "updated_at": row.updated_at}
    finally:
        s.rollback()
        s.close()



def _parse_pace_sec_per_mile(value):
    """Parse common manual pace formats into seconds/mile when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text=str(value).strip().lower().replace("/mile", "").replace("/mi", "").strip()
    if ":" in text:
        try:
            m, sec = text.split(":", 1)
            return float(m) * 60 + float(sec)
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _recovery_analysis(interval):
    """Calculate recovery-response metrics from manually supplied interval data.

    Supported keys are intentionally flexible so Claude can pass natural
    interval data without requiring a rigid schema.
    """
    if not isinstance(interval, dict):
        return {}

    def first(*keys):
        for key in keys:
            if key in interval and interval[key] is not None:
                return interval[key]
        return None

    work_max_hr=first("interval_max_hr", "work_max_hr", "max_hr")
    recovery_start_hr=first("recovery_start_hr", "recovery_hr_start", "recovery_hr")
    recovery_min_hr=first("recovery_min_hr", "recovery_hr_min", "recovery_low_hr")
    recovery_duration=first("recovery_duration_seconds", "recovery_seconds", "recovery_duration")
    work_cadence=first("interval_cadence", "work_cadence", "cadence")
    recovery_cadence=first("recovery_cadence", "recovery_spm", "recovery_cadence_spm")
    work_pace=first("interval_pace_sec_per_mile", "work_pace_sec_per_mile", "pace_sec_per_mile", "interval_pace", "work_pace", "pace")
    recovery_pace=first("recovery_pace_sec_per_mile", "recovery_pace")

    out={}
    try:
        if work_max_hr is not None and recovery_min_hr is not None:
            out["hr_drop_from_interval_max_bpm"]=round(float(work_max_hr)-float(recovery_min_hr),2)
        if recovery_start_hr is not None and recovery_min_hr is not None:
            out["hr_drop_from_recovery_start_bpm"]=round(float(recovery_start_hr)-float(recovery_min_hr),2)
        if recovery_duration is not None and recovery_start_hr is not None and recovery_min_hr is not None and float(recovery_duration)>0:
            out["hr_recovery_rate_bpm_per_min"]=round((float(recovery_start_hr)-float(recovery_min_hr))/(float(recovery_duration)/60.0),2)
        if work_cadence is not None and recovery_cadence is not None:
            out["cadence_drop_spm"]=round(float(work_cadence)-float(recovery_cadence),2)
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    wp=_parse_pace_sec_per_mile(work_pace)
    rp=_parse_pace_sec_per_mile(recovery_pace)
    if wp is not None and rp is not None:
        out["pace_slowdown_sec_per_mile"]=round(rp-wp,2)

    return out


def save_treadmill_intervals(activity_id, intervals):
    """Persist manual treadmill intervals and derived work-to-recovery metrics."""
    from datetime import datetime
    normalized=[]
    for interval in intervals or []:
        item=dict(interval) if isinstance(interval, dict) else {"value": interval}
        recovery=_recovery_analysis(item)
        if recovery:
            item["recovery_analysis"]=recovery
        normalized.append(item)

    s=get_session()
    try:
        row=s.query(ActivityAnnotation).filter_by(activity_id=activity_id).first()
        if not row:
            row=ActivityAnnotation(activity_id=activity_id, source="user")
            s.add(row)
        row.manual_treadmill_intervals=json.dumps(normalized)
        row.source="user"
        row.updated_at=datetime.now().isoformat()
        s.commit()
        return {
            "activity_id": activity_id,
            "manual_treadmill_intervals": _parse_json(row.manual_treadmill_intervals),
            "source": row.source,
            "updated_at": row.updated_at,
        }
    finally:
        s.rollback()
        s.close()


def get_treadmill_intervals(activity_id):
    s=get_session()
    try:
        row=s.query(ActivityAnnotation).filter_by(activity_id=activity_id).first()
        if not row:
            return {"activity_id": activity_id, "manual_treadmill_intervals": [], "found": False}
        return {
            "activity_id": activity_id,
            "manual_treadmill_intervals": _parse_json(row.manual_treadmill_intervals),
            "source": row.source,
            "updated_at": row.updated_at,
            "found": bool(row.manual_treadmill_intervals),
        }
    finally:
        s.close()

def _historical_benchmarks(sport, band, window_days=3650):
    lo,hi=INTERVAL_BANDS[sport][band]
    start=date.today().fromordinal(date.today().toordinal()-window_days+1)
    s=get_session()
    try:
        rows=(s.query(PerformanceRecord,Activity.activity_date,Activity.activity_name)
              .join(Activity,Activity.activity_id==PerformanceRecord.activity_id)
              .filter(PerformanceRecord.sport==sport,PerformanceRecord.metric_type=="peak",
                      Activity.activity_date>=start,PerformanceRecord.duration_seconds>lo,
                      PerformanceRecord.duration_seconds<=hi).all())
        valid=[]
        for r,d,n in rows:
            if r.primary_value is None: continue
            if sport=="swim":
                if r.primary_value<20 or r.primary_value>300: continue
                extra=_parse_json(r.metric_json)
                stroke=str(extra.get("stroke_type") or extra.get("swim_stroke") or "").upper()
                strokes=extra.get("strokes")
                if stroke=="DRILL" and strokes in (0,0.0,None): continue
            extra=_parse_json(r.metric_json)
            valid.append({"record":r,"date":d,"name":n,"extra":extra})
        if not valid: return None
        primary=[x["record"].primary_value for x in valid]
        hrs=[x["record"].avg_hr for x in valid if x["record"].avg_hr is not None]
        cad=[x["record"].cadence for x in valid if x["record"].cadence is not None]
        best=min(valid,key=lambda x:x["record"].primary_value) if sport in ("run","swim") else max(valid,key=lambda x:x["record"].primary_value)
        result={
            "band":band,"sample_count":len(valid),
            "typical_primary":round(median(primary),2),"mean_primary":round(mean(primary),2),"cv_primary_percent":_cv(primary),
            "best_primary":round(best["record"].primary_value,2),"best_date":str(best["date"]),"best_activity":best["name"],
            "typical_hr":round(median(hrs),1) if hrs else None,
            "typical_cadence":round(median(cad),1) if cad else None,
        }
        if sport=="bike":
            by_pos={"aero":[],"non_aero":[]}
            for x in valid:
                ann=s.query(ActivityAnnotation).filter_by(activity_id=x["record"].activity_id).first()
                pos=ann.bike_position if ann else None
                if pos in by_pos: by_pos[pos].append(x)
            result["position_benchmarks"]={}
            for pos,items in by_pos.items():
                if not items: continue
                pv=[x["record"].primary_value for x in items]
                ph=[x["record"].avg_hr for x in items if x["record"].avg_hr is not None]
                result["position_benchmarks"][pos]={"sample_count":len(items),"typical_power_w":round(median(pv),1),"best_power_w":round(max(pv),1),"typical_hr":round(median(ph),1) if ph else None}
        return result
    finally: s.close()


def _lap_table(session, sport, annotation_by_activity):
    rows=[]
    for lap in session["lap_analysis"]["laps"]:
        d=lap.get("duration_seconds")
        band=classify_interval(sport,d) if sport in INTERVAL_BANDS else None
        ann=annotation_by_activity.get(session["activity_id"]) or {}
        position=ann.get("bike_position") if sport=="bike" else None
        positions=ann.get("interval_positions") or {}
        if sport=="bike" and str(lap.get("lap_index")) in positions:
            position=positions[str(lap["lap_index"])]
        rows.append({
            "lap":lap.get("lap_index"),"classification":band,"duration_sec":round(d,1) if d is not None else None,
            "duration":"%d:%04.1f"%(int(d//60),d%60) if d is not None else None,
            "position":position,
            "power_w":lap.get("avg_power"),"pace_sec_per_km":lap.get("pace_seconds_per_km"),
            "pace_sec_per_100m":lap.get("pace_seconds_per_100m"),"hr":lap.get("avg_hr"),
            "max_hr":lap.get("max_hr"),"cadence_spm":lap.get("avg_cadence"),
            "gct_ms":lap.get("ground_contact_time"),"vertical_oscillation_cm":lap.get("vertical_oscillation"),
            "vertical_ratio_pct":lap.get("vertical_ratio"),"stride_length_cm":lap.get("stride_length"),
            "power_hr_ratio":(lap.get("avg_power")/lap.get("avg_hr") if lap.get("avg_power") and lap.get("avg_hr") else None),
            "data_quality_flags":lap.get("data_quality_flags",[]),
        })
    return rows


def build_today_coaching_tables(today_analysis):
    annotations={}
    s=get_session()
    try:
        for a in today_analysis.get("sessions",[]):
            row=s.query(ActivityAnnotation).filter_by(activity_id=a["activity_id"]).first()
            if row:
                annotations[a["activity_id"]]={"note":row.note,"bike_position":row.bike_position,"interval_positions":_parse_json(row.interval_positions),"swim_subtype":row.swim_subtype,"swim_set_description":row.swim_set_description,"swim_lap_indices":_parse_json(row.swim_lap_indices)}
    finally: s.close()
    out={"date":today_analysis.get("date"),"sessions":[]}
    for session in today_analysis.get("sessions",[]):
        sport=session["sport"]
        laps=_lap_table(session,sport,annotations)
        bands={}
        if sport in INTERVAL_BANDS:
            for b in INTERVAL_BANDS[sport]:
                selected=[r for r in laps if r["classification"]==b]
                if not selected: continue
                primary_key="power_w" if sport=="bike" else "pace_sec_per_km" if sport=="run" else "pace_sec_per_100m"
                vals=[r[primary_key] for r in selected if r[primary_key] is not None]
                hrs=[r["hr"] for r in selected if r["hr"] is not None]
                bands[b]={"interval_count":len(selected),"primary_metric":primary_key,
                          "mean_primary":round(mean(vals),2) if vals else None,"cv_primary_percent":_cv(vals),
                          "mean_hr":round(mean(hrs),1) if hrs else None,"hr_change_first_to_last":round(hrs[-1]-hrs[0],1) if len(hrs)>=2 else None,
                          "historical":_historical_benchmarks(sport,b)}
        out["sessions"].append({"activity_id":session["activity_id"],"name":session["name"],"sport":sport,
                                 "activity_note":annotations.get(session["activity_id"],{}).get("note"),
                                 "swim_annotation":{k:annotations.get(session["activity_id"],{}).get(k) for k in ("swim_subtype","swim_set_description","swim_lap_indices")},
                                 "lap_table":laps,"classification_summary":bands,
                                 "position_comparison":position_comparison(laps) if sport=="bike" else None})
    return out


def position_comparison(laps):
    groups={"aero":[],"non_aero":[]}
    for r in laps:
        p=r.get("position")
        if p in groups and r.get("power_w") is not None: groups[p].append(r)
    out={}
    for p,rows in groups.items():
        if rows:
            out[p]={"count":len(rows),"mean_power_w":round(mean([r["power_w"] for r in rows]),1),
                    "mean_hr":round(mean([r["hr"] for r in rows if r.get("hr") is not None]),1) if any(r.get("hr") is not None for r in rows) else None,
                    "mean_power_hr":round(mean([r["power_hr_ratio"] for r in rows if r.get("power_hr_ratio") is not None]),3) if any(r.get("power_hr_ratio") is not None for r in rows) else None}
    return out
