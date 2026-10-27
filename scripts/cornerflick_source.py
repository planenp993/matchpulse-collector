"""Validate openly published Cornerflick football JSON exports.

Source publishes its *compilation* under CC BY 4.0, but the original data
provider's rights remain separate. This file performs a one-time connectivity
test and offline parsing; it does not archive, redistribute or bulk scrape data.
"""
import datetime as dt
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://cornerflick.com"
SEASONS = {"Premier League": "premier-league", "La Liga": "la-liga"}
KEYS = {
    "Possession": ("possession_home", "possession_away", "percent"),
    "Shots": ("shots_home", "shots_away", "count"),
    "Shots on Target": ("shots_on_target_home", "shots_on_target_away", "count"),
    "xG": ("xg_home", "xg_away", "xg"),
    "Corners": ("corners_home", "corners_away", "count"),
    "Yellow Cards": ("yellow_home", "yellow_away", "count"),
    "Red Cards": ("red_home", "red_away", "count"),
    "Fouls": ("fouls_home", "fouls_away", "count"),
    "Offsides": ("offsides_home", "offsides_away", "count"),
    "Passes": ("passes_home", "passes_away", "count"),
}
MAX_RESPONSE = 1500000


def safe_public_url(url):
    split = urllib.parse.urlsplit(url)
    if split.scheme != "https" or split.netloc != "cornerflick.com":
        raise ValueError("Only published Cornerflick export URLs allowed")
    if split.query or split.fragment or ".." in split.path:
        raise ValueError("Invalid URL")
    pattern = (r"/football/leagues/[a-z0-9-]+/results/season[.]json|"
               r"/football/[a-z0-9-]+/matches/[a-z0-9-]+/data[.]json")
    if re.fullmatch(pattern, split.path) is None:
        raise ValueError("Not an advertised JSON export")
    return url


def fetch_json(url):
    safe_public_url(url)
    req = urllib.request.Request(url, method="GET", headers={
        "User-Agent": "MATCHPULSE-collector/0.1 (one-time public CC-BY export test)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=12) as res:
        final_url = res.geturl()
        safe_public_url(final_url)
        if res.getcode() != 200 or "json" not in res.headers.get("Content-Type", "").lower():
            raise ValueError("Not an HTTP 200 JSON response")
        buf = res.read(MAX_RESPONSE + 1)
        if len(buf) > MAX_RESPONSE:
            raise ValueError("JSON export too large")
    data = json.loads(buf)
    if not isinstance(data, dict):
        raise ValueError("Invalid document type")
    return data


def _number(v, kind):
    if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
        raise ValueError("Invalid numeric statistic")
    maximum = 100 if kind == "percent" else 30 if kind == "xg" else 3000
    if v > maximum or (kind == "count" and int(v) != v):
        raise ValueError("Statistic outside range")
    return v


def parse_match(doc):
    if not isinstance(doc, dict):
        raise ValueError("Invalid match document")
    match, teams, meta = doc.get("match") or {}, doc.get("teams") or {}, doc.get("meta") or {}
    if match.get("status") != "finished":
        raise ValueError("Only full-time games can be imported")
    home, away = teams.get("home") or {}, teams.get("away") or {}
    if not home.get("name") or not away.get("name") or home["name"] == away["name"]:
        raise ValueError("Invalid teams")
    score = match.get("score") or {}
    if any(type(score.get(side)) is not int or score[side] < 0 for side in ("home", "away")):
        raise ValueError("Invalid score")
    kickoff = dt.datetime.fromisoformat(match["kickoff_at"].replace("Z", "+00:00"))
    if kickoff.tzinfo is None:
        raise ValueError("Kickoff must be timezone-aware")
    values = {}
    stats = doc.get("statistics") or []
    if not isinstance(stats, list):
        raise ValueError("Invalid statistics array")
    for item in stats:
        if not isinstance(item, dict):
            raise ValueError("Malformed statistics item")
        mapping = KEYS.get(item.get("label"))
        if mapping is None:
            continue
        h, a, kind = mapping
        for key, value in ((h, item.get("home")), (a, item.get("away"))):
            if value is None:
                continue
            parsed = _number(value, kind)
            if key in values and values[key] != parsed:
                raise ValueError("Conflicting statistic")
            values[key] = parsed
    for side in ("home", "away"):
        if (f"shots_{side}" in values and f"shots_on_target_{side}" in values
                and values[f"shots_on_target_{side}"] > values[f"shots_{side}"]):
            raise ValueError("Shots-on-target exceeds all shots")
    return {
        "external_id": match.get("id"),
        "league": (match.get("competition") or {}).get("name"),
        "date": kickoff.date().isoformat(),
        "kickoff_utc": kickoff.astimezone(dt.timezone.utc).isoformat(),
        "home": home["name"], "away": away["name"],
        "home_goals": score["home"], "away_goals": score["away"],
        "statistics": values,
        "provenance": {"publisher": meta.get("publisher"), "origin": meta.get("source"),
                       "license": meta.get("license"), "last_updated": meta.get("last_updated_at"),
                       "attribution": meta.get("attribution")},
    }


def newest_finished(season_doc):
    """Only follow explicit match exports listed in season index."""
    items = season_doc.get("matches")
    if not isinstance(items, list):
        raise ValueError("Season index missing matches")
    candidates = [m for m in items if isinstance(m, dict) and m.get("status") == "finished"
                  and isinstance(m.get("dataset_url"), str)]
    candidates.sort(key=lambda m: m.get("kickoff_at") or "", reverse=True)
    if not candidates:
        return None, len(items)
    return safe_public_url(candidates[0]["dataset_url"]), len(items)


def audit_once():
    for title, slug in SEASONS.items():
        try:
            source = fetch_json(f"{BASE}/football/leagues/{slug}/results/season.json")
            link, total = newest_finished(source)
            if not link:
                result = {"league": title, "status": "no_finished_match", "season_rows": total}
            else:
                match = parse_match(fetch_json(link))
                result = {
                    "league": title,
                    "status": "readable",
                    "season_rows": total,
                    "latest_match_date": match["date"],
                    "stats_fields": sorted(match["statistics"]),
                    "has_xg": "xg_home" in match["statistics"] and "xg_away" in match["statistics"],
                    "data_origin": match["provenance"]["origin"],
                    "license": match["provenance"]["license"],
                    "last_updated_at": match["provenance"]["last_updated"],
                }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                ValueError, KeyError, TypeError, OSError) as exc:
            result = {"league": title, "status": "failed", "error_type": type(exc).__name__,
                      "http": getattr(exc, "code", None)}
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    audit_once()
