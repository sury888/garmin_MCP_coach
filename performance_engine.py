"""High-performance Garmin analytics engine.

The engine keeps Garmin-native measurements separate from coach interpretation.
It builds:
- mean-max bike power and run pace curves
- HR response curves / highest-HR windows
- HR-controlled performance records
- run biomechanics attached to performance windows
- historical/all-time leaderboards
- durability records from long-session and brick context
- per-activity performance summaries

No universal HR ceiling is assumed; HR thresholds are query controls, not
physiological prescriptions.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import json, math
from statistics import mean
from typing import Any

from activity_details import parse_activity_details
from database import Activity, PerformanceRecord, get_session, initialize_database
from garmin_client import GarminClient

BIKE_DURATIONS = [1,5,10,30,60,120,180,300,480,600,720,900,1200,1800,2400,3600,5400,7200,10800]
RUN_DURATIONS = [30,60,120,300,600,900,1200,1800,2400,3000,3600,5400,7200]
SWIM_DISTANCES = [25,50,100,200,400,800,1000,1500,1900,3800]
BIKE_HR_LIMITS = [150,155,160,165,170,175]
RUN_HR_LIMITS = [150,155,160,165,170]


def _num(v):
    if v is None or isinstance(v, bool): return None
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError): return None


def _first(row, *keys):
    for k in keys:
        x=_num(row.get(k))
        if x is not None: return x
    return None


def _timestamp(row):
    x=_num(row.get("directTimestamp"))
    if x is not None: return x/1000 if x>10_000_000_000 else x
    raw=row.get("timestamp")
    if isinstance(raw,str):
        try: return datetime.fromisoformat(raw.replace("Z","+00:00")).timestamp()
        except ValueError: return None
    return None


def _sport(activity):
    s=" ".join(str(x or "") for x in (activity.activity_type,activity.activity_name)).lower()
    if any(x in s for x in ("swim","pool","open_water")): return "swim"
    if any(x in s for x in ("run","trail","treadmill")): return "run"
    if any(x in s for x in ("bike","cycling","ride","trainer")): return "bike"
    return "other"


def _is_treadmill(activity) -> bool:
    text = " ".join(str(getattr(activity, attr, "") or "") for attr in ("activity_type", "activity_name")).lower()
    return any(term in text for term in ("treadmill", "indoor run", "indoor_running", "virtual run"))


def _pace(sec):
    if sec is None or not math.isfinite(sec): return None
    n=int(round(sec)); return f"{n//60}:{n%60:02d}/km"


def _samples(details, sport, treadmill=False):
    out=[]
    for r in parse_activity_details(details):
        t=_timestamp(r)
        if t is None: continue
        out.append({
            "t":t,
            "hr":_first(r,"directHeartRate","heartRate","averageHR"),
            "power":_first(r,"directPower","power","averagePower") if sport=="bike" else None,
            "speed":_first(r,"directSpeed","speed","directEnhancedSpeed","enhancedSpeed") if sport=="run" and not treadmill else None,
            "cadence":_first(r,"directBikeCadence","directCadence","bikeCadence","cadence","directRunCadence","runCadence"),
            "gct":_first(r,"directGroundContactTime","groundContactTime","groundContactTimeMillis","groundContactTimeMS"),
            "vo":_first(r,"directVerticalOscillation","verticalOscillation"),
            "vr":_first(r,"directVerticalRatio","verticalRatio"),
            "stride":_first(r,"directStrideLength","strideLength","avgStrideLength"),
            "run_power":_first(r,"directRunningPower","runningPower","power") if sport=="run" else None,
        })
    return sorted(out,key=lambda x:x["t"])


def _windows(samples,duration):
    if len(samples)<2: return
    left=0
    for right in range(len(samples)):
        tr=samples[right]["t"]
        while left<right and tr-samples[left]["t"]>duration: left+=1
        elapsed=tr-samples[left]["t"]
        if elapsed>=duration*.90:
            yield samples[left:right+1],elapsed


def _metrics(w,elapsed,sport,treadmill=False):
    hrs=[x["hr"] for x in w if x["hr"] is not None]
    cad=[x["cadence"] for x in w if x["cadence"] is not None]
    m={"duration_seconds":elapsed,"avg_hr":mean(hrs) if hrs else None,"max_hr":max(hrs) if hrs else None,"avg_cadence":mean(cad) if cad else None}
    for name,key in (("ground_contact_time","gct"),("vertical_oscillation","vo"),("vertical_ratio","vr"),("stride_length","stride")):
        vals=[x[key] for x in w if x[key] is not None]
        if vals:
            m[f"{name}_avg"]=mean(vals); m[f"{name}_max"]=max(vals)
    if sport=="bike":
        p=[x["power"] for x in w if x["power"] is not None]
        if p:
            avg=mean(p); m.update(avg_power=avg,max_power=max(p),kilojoules=avg*elapsed/1000,
                                  power_hr_ratio=avg/m["avg_hr"] if m["avg_hr"] else None)
    elif sport=="run":
        s=[x["speed"] for x in w if x["speed"] and x["speed"]>0]
        rp=[x["run_power"] for x in w if x["run_power"] is not None]
        if s:
            avg=mean(s); m.update(avg_speed_mps=avg,pace_seconds_per_km=1000/avg,pace_per_km=_pace(1000/avg),speed_hr_ratio=avg/m["avg_hr"] if m["avg_hr"] else None)
        if rp: m["avg_running_power"]=mean(rp); m["max_running_power"]=max(rp)
    return m


def _best(parsed,sport,duration,objective,hr_limit=None,treadmill=False):
    ss=_samples(parsed,sport,treadmill=treadmill); best=None
    for w,e in _windows(ss,duration) or []:
        m=_metrics(w,e,sport,treadmill=treadmill); v=m.get(objective)
        if v is None: continue
        if hr_limit is not None and (m.get("avg_hr") is None or m["avg_hr"]>hr_limit): continue
        if best is None or ((v>best["value"]) if objective not in ("pace_seconds_per_km",) else (v<best["value"])):
            best={"value":v,"metrics":m,"start":w[0]["t"],"end":w[-1]["t"]}
    return best


def _activity_start(a):
    raw=a.raw_data
    if raw:
        try:
            d=json.loads(raw) if isinstance(raw,str) else raw
            for k in ("startTimeLocal","startTimeGMT","startTime","activityStartTime"):
                if d.get(k):
                    return datetime.fromisoformat(str(d[k]).replace("Z","+00:00")).timestamp()
        except Exception: pass
    return datetime.combine(a.activity_date,datetime.min.time()).timestamp() if a.activity_date else 0


def _record(activity_id,sport,metric_type,primary,duration=None,distance=None,metrics=None):
    m=metrics or {}
    return PerformanceRecord(activity_id=activity_id,sport=sport,metric_type=metric_type,
        duration_seconds=duration,distance_m=distance,primary_value=primary,
        avg_hr=m.get("avg_hr"),max_hr=m.get("max_hr"),cadence=m.get("avg_cadence"),
        watts_per_kg=m.get("watts_per_kg"),kilojoules=m.get("kilojoules"),
        power_hr_ratio=m.get("power_hr_ratio"),window_start=_iso(m.get("window_start")),
        window_end=_iso(m.get("window_end")),metric_json=json.dumps(_jsonsafe(m)))


def _iso(ts):
    return datetime.fromtimestamp(ts).isoformat() if isinstance(ts,(int,float)) else ts


def _jsonsafe(x):
    if isinstance(x,dict): return {k:_jsonsafe(v) for k,v in x.items()}
    if isinstance(x,list): return [_jsonsafe(v) for v in x]
    if isinstance(x,(datetime,date)): return x.isoformat()
    return x


def analyze_bike_performance(activity_id,details,weight_kg=None):
    parsed=parse_activity_details(details); curve={}; hr_curve={}; controlled={}
    for d in BIKE_DURATIONS:
        b=_best(parsed,"bike",d,"avg_power")
        h=_best(parsed,"bike",d,"avg_hr")
        if b:
            m=dict(b["metrics"]); m["watts_per_kg"]=m["avg_power"]/weight_kg if weight_kg else None
            m.update(window_start=b["start"],window_end=b["end"])
            curve[str(d)]={"duration_seconds":d,"best_power_w":round(m["avg_power"],1),"watts_per_kg":round(m["watts_per_kg"],2) if m["watts_per_kg"] else None,**_public_metrics(m)}
        if h: hr_curve[str(d)]={"duration_seconds":d,"highest_avg_hr":round(h["value"],1),"max_hr":h["metrics"].get("max_hr"),"power_during_window":h["metrics"].get("avg_power")}
        for limit in BIKE_HR_LIMITS:
            b=_best(parsed,"bike",d,"avg_power",limit)
            if b: controlled[f"{d}:{limit}"]={"duration_seconds":d,"hr_limit":limit,"power_w":round(b["value"],1),**_public_metrics(b["metrics"])}
    return {"activity_id":activity_id,"sport":"bike","peak_power_curve":curve,"highest_hr_curve":hr_curve,"hr_controlled_records":controlled}


def analyze_run_performance(activity_id,details,treadmill=False):
    parsed=parse_activity_details(details); curve={}; hr_curve={}; controlled={}
    for d in RUN_DURATIONS:
        b=_best(parsed,"run",d,"avg_speed_mps",treadmill=treadmill); h=_best(parsed,"run",d,"avg_hr",treadmill=treadmill)
        if b:
            m=dict(b["metrics"]); m.update(window_start=b["start"],window_end=b["end"])
            curve[str(d)]={"duration_seconds":d,"pace_per_km":m.get("pace_per_km"),"pace_seconds_per_km":m.get("pace_seconds_per_km"),**_public_metrics(m)}
        if h: hr_curve[str(d)]={"duration_seconds":d,"highest_avg_hr":round(h["value"],1),"max_hr":h["metrics"].get("max_hr"),"pace_during_window":h["metrics"].get("pace_per_km")}
        for limit in RUN_HR_LIMITS:
            b=_best(parsed,"run",d,"pace_seconds_per_km",limit,treadmill=treadmill)
            if b: controlled[f"{d}:{limit}"]={"duration_seconds":d,"hr_limit":limit,"pace_per_km":b["metrics"].get("pace_per_km"),"pace_seconds_per_km":round(b["value"],1),**_public_metrics(b["metrics"])}
    return {"activity_id":activity_id,"sport":"run","treadmill":treadmill,"pace_data_excluded":treadmill,"peak_pace_curve":curve,"highest_hr_curve":hr_curve,"hr_controlled_records":controlled}


def _public_metrics(m):
    keys=("avg_hr","max_hr","avg_cadence","ground_contact_time_avg","ground_contact_time_max","vertical_oscillation_avg","vertical_oscillation_max","vertical_ratio_avg","vertical_ratio_max","stride_length_avg","stride_length_max","avg_running_power","max_running_power","kilojoules","power_hr_ratio","speed_hr_ratio")
    return {k:round(m[k],3) if isinstance(m.get(k),(int,float)) else m.get(k) for k in keys if m.get(k) is not None}


def analyze_swim_performance(activity_id,splits):
    curve={}
    for target in SWIM_DISTANCES:
        candidates=[]
        for lap in splits.get("lapDTOs",[]):
            dist=_first(lap,"distance","distanceMeters"); dur=_first(lap,"duration","durationSeconds")
            if not dist or not dur or abs(dist-target)>max(1,target*.01): continue
            candidates.append((dur/dist*100,lap))
        if candidates:
            pace,lap=min(candidates,key=lambda x:x[0]); curve[str(target)]={"distance_m":target,"time_seconds":round(pace*target/100,2),"pace_seconds_per_100m":round(pace,2),"pace_per_100m":_pace100(pace),"avg_hr":_first(lap,"averageHR","avgHR","averageHeartRate"),"strokes":_first(lap,"totalNumberOfStrokes","strokes","totalStrokes"),"stroke_type":lap.get("swimStroke") or lap.get("strokeType") or lap.get("stroke")}
    return {"activity_id":activity_id,"sport":"swim","peak_swim_curve":curve,"note":"Exact Garmin-native lap distances only; no synthetic boundaries."}


def _pace100(s):
    n=int(round(s)); return f"{n//60}:{n%60:02d}/100m"


def save_performance_records(activity_id,sport,analysis):
    session=get_session()
    try:
        session.query(PerformanceRecord).filter_by(activity_id=activity_id).delete()
        curve_key={"bike":"peak_power_curve","run":"peak_pace_curve","swim":"peak_swim_curve"}[sport]
        for key,r in analysis.get(curve_key,{}).items():
            primary=r.get("best_power_w") if sport=="bike" else r.get("pace_seconds_per_km") if sport=="run" else r.get("pace_seconds_per_100m")
            session.add(_record(activity_id,sport,"peak",primary,r.get("duration_seconds"),r.get("distance_m"),r))
        if sport in ("bike","run"):
            for key,r in analysis.get("highest_hr_curve",{}).items():
                session.add(_record(activity_id,sport,"hr_peak",r.get("highest_avg_hr"),r.get("duration_seconds"),metrics=r))
            for key,r in analysis.get("hr_controlled_records",{}).items():
                session.add(_record(activity_id,sport,f"controlled_hr_{r['hr_limit']}",r.get("power_w") if sport=="bike" else r.get("pace_seconds_per_km"),r.get("duration_seconds"),metrics=r))
        session.commit()
    finally: session.close()


def _load_activity(activity_id):
    s=get_session()
    try: return s.query(Activity).filter_by(activity_id=activity_id).first()
    finally: s.close()


def process_activity_performance(activity_id,weight_kg=None):
    initialize_database()
    a=_load_activity(activity_id)
    if not a: return {"error":"Activity is not in local database.","activity_id":activity_id}
    sport=_sport(a); g=GarminClient(); g.login()
    if sport=="swim": analysis=analyze_swim_performance(activity_id,g.get_activity_splits(activity_id))
    elif sport in ("bike","run"):
        d=g.get_activity_details(activity_id)
        if sport=="bike":
            analysis=analyze_bike_performance(activity_id,d,weight_kg)
        else:
            treadmill=_is_treadmill(a)
            analysis=analyze_run_performance(activity_id,d,treadmill=treadmill)
    else: return {"error":"Unsupported activity sport.","sport":sport,"activity_id":activity_id}
    save_performance_records(activity_id,sport,analysis); return analysis


def build_performance_database(
    days=None,
    max_activities=None,
    weight_kg=None,
    batch_size=10,
    resume=True,
):
    """
    Build performance records in small resumable batches.

    This deliberately avoids one giant Garmin-detail workload. Activities are
    selected from the local database, processed in batches, committed after
    every activity, and errors are isolated to individual activities.

    max_activities=None means all locally synced activities in the date window.
    resume=True skips an activity only when it already has usable performance
    records for its sport. Set resume=False to force reprocessing.
    """
    initialize_database()
    batch_size = max(1, int(batch_size))

    s = get_session()
    try:
        q = s.query(Activity).order_by(Activity.activity_date.desc(), Activity.activity_id.desc())
        if days is not None:
            q = q.filter(
                Activity.activity_date >= date.today() - timedelta(days=days - 1)
            )
        if max_activities is not None:
            q = q.limit(int(max_activities))
        acts = q.all()
    finally:
        s.close()

    # Only endurance sports enter the detailed performance engine.
    endurance = [a for a in acts if _sport(a) in ("bike", "run", "swim")]

    def has_usable_records(activity_id, sport):
        if not resume:
            return False
        s = get_session()
        try:
            return s.query(PerformanceRecord).filter(
                PerformanceRecord.activity_id == activity_id,
                PerformanceRecord.sport == sport,
                PerformanceRecord.metric_type == "peak",
            ).count() > 0
        finally:
            s.close()

    g = GarminClient()
    g.login()

    processed = []
    skipped = []
    errors = []
    batch_reports = []

    for batch_start in range(0, len(endurance), batch_size):
        batch = endurance[batch_start:batch_start + batch_size]
        batch_processed = []
        batch_errors = []
        batch_skipped = []

        for a in batch:
            sport = _sport(a)

            usable = has_usable_records(a.activity_id, sport)
            if sport == "run" and _is_treadmill(a):
                # Existing treadmill peak-pace records may have been generated
                # before treadmill pace was marked unreliable. Reprocess them so
                # those invalid pace records are removed and only HR/dynamics remain.
                usable = False

            if usable:
                item = {
                    "activity_id": a.activity_id,
                    "name": a.activity_name,
                    "date": str(a.activity_date),
                    "sport": sport,
                    "reason": "already_processed",
                }
                skipped.append(item)
                batch_skipped.append(item)
                continue

            try:
                if sport == "swim":
                    raw = g.get_activity_splits(a.activity_id)
                    analysis = analyze_swim_performance(a.activity_id, raw)
                else:
                    raw = g.get_activity_details(a.activity_id)
                    analysis = (
                        analyze_bike_performance(a.activity_id, raw, weight_kg)
                        if sport == "bike"
                        else analyze_run_performance(a.activity_id, raw, treadmill=_is_treadmill(a))
                    )

                save_performance_records(a.activity_id, sport, analysis)

                item = {
                    "activity_id": a.activity_id,
                    "name": a.activity_name,
                    "date": str(a.activity_date),
                    "sport": sport,
                }
                processed.append(item)
                batch_processed.append(item)
            except Exception as exc:
                item = {
                    "activity_id": a.activity_id,
                    "name": a.activity_name,
                    "date": str(a.activity_date),
                    "sport": sport,
                    "error": str(exc),
                }
                errors.append(item)
                batch_errors.append(item)

        batch_reports.append({
            "batch_start": batch_start,
            "processed": len(batch_processed),
            "skipped": len(batch_skipped),
            "errors": len(batch_errors),
        })

    return {
        "success": True,
        "activities_considered": len(acts),
        "endurance_activities_considered": len(endurance),
        "activities_processed": len(processed),
        "activities_skipped": len(skipped),
        "errors": len(errors),
        "processed": processed,
        "skipped": skipped,
        "error_items": errors,
        "batch_size": batch_size,
        "batch_reports": batch_reports,
        "durability_records_created": durability,
        "note": (
            "Processing is resumable. Existing peak records are skipped when "
            "resume=True. Use max_activities=None for all locally synced "
            "activities in the selected date window."
        ),
    }

def _build_durability(activities,analyses):
    # Uses same-day sequencing when Garmin exposes start time in raw_data.
    ordered=sorted([a for a in activities if _sport(a) in ("bike","run","swim")],key=_activity_start)
    saved=0; out=[]; s=get_session()
    try:
        for i,a in enumerate(ordered):
            sp=_sport(a); prior=[x for x in ordered[:i] if x.activity_date==a.activity_date]
            bike_sec=sum((x.duration_seconds or 0) for x in prior if _sport(x)=="bike")
            if sp=="bike" and (a.duration_seconds or 0)>=3*3600:
                candidates=[r for r in analyses.get(a.activity_id,{}).get("peak_power_curve",{}).values() if r.get("duration_seconds") in (1800,3600)]
                if candidates:
                    r=max(candidates,key=lambda x:x.get("best_power_w",-1)); out.append({"type":"bike_after_3h","activity_id":a.activity_id,"duration_seconds":r["duration_seconds"],"power_w":r["best_power_w"]})
                    s.add(_record(a.activity_id,"bike","durability_after_3h",r["best_power_w"],r["duration_seconds"],metrics=r)); saved+=1
            if sp=="run" and bike_sec>=2*3600:
                candidates=[r for r in analyses.get(a.activity_id,{}).get("peak_pace_curve",{}).values() if r.get("duration_seconds")==1800]
                if candidates:
                    r=min(candidates,key=lambda x:x.get("pace_seconds_per_km",1e9)); out.append({"type":"run_after_2h_bike","activity_id":a.activity_id,"duration_seconds":1800,"pace_per_km":r.get("pace_per_km"),"preceding_bike_seconds":bike_sec})
                    s.add(_record(a.activity_id,"run","durability_after_2h_bike",r.get("pace_seconds_per_km"),1800,metrics=r)); saved+=1
            if sp=="swim":
                # Session-distance durability: exact 400/800/1000m laps are retained;
                # only flag sessions whose total distance exceeds 3000m.
                dist=a.distance_meters or 0
                if dist>=3000:
                    r=analyses.get(a.activity_id,{}).get("peak_swim_curve",{}).get("400")
                    if r:
                        out.append({"type":"swim_after_3000m_session","activity_id":a.activity_id,"distance_m":dist,"pace_per_100m":r.get("pace_per_100m")})
                        s.add(_record(a.activity_id,"swim","durability_after_3000m",r.get("pace_seconds_per_100m"),distance=400,metrics=r)); saved+=1
        s.commit()
    finally: s.close()
    return saved


def _query_records(sport,metric_type=None,window_days=None,limit=None):
    s=get_session()
    try:
        q=s.query(PerformanceRecord,Activity.activity_date,Activity.activity_name).join(Activity,Activity.activity_id==PerformanceRecord.activity_id).filter(PerformanceRecord.sport==sport)
        if metric_type: q=q.filter(PerformanceRecord.metric_type==metric_type)
        if window_days is not None: q=q.filter(Activity.activity_date>=date.today()-timedelta(days=window_days-1))
        if limit: q=q.limit(limit)
        return q.all()
    finally: s.close()


def _dict(r,d,n):
    try: extra=json.loads(r.metric_json) if r.metric_json else {}
    except Exception: extra={}
    return {"activity_id":r.activity_id,"activity_date":str(d),"activity_name":n,"sport":r.sport,"metric_type":r.metric_type,"duration_seconds":r.duration_seconds,"distance_m":r.distance_m,"primary_value":r.primary_value,"avg_hr":r.avg_hr,"max_hr":r.max_hr,"cadence":r.cadence,"watts_per_kg":r.watts_per_kg,"kilojoules":r.kilojoules,"power_hr_ratio":r.power_hr_ratio,**extra}


def _is_valid_historical_record(row, sport):
    r, _, _ = row
    if r.primary_value is None:
        return False

    # Garmin can occasionally save impossible short swim splits, especially
    # drill/touchpad laps. Never allow those into athlete-performance records.
    if sport == "swim":
        pace = float(r.primary_value)
        if pace < 20 or pace > 300:
            return False
        try:
            extra = json.loads(r.metric_json) if r.metric_json else {}
        except Exception:
            extra = {}
        stroke_type = str(extra.get("stroke_type") or extra.get("swim_stroke") or "").upper()
        strokes = extra.get("strokes")
        if stroke_type == "DRILL" and strokes in (0, 0.0, None):
            return False
    return True


def get_peak_records(sport,window_days=None):
    rows=_query_records(sport,"peak",window_days)
    grouped={}
    for row in rows:
        if not _is_valid_historical_record(row, sport):
            continue
        r,d,n = row
        key=str(r.duration_seconds if r.duration_seconds is not None else r.distance_m); grouped.setdefault(key,[]).append(row)
    out={}
    for k,items in grouped.items():
        vals=[x for x in items if x[0].primary_value is not None]
        if not vals: continue
        winner=max(vals,key=lambda x:x[0].primary_value) if sport=="bike" else min(vals,key=lambda x:x[0].primary_value)
        out[k]=_dict(*winner)
    return dict(sorted(out.items(),key=lambda x:float(x[0])))


def get_historical_records(sport,window_days=365,limit=100):
    rows=_query_records(sport,"peak",window_days)
    valid=[x for x in rows if _is_valid_historical_record(x, sport)]
    # Return the requested number of actual records after quality filtering.
    valid.sort(key=lambda x: x[0].activity_id or 0, reverse=True)
    return [_dict(*x) for x in valid[:max(1, min(int(limit), 500))]]


def get_hr_controlled_records(sport,hr_limit=165,window_days=None):
    if sport not in ("bike","run"): return {"error":"HR-controlled records are for bike or run."}
    rows=_query_records(sport,f"controlled_hr_{int(hr_limit)}",window_days)
    grouped={}
    for r,d,n in rows:
        k=str(r.duration_seconds); grouped.setdefault(k,[]).append((r,d,n))
    out={}
    for k,items in grouped.items():
        winner=(max if sport=="bike" else min)(items,key=lambda x:x[0].primary_value if x[0].primary_value is not None else (-1 if sport=="bike" else 1e99))
        out[k]=_dict(*winner)
    return out


def get_highest_hr_history(sport,window_days=None):
    rows=_query_records(sport,"hr_peak",window_days)
    grouped={}
    for r,d,n in rows:
        k=str(r.duration_seconds); grouped.setdefault(k,[]).append((r,d,n))
    out={}
    for k,items in grouped.items():
        winner=max(items,key=lambda x:x[0].primary_value or -1); out[k]=_dict(*winner)
    return dict(sorted(out.items(),key=lambda x:float(x[0])))


def get_leaderboard(sport,metric="peak",window_days=None,limit=20):
    rows=_query_records(sport,metric,window_days)
    vals=[_dict(*x) for x in rows if x[0].primary_value is not None]
    vals.sort(key=lambda x:x["primary_value"],reverse=(sport=="bike" or metric=="hr_peak"))
    return vals[:max(1,min(int(limit),200))]


def get_durability_records(sport=None,window_days=None):
    types=("durability_after_3h","durability_after_2h_bike","durability_after_3000m")
    sports=[sport] if sport else ["bike","run","swim"]
    out=[]
    for sp in sports:
        for typ in types: out.extend(_dict(*x) for x in _query_records(sp,typ,window_days))
    return out
