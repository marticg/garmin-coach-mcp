"""
Garmin Coach IA — Servidor MCP
================================
Servidor MCP que connecta les teves dades reals de Garmin Connect
amb Claude i ChatGPT. Desplega a Render.com (0€/mes).

Eines exposades:
  Son & HRV     → get_sleep, get_hrv, get_sleep_summary
  Activitat     → get_activities, get_steps, get_today_stats
  Salut         → get_body_battery, get_stress, get_heart_rate
  Rendiment     → get_vo2max, get_training_status, get_training_load
  Pes           → get_weight
  Perfil        → get_user_profile
  Coach         → get_full_snapshot  (tot en una crida)
"""

import os
import json
import datetime
import secrets
import hashlib
from typing import Optional
from contextlib import asynccontextmanager

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

# ─── Garmin Connect ───────────────────────────────────────────────────────────
try:
    from garminconnect import (
        Garmin,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
    )
    GARMIN_AVAILABLE = True
except ImportError:
    GARMIN_AVAILABLE = False

# ─── Config des de variables d'entorn ────────────────────────────────────────
GARMIN_EMAIL    = os.environ.get("GARMIN_EMAIL", "")
GARMIN_PASSWORD = os.environ.get("GARMIN_PASSWORD", "")
MCP_TOKEN       = os.environ.get("MCP_TOKEN", secrets.token_urlsafe(32))

# Perfil de l'usuari (configurable per variables d'entorn)
USER_NAME   = os.environ.get("USER_NAME", "")
USER_AGE    = int(os.environ.get("USER_AGE", "0") or "0")
USER_SEX    = os.environ.get("USER_SEX", "")
USER_HEIGHT = int(os.environ.get("USER_HEIGHT", "0") or "0")
USER_WEIGHT = float(os.environ.get("USER_WEIGHT", "0") or "0")
USER_GOAL   = os.environ.get("USER_GOAL", "salut general")
USER_LANG   = os.environ.get("USER_LANG", "ca")  # ca | es

print(f"[GARMIN MCP] Token: {MCP_TOKEN}")
print(f"[GARMIN MCP] Usuari: {USER_NAME or 'sense nom'}, {USER_AGE} anys, {USER_SEX}")

# ─── Connexió singleton a Garmin ─────────────────────────────────────────────
_garmin_client: Optional[Garmin] = None

def get_garmin() -> Garmin:
    global _garmin_client
    if _garmin_client is not None:
        return _garmin_client

    if not GARMIN_AVAILABLE:
        raise RuntimeError("garminconnect no instal·lat. Afegeix-lo a requirements.txt")
    if not GARMIN_EMAIL or not GARMIN_PASSWORD:
        raise RuntimeError("Cal definir GARMIN_EMAIL i GARMIN_PASSWORD com a variables d'entorn")

    client = Garmin(email=GARMIN_EMAIL, password=GARMIN_PASSWORD)
    client.login()
    _garmin_client = client
    return client

def safe_garmin(fn, *args, default=None, **kwargs):
    """Crida una funció de Garmin i retorna default si falla."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[GARMIN ERR] {fn.__name__}: {e}")
        return default

def today() -> str:
    return datetime.date.today().isoformat()

def days_ago(n: int) -> str:
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()

def profile_context() -> str:
    """Retorna el context del perfil de l'usuari per incloure a totes les respostes."""
    if not USER_AGE and not USER_SEX:
        return ""
    parts = []
    if USER_NAME:   parts.append(USER_NAME)
    if USER_AGE:    parts.append(f"{USER_AGE} anys")
    if USER_SEX:    parts.append(USER_SEX)
    if USER_HEIGHT: parts.append(f"{USER_HEIGHT}cm")
    if USER_WEIGHT: parts.append(f"{USER_WEIGHT}kg")
    if USER_GOAL:   parts.append(f"objectiu: {USER_GOAL}")
    return "Perfil: " + ", ".join(parts) + "."

# ─── FastMCP ──────────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="Garmin Coach IA",
    instructions=(
        "Servidor MCP que dona accés a les dades reals de Garmin Connect. "
        "Usa les eines per obtenir dades de son, activitat, salut i rendiment. "
        "Sempre tingues en compte el perfil de l'usuari en les recomanacions. "
        f"{profile_context()}"
    ),
)

