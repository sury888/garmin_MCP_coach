"""Historical weather context for Garmin activities.

Uses Open-Meteo archive data when an activity contains GPS coordinates.
Weather is contextual evidence, not a performance correction by itself.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json, math, urllib.parse, urllib.request

from database import Activity, WeatherObservation, get_session, initialize_database


def _num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _raw(a):
    try:
        return json.loads(a.raw_data) if isinstance(a.raw_data, str) else (a.raw_data or {})
    except Exception:
        return {}


def activity_location(a):
    d=_raw(a)
    # Garmin uses several names across activity endpoints.
    lat_keys=("startLatitude","startLat","latitude","startLatitudeDegrees")
    lon_keys=("startLongitude","startLon","longitude","startLongitudeDegrees")
    lat=next((_num(d.get(k)) for k in lat_keys if _num(d.get(k)) is not None),None)
    lon=next((_num(d.get(k)) for k in lon_keys if _num(d.get(k)) is not None),None)
    return lat,lon


def _activity_start_utc(a):
    d=_raw(a)
    for k in ("startTimeGMT","startTimeUtc","startTimeUTC","startTimeLocal","startTime"):
        if d.get(k):
            try:
                x=datetime.fromisoformat(str(d[k]).replace("Z","+00:00"))
                if x.tzinfo is None: x=x.replace(tzinfo=timezone.utc)
                return x.astimezone(timezone.utc)
            except ValueError: pass
    return datetime.combine(a.activity_date, datetime.min.time(), tzinfo=timezone.utc)


def _archive(lat,lon,dt):
    params={"latitude":lat,"longitude":lon,"start_date":dt.date().isoformat(),"end_date":dt.date().isoformat(),
            "hourly":"temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,wind_speed_10m,wind_direction_10m,shortwave_radiation,uv_index",
            "timezone":"UTC"}
    url="https://archive-api.open-meteo.com/v1/archive?"+urllib.parse.urlencode(params)
    with urllib.request.urlopen(url,timeout=15) as r:
        return json.load(r)


def fetch_activity_weather(activity_id):
    initialize_database(); s=get_session()
    try:
        a=s.query(Activity).filter_by(activity_id=activity_id).first()
        if not a: return {"error":"Activity not found","activity_id":activity_id}
        lat,lon=activity_location(a)
        if lat is None or lon is None:
            return {"error":"No GPS start coordinates available for this activity.","activity_id":activity_id}
        dt=_activity_start_utc(a); data=_archive(lat,lon,dt)
        times=data.get("hourly",{}).get("time",[])
        if not times: return {"error":"Weather API returned no hourly data.","activity_id":activity_id}
        idx=min(range(len(times)),key=lambda i: abs(datetime.fromisoformat(times[i]).replace(tzinfo=timezone.utc)-dt))
        h=data["hourly"]
        def val(k): return h.get(k,[None]*len(times))[idx]
        obs={"activity_id":activity_id,"observed_at":dt.isoformat(),"latitude":lat,"longitude":lon,
             "temperature_c":val("temperature_2m"),"relative_humidity":val("relative_humidity_2m"),
             "apparent_temperature_c":val("apparent_temperature"),"precipitation_mm":val("precipitation"),
             "wind_speed_kmh":val("wind_speed_10m"),"wind_direction_deg":val("wind_direction_10m"),
             "shortwave_radiation_wm2":val("shortwave_radiation"),"uv_index":val("uv_index")}
        existing=s.query(WeatherObservation).filter_by(activity_id=activity_id).first()
        if existing:
            for k,v in obs.items(): setattr(existing,k,v)
        else: s.add(WeatherObservation(**obs))
        s.commit()
        obs["temperature_f"]=round(obs["temperature_c"]*9/5+32,1) if obs["temperature_c"] is not None else None
        obs["apparent_temperature_f"]=round(obs["apparent_temperature_c"]*9/5+32,1) if obs["apparent_temperature_c"] is not None else None
        return obs
    except Exception as e:
        s.rollback(); return {"error":str(e),"activity_id":activity_id}
    finally: s.close()


def get_activity_weather(activity_id):
    initialize_database(); s=get_session()
    try:
        x=s.query(WeatherObservation).filter_by(activity_id=activity_id).first()
        if not x: return fetch_activity_weather(activity_id)
        return {c.name:getattr(x,c.name) for c in x.__table__.columns} | {
            "temperature_f":round(x.temperature_c*9/5+32,1) if x.temperature_c is not None else None,
            "apparent_temperature_f":round(x.apparent_temperature_c*9/5+32,1) if x.apparent_temperature_c is not None else None}
    finally: s.close()