# ══════════════════════════════════════════════════════════════════════════════
# EINES — SON & HRV
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_sleep(date: str = "") -> dict:
    """
    Obté les dades de son d'una nit específica.
    Inclou: durada total, son profund/lleuger/REM, despertes,
    puntuació de son, SpO2, freqüència respiratòria i HRV nocturn.
    date: YYYY-MM-DD (per defecte: avui)
    """
    d = date or today()
    api = get_garmin()
    raw = safe_garmin(api.get_sleep_data, d, default={})

    if not raw:
        return {"error": f"No hi ha dades de son per al {d}", "perfil": profile_context()}

    daily = raw.get("dailySleepDTO") or raw
    result = {
        "data":                   d,
        "total_son_min":          round((daily.get("sleepTimeSeconds") or 0) / 60),
        "son_profund_min":        round((daily.get("deepSleepSeconds") or 0) / 60),
        "son_lleuger_min":        round((daily.get("lightSleepSeconds") or 0) / 60),
        "son_rem_min":            round((daily.get("remSleepSeconds") or 0) / 60),
        "despertes_min":          round((daily.get("awakeSleepSeconds") or 0) / 60),
        "puntuacio_son":          daily.get("sleepScores", {}).get("overall", {}).get("value") if isinstance(daily.get("sleepScores"), dict) else daily.get("sleepScore"),
        "spo2_mig":               daily.get("averageSpO2Value"),
        "freq_respiratoria_mig":  daily.get("averageRespirationValue"),
        "hrv_nocturn":            daily.get("avgOvernightHrv"),
        "perfil":                 profile_context(),
    }
    result["total_son_hores"] = round(result["total_son_min"] / 60, 1)
    return result


@mcp.tool
def get_hrv(days: int = 7) -> dict:
    """
    Obté les dades d'HRV (variabilitat de la freqüència cardíaca) dels últims N dies.
    L'HRV és un indicador clau de recuperació i estrès del sistema nerviós.
    days: nombre de dies (1-30, per defecte 7)
    """
    api = get_garmin()
    raw = safe_garmin(api.get_hrv_data, today(), default={})

    result = {"dies_sol·licitats": days, "perfil": profile_context()}

    if raw and isinstance(raw, dict):
        hrv = raw.get("hrvSummary") or raw
        result.update({
            "hrv_mig_setmanal":   hrv.get("weeklyAvg"),
            "hrv_ultima_nit":     hrv.get("lastNight"),
            "hrv_5dies_alt":      hrv.get("lastFive", {}).get("high") if isinstance(hrv.get("lastFive"), dict) else None,
            "hrv_5dies_baix":     hrv.get("lastFive", {}).get("low") if isinstance(hrv.get("lastFive"), dict) else None,
            "estat_hrv":          hrv.get("status"),
        })

    # Historial de son per HRV nocturn
    sleep_hrv = []
    for i in range(min(days, 14)):
        d = days_ago(i)
        s = safe_garmin(api.get_sleep_data, d, default={})
        if s:
            daily = s.get("dailySleepDTO") or s
            hrv_val = daily.get("avgOvernightHrv")
            if hrv_val:
                sleep_hrv.append({"data": d, "hrv": hrv_val})

    result["historial_hrv_nocturn"] = sleep_hrv
    return result


@mcp.tool
def get_sleep_summary(days: int = 7) -> dict:
    """
    Resum de son dels últims N dies: tendències, mitjanes i alertes.
    Útil per detectar patrons de mala qualitat de son.
    days: 7, 14 o 30
    """
    api = get_garmin()
    records = []

    for i in range(days):
        d = days_ago(i)
        raw = safe_garmin(api.get_sleep_data, d, default={})
        if raw:
            daily = raw.get("dailySleepDTO") or raw
            mins = round((daily.get("sleepTimeSeconds") or 0) / 60)
            if mins > 0:
                records.append({
                    "data":        d,
                    "hores":       round(mins / 60, 1),
                    "puntuacio":   daily.get("sleepScore"),
                    "hrv":         daily.get("avgOvernightHrv"),
                    "spo2":        daily.get("averageSpO2Value"),
                })

    if not records:
        return {"error": "No hi ha dades de son disponibles", "perfil": profile_context()}

    hores_valides = [r["hores"] for r in records if r["hores"]]
    punts_valids  = [r["puntuacio"] for r in records if r.get("puntuacio")]
    hrv_valids    = [r["hrv"] for r in records if r.get("hrv")]

    return {
        "periode_dies":      days,
        "nits_amb_dades":    len(records),
        "hores_mig":         round(sum(hores_valides) / len(hores_valides), 1) if hores_valides else None,
        "puntuacio_mitja":   round(sum(punts_valids) / len(punts_valids)) if punts_valids else None,
        "hrv_mig_nocturn":   round(sum(hrv_valids) / len(hrv_valids)) if hrv_valids else None,
        "nits_menys_6h":     sum(1 for h in hores_valides if h < 6),
        "registres":         records,
        "perfil":            profile_context(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EINES — ACTIVITAT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_activities(days: int = 7, activity_type: str = "") -> dict:
    """
    Obté les activitats esportives dels últims N dies.
    Inclou: tipus, durada, distància, calories, FC, zones de FC, potència.
    days: 1-90 (per defecte 7)
    activity_type: filtre opcional (running, cycling, swimming, hiking, etc.)
    """
    api = get_garmin()
    start = days_ago(days)
    raw = safe_garmin(api.get_activities_by_date, start, today(), default=[])

    if not raw:
        return {"error": "No hi ha activitats al període", "perfil": profile_context()}

    activities = []
    for a in raw:
        atype = ""
        if isinstance(a.get("activityType"), dict):
            atype = a["activityType"].get("typeKey", "unknown")
        elif isinstance(a.get("activityType"), str):
            atype = a["activityType"]

        if activity_type and activity_type.lower() not in atype.lower():
            continue

        activities.append({
            "id":              a.get("activityId"),
            "data":            (a.get("startTimeLocal") or "")[:10],
            "nom":             a.get("activityName"),
            "tipus":           atype,
            "durada_min":      round((a.get("duration") or 0) / 60, 1),
            "distancia_km":    round((a.get("distance") or 0) / 1000, 2) or None,
            "calories":        a.get("calories"),
            "fc_mitja":        a.get("averageHR"),
            "fc_max":          a.get("maxHR"),
            "desnivell_m":     a.get("elevationGain"),
            "potencia_w":      a.get("avgPower"),
            "ef_aerobi":       a.get("aerobicTrainingEffect"),
            "ef_anaerobi":     a.get("anaerobicTrainingEffect"),
            "vo2max_est":      a.get("vO2MaxValue"),
        })

    return {
        "periode_dies":    days,
        "total":           len(activities),
        "activitats":      activities,
        "perfil":          profile_context(),
    }


@mcp.tool
def get_steps(days: int = 7) -> dict:
    """
    Historial de passos diaris dels últims N dies.
    Inclou: passos, pisos pujats, calories actives i minuts d'intensitat.
    days: 1-30 (per defecte 7)
    """
    api = get_garmin()
    records = []

    for i in range(days):
        d = days_ago(i)
        stats = safe_garmin(api.get_stats, d, default={})
        if stats and isinstance(stats, dict):
            records.append({
                "data":          d,
                "passos":        stats.get("totalSteps"),
                "pisos":         stats.get("floorsAscended"),
                "calories_act":  stats.get("activeKilocalories"),
                "min_moderada":  stats.get("moderateIntensityMinutes"),
                "min_vigorosa":  stats.get("vigorousIntensityMinutes"),
            })

    if not records:
        return {"error": "No hi ha dades de passos", "perfil": profile_context()}

    passos_valids = [r["passos"] for r in records if r.get("passos")]
    return {
        "periode_dies":   days,
        "passos_mig":     round(sum(passos_valids) / len(passos_valids)) if passos_valids else None,
        "dies_10k_passos": sum(1 for p in passos_valids if p >= 10000),
        "registres":      records,
        "perfil":         profile_context(),
    }


@mcp.tool
def get_today_stats() -> dict:
    """
    Estadístiques d'avui en temps real: passos actuals, calories, Body Battery,
    freqüència cardíaca en repòs i nivell d'estrès actual.
    """
    api = get_garmin()
    d = today()

    stats = safe_garmin(api.get_stats, d, default={})
    bb    = safe_garmin(api.get_body_battery, d, d, default=[])
    hr    = safe_garmin(api.get_rhr_day, d, d, default=[])

    result = {
        "data":  d,
        "avui": {},
        "perfil": profile_context(),
    }

    if stats:
        result["avui"].update({
            "passos":          stats.get("totalSteps"),
            "calories_act":    stats.get("activeKilocalories"),
            "calories_total":  stats.get("totalKilocalories"),
            "pisos":           stats.get("floorsAscended"),
            "min_moderada":    stats.get("moderateIntensityMinutes"),
            "min_vigorosa":    stats.get("vigorousIntensityMinutes"),
            "estres_mig":      stats.get("averageStressLevel"),
            "estres_max":      stats.get("maxStressLevel"),
        })

    if bb and isinstance(bb, list):
        vals = [b.get("value") or b.get("charged") for b in bb if b.get("value") or b.get("charged")]
        if vals:
            result["avui"]["body_battery_actual"] = vals[-1]
            result["avui"]["body_battery_maxim"]  = max(vals)

    if hr and isinstance(hr, list) and hr:
        result["avui"]["fc_repos"] = hr[-1].get("value") or hr[-1].get("restingHeartRate")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# EINES — SALUT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_body_battery(days: int = 7) -> dict:
    """
    Historial del Body Battery dels últims N dies.
    El Body Battery mesura la reserva d'energia: 0-100.
    Valors alts = bona recuperació. Valors baixos = cal descansar.
    days: 1-30 (per defecte 7)
    """
    api = get_garmin()
    records = []

    for i in range(days):
        d = days_ago(i)
        bb = safe_garmin(api.get_body_battery, d, d, default=[])
        if bb and isinstance(bb, list):
            vals = [b.get("value") or b.get("charged") for b in bb if b.get("value") or b.get("charged")]
            drained = [b.get("drained") for b in bb if b.get("drained")]
            if vals:
                records.append({
                    "data":         d,
                    "maxim":        max(vals),
                    "minim":        min(vals),
                    "actual":       vals[-1],
                    "energia_usada": max(drained) if drained else None,
                })

    if not records:
        return {"error": "No hi ha dades de Body Battery", "perfil": profile_context()}

    maxims = [r["maxim"] for r in records]
    return {
        "periode_dies":     days,
        "bb_mig_maxim":     round(sum(maxims) / len(maxims)),
        "dies_baixa_energia": sum(1 for m in maxims if m < 50),
        "registres":        records,
        "perfil":           profile_context(),
    }


@mcp.tool
def get_stress(days: int = 7) -> dict:
    """
    Historial d'estrès dels últims N dies.
    Escala 0-100: 0-25 descans, 26-50 baix, 51-75 mig, 76-100 alt.
    days: 1-30 (per defecte 7)
    """
    api = get_garmin()
    records = []

    for i in range(days):
        d = days_ago(i)
        stats = safe_garmin(api.get_stats, d, default={})
        if stats and isinstance(stats, dict):
            avg = stats.get("averageStressLevel")
            if avg is not None:
                records.append({
                    "data":       d,
                    "estres_mig": avg,
                    "estres_max": stats.get("maxStressLevel"),
                    "nivell":     "alt" if avg > 75 else ("mig" if avg > 50 else ("baix" if avg > 25 else "descans")),
                })

    if not records:
        return {"error": "No hi ha dades d'estrès", "perfil": profile_context()}

    vals = [r["estres_mig"] for r in records if r.get("estres_mig")]
    return {
        "periode_dies":      days,
        "estres_mig_periode": round(sum(vals) / len(vals)) if vals else None,
        "dies_alt_estres":   sum(1 for v in vals if v > 75),
        "registres":         records,
        "perfil":            profile_context(),
    }


@mcp.tool
def get_heart_rate(days: int = 7) -> dict:
    """
    Historial de freqüència cardíaca en repòs dels últims N dies.
    La FC en repòs baixa indica millor condició cardiovascular.
    days: 1-30 (per defecte 7)
    """
    api = get_garmin()
    start = days_ago(days)
    raw = safe_garmin(api.get_rhr_day, start, today(), default=[])

    if not raw or not isinstance(raw, list):
        return {"error": "No hi ha dades de FC en repòs", "perfil": profile_context()}

    records = []
    for r in raw:
        val = r.get("value") or r.get("restingHeartRate")
        d   = r.get("statisticsStartDate") or r.get("calendarDate")
        if val and d:
            records.append({"data": d, "fc_repos": val})

    if not records:
        return {"error": "Cap registre de FC en repòs", "perfil": profile_context()}

    vals = [r["fc_repos"] for r in records]
    return {
        "periode_dies":   days,
        "fc_repos_mitja": round(sum(vals) / len(vals)),
        "fc_repos_minima": min(vals),
        "fc_repos_maxima": max(vals),
        "tendencia":      "baixant" if vals[0] > vals[-1] else ("pujant" if vals[0] < vals[-1] else "estable"),
        "registres":      records,
        "perfil":         profile_context(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EINES — RENDIMENT
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_vo2max() -> dict:
    """
    Obté el VO2max actual i l'edat de forma física (fitness age).
    El VO2max mesura la capacitat aeròbica màxima: com més alt, millor.
    """
    api = get_garmin()
    raw = safe_garmin(api.get_training_status, today(), default={})

    result = {"perfil": profile_context()}

    if raw and isinstance(raw, dict):
        ts = raw.get("trainingStatusDTO") or raw
        result.update({
            "vo2max":              ts.get("latestVO2Max") or ts.get("vo2MaxPreciseValue"),
            "edat_fitness":        ts.get("fitnessAge"),
            "llindar_lactat_fc":   ts.get("lactateThresholdHeartRate"),
            "estat_entrenament":   ts.get("trainingStatus"),
            "readiness":           ts.get("trainingReadiness") or ts.get("trainingReadinessScore"),
            "temps_recuperacio_h": ts.get("recoveryTime"),
        })

    if USER_AGE:
        vo2 = result.get("vo2max")
        if vo2:
            # Percentils orientatius per sexe/edat
            result["interpretacio"] = _interpret_vo2max(vo2, USER_AGE, USER_SEX)

    return result


def _interpret_vo2max(vo2: float, age: int, sex: str) -> str:
    """Interpretació orientativa del VO2max."""
    # Valors de referència simplificats (homes 50-59 anys)
    if age >= 50 and age < 60:
        if sex in ("home", "hombre"):
            if vo2 >= 46: return "excel·lent per a la teva edat"
            if vo2 >= 40: return "bo per a la teva edat"
            if vo2 >= 34: return "normal per a la teva edat"
            return "per sota de la mitjana — hi ha marge de millora"
        else:
            if vo2 >= 40: return "excel·lent per a la teva edat"
            if vo2 >= 34: return "bo per a la teva edat"
            if vo2 >= 28: return "normal per a la teva edat"
            return "per sota de la mitjana — hi ha marge de millora"
    return "consulta taules de referència per a la teva edat i sexe"


@mcp.tool
def get_training_status() -> dict:
    """
    Estat actual d'entrenament: training readiness, càrrega aguda/crònica,
    relació de càrrega i temps de recuperació recomanat.
    """
    api = get_garmin()
    ts_raw = safe_garmin(api.get_training_status, today(), default={})
    tl_raw = safe_garmin(api.get_training_load, today(), default={})

    result = {"perfil": profile_context()}

    if ts_raw and isinstance(ts_raw, dict):
        ts = ts_raw.get("trainingStatusDTO") or ts_raw
        result.update({
            "readiness":              ts.get("trainingReadiness") or ts.get("trainingReadinessScore"),
            "estat":                  ts.get("trainingStatus"),
            "temps_recuperacio_h":    ts.get("recoveryTime"),
            "llindar_lactat_fc":      ts.get("lactateThresholdHeartRate"),
        })

    if tl_raw and isinstance(tl_raw, dict):
        tl = tl_raw.get("trainingLoadDTO") or tl_raw
        result.update({
            "carrega_7dies":   tl.get("weeklyTrainingLoad") or tl.get("sevenDayLoad"),
            "carrega_aguda":   tl.get("acuteLoad"),
            "carrega_cronica": tl.get("chronicLoad"),
            "ratio_carrega":   tl.get("loadRatio"),
        })

    # Interpretació de la ràtio
    ratio = result.get("ratio_carrega")
    if ratio:
        if ratio < 0.8:
            result["interpretacio_carrega"] = "infraentrenament — pots augmentar la càrrega"
        elif ratio <= 1.3:
            result["interpretacio_carrega"] = "zona òptima — bona progressió sense risc"
        else:
            result["interpretacio_carrega"] = "sobreentrenament — redueix la intensitat"

    return result


@mcp.tool
def get_training_load(days: int = 28) -> dict:
    """
    Historial de càrrega d'entrenament dels últims N dies.
    Útil per veure tendències i detectar sobreentrenament o desentrenament.
    days: 7, 14 o 28
    """
    api = get_garmin()
    activities = safe_garmin(
        api.get_activities_by_date, days_ago(days), today(), default=[]
    )

    if not activities:
        return {"error": "No hi ha activitats al període", "perfil": profile_context()}

    weekly: dict = {}
    for a in activities:
        d     = (a.get("startTimeLocal") or "")[:10]
        if not d:
            continue
        week  = datetime.date.fromisoformat(d).strftime("%Y-W%V")
        cal   = a.get("calories") or 0
        dur   = round((a.get("duration") or 0) / 60)
        atype = ""
        if isinstance(a.get("activityType"), dict):
            atype = a["activityType"].get("typeKey", "")
        weekly.setdefault(week, {"calories": 0, "minuts": 0, "activitats": 0, "tipus": set()})
        weekly[week]["calories"]   += cal
        weekly[week]["minuts"]     += dur
        weekly[week]["activitats"] += 1
        if atype:
            weekly[week]["tipus"].add(atype)

    resum_setmanal = [
        {
            "setmana":    k,
            "calories":   v["calories"],
            "minuts":     v["minuts"],
            "activitats": v["activitats"],
            "tipus":      list(v["tipus"]),
        }
        for k, v in sorted(weekly.items())
    ]

    return {
        "periode_dies":    days,
        "total_activitats": len(activities),
        "resum_setmanal":  resum_setmanal,
        "perfil":          profile_context(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EINES — PES
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_weight(days: int = 30) -> dict:
    """
    Historial de pes i composició corporal dels últims N dies.
    Inclou: pes, IMC, % greix corporal, massa muscular i massa òssia.
    days: 7-90 (per defecte 30)
    """
    api = get_garmin()
    raw = safe_garmin(
        api.get_body_composition, days_ago(days), today(), default={}
    )

    if not raw or not isinstance(raw, dict):
        return {"error": "No hi ha dades de pes", "perfil": profile_context()}

    entries = raw.get("dateWeightList") or []
    if not isinstance(entries, list):
        entries = []

    records = []
    for w in entries:
        wkg = w.get("weight")
        if wkg and wkg > 500:
            wkg = wkg / 1000  # Garmin a vegades retorna en grams
        if wkg:
            records.append({
                "data":          w.get("calendarDate") or w.get("date"),
                "pes_kg":        round(float(wkg), 1),
                "imc":           w.get("bmi"),
                "greix_pct":     w.get("bodyFat"),
                "musculatura_kg": w.get("muscleMass"),
                "massa_ossia_kg": w.get("boneMass"),
            })

    if not records:
        return {"error": "Cap registre de pes al període", "perfil": profile_context()}

    pesos = [r["pes_kg"] for r in records if r["pes_kg"]]
    return {
        "periode_dies":    days,
        "pes_actual":      records[0]["pes_kg"] if records else None,
        "pes_inicial":     records[-1]["pes_kg"] if records else None,
        "variacio_kg":     round(records[0]["pes_kg"] - records[-1]["pes_kg"], 1) if len(records) > 1 else 0,
        "pes_mig":         round(sum(pesos) / len(pesos), 1) if pesos else None,
        "registres":       records,
        "perfil":          profile_context(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# EINES — PERFIL
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_user_profile() -> dict:
    """
    Retorna el perfil personal de l'usuari configurat al servidor.
    Inclou edat, sexe, alçada, pes i objectiu principal.
    Usa aquesta eina per personalitzar qualsevol recomanació.
    """
    return {
        "nom":      USER_NAME  or None,
        "edat":     USER_AGE   or None,
        "sexe":     USER_SEX   or None,
        "alcada_cm": USER_HEIGHT or None,
        "pes_kg":   USER_WEIGHT or None,
        "objectiu": USER_GOAL  or None,
        "idioma":   USER_LANG,
        "nota":     (
            f"Aquesta persona té {USER_AGE} anys, és {USER_SEX}, "
            f"{'mesura ' + str(USER_HEIGHT) + 'cm, ' if USER_HEIGHT else ''}"
            f"{'pesa ' + str(USER_WEIGHT) + 'kg, ' if USER_WEIGHT else ''}"
            f"objectiu: {USER_GOAL}. "
            "Tingues en compte el seu perfil en totes les recomanacions."
        ) if USER_AGE else "Perfil no configurat al servidor."
    }


# ══════════════════════════════════════════════════════════════════════════════
# EINA PRINCIPAL — SNAPSHOT COMPLET
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool
def get_full_snapshot(days: int = 7) -> dict:
    """
    Snapshot complet de salut i rendiment dels últims N dies.
    Combina: son, HRV, activitat, Body Battery, estrès, FC en repòs i VO2max.
    Usa aquesta eina quan l'usuari demana un resum general o vol saber com està.
    days: 7 o 14 (per defecte 7)
    """
    api = get_garmin()
    snapshot = {
        "data_generacio": datetime.datetime.now().isoformat(),
        "periode_dies":   days,
        "perfil":         get_user_profile(),
    }

    # Son (últim disponible)
    snapshot["son_avui"] = get_sleep()

    # Resum de son
    snapshot["resum_son"] = get_sleep_summary(days)

    # Stats avui
    snapshot["stats_avui"] = get_today_stats()

    # Body Battery
    snapshot["body_battery"] = get_body_battery(days)

    # Activitats
    snapshot["activitats"] = get_activities(days)

    # Rendiment
    snapshot["rendiment"] = get_training_status()

    # VO2max
    snapshot["vo2max"] = get_vo2max()

    # Instruccions per a la IA
    lang_note = "en català" if USER_LANG == "ca" else "en español"
    snapshot["instruccions_ia"] = (
        f"Ets un coach personal expert en salut i fitness. "
        f"Analitza aquestes dades reals de Garmin i respon {lang_note}. "
        f"L'usuari és: {profile_context()} "
        f"Sigues concret, pràctic i personalitzat. "
        f"Si detectes alertes (poc son, HRV baix, sobreentrenament), menciona-les."
    )

    return snapshot


# ══════════════════════════════════════════════════════════════════════════════
# AUTENTICACIÓ PER TOKEN
# ══════════════════════════════════════════════════════════════════════════════

# FastMCP gestiona el transport SSE/HTTP; afegim middleware de token
from starlette.middleware.base import BaseHTTPMiddleware

class TokenAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Health check públic
        if request.url.path in ("/", "/health"):
            return await call_next(request)

        # Comprova token a query string o header
        token = (
            request.query_params.get("token")
            or request.headers.get("X-MCP-Token")
            or request.headers.get("Authorization", "").replace("Bearer ", "")
        )

        if not token or not secrets.compare_digest(
            hashlib.sha256(token.encode()).digest(),
            hashlib.sha256(MCP_TOKEN.encode()).digest()
        ):
            return JSONResponse(
                {"error": "Token invàlid. Afegeix ?token=EL_TEU_TOKEN a la URL"},
                status_code=401
            )

        return await call_next(request)


# ══════════════════════════════════════════════════════════════════════════════
# APLICACIÓ STARLETTE (per a Render)
# ══════════════════════════════════════════════════════════════════════════════

from starlette.applications import Starlette
from starlette.routing import Route, Mount

async def health(request):
    return JSONResponse({
        "status": "ok",
        "server": "Garmin Coach IA MCP",
        "eines":  18,
        "usuari": USER_NAME or "no configurat",
        "token_hint": MCP_TOKEN[:8] + "..." + MCP_TOKEN[-4:],
    })

# Construeix l'app amb el servidor MCP muntat
mcp_app = mcp.http_app(path="/mcp")

app = Starlette(
    routes=[
        Route("/", health),
        Route("/health", health),
        Mount("/", app=mcp_app),
    ]
)

app.add_middleware(TokenAuthMiddleware)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
