"""Bounded, one-off FotMob connectivity diagnostic and offline stats parser.

No scheduled FotMob collection, retries, proxy pools, browser impersonation,
authentication bypass, or copying provider data into the public repository.
FotMob disallows automated / systematic access in its terms. This is a
diagnostic experiment, NOT an approved data source.
"""
import argparse
import datetime as dt
import json
import math
import re
import urllib.error
import urllib.request

BASE = "https://www.fotmob.com/api/data/"
LEAGUES = {47: "Premier League", 54: "Bundesliga", 87: "La Liga", 55: "Serie A"}
MAP = {
    "expected goals (xg)": ("xg_home", "xg_away", "decimal"),
    "expected goals": ("xg_home", "xg_away", "decimal"),
    "xg": ("xg_home", "xg_away", "decimal"),
    "total shots": ("shots_home", "shots_away", "integer"),
    "shots": ("shots_home", "shots_away", "integer"),
    "shots on target": ("shots_on_target_home", "shots_on_target_away", "integer"),
    "shots on goal": ("shots_on_target_home", "shots_on_target_away", "integer"),
    "corner kicks": ("corners_home", "corners_away", "integer"),
    "corners": ("corners_home", "corners_away", "integer"),
    "yellow cards": ("yellow_home", "yellow_away", "integer"),
    "red cards": ("red_home", "red_away", "integer"),
    "ball possession": ("possession_home", "possession_away", "percent"),
    "possession": ("possession_home", "possession_away", "percent"),
}


class AccessUnavailable(Exception):
    pass


def get_json(endpoint, *, opener=None):
    # Fixed whitelist; no URL/path passthrough from user-controlled input.
    if not (endpoint.startswith("matches?date=") and re.fullmatch(r"matches\?date=\d{8}", endpoint)
            or endpoint.startswith("matchDetails?matchId=")
            and re.fullmatch(r"matchDetails\?matchId=\d{5,12}", endpoint)):
        raise ValueError("Unsupported endpoint")
    request = urllib.request.Request(BASE + endpoint, headers={
        "Accept": "application/json",
        "User-Agent": "MATCHPULSE-one-off-probe/0.1 (no retry)"
    })
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(request, timeout=12) as response:
            if response.getcode() != 200:
                raise AccessUnavailable("HTTP " + str(response.getcode()))
            if "json" not in response.headers.get("Content-Type", "").lower():
                raise AccessUnavailable("Response is not JSON")
            value = json.load(response)
            if not isinstance(value, dict):
                raise ValueError("Unexpected provider schema")
            return value
    except urllib.error.HTTPError as exc:
        raise AccessUnavailable(f"HTTP {exc.code} (stopped, no retry)") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AccessUnavailable(f"Network unavailable ({type(exc).__name__}); no retry") from None


def normalize_label(label):
    return " ".join(str(label).strip().lower().replace("–", "-").split())


def number(value, kind):
    if type(value) is bool:
        raise ValueError("Boolean statistic")
    if isinstance(value, str):
        value = value.strip().replace("%", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", value):
            raise ValueError("Invalid numeric string")
        value = float(value)
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid numeric value")
    if value > (100 if kind == "percent" else 30 if kind == "decimal" else 500):
        raise ValueError("Value outside expected range")
    if kind == "integer" and int(value) != value:
        raise ValueError("Fractional count")
    return int(value) if kind == "integer" else float(value)


def parse_match_stats(document):
    """Read only full-match stats, never infer missing xG or add halves together."""
    groups = (((document.get("content") or {}).get("stats") or {})
              .get("Periods") or {}).get("All")
    if not isinstance(groups, dict) or not isinstance(groups.get("stats"), list):
        raise ValueError("Missing full-match statistics")
    out = {}
    for section in groups["stats"]:
        if not isinstance(section, dict):
            continue
        lines = section.get("stats")
        if not isinstance(lines, list):
            continue
        # The normal shape is a group {title:'Shots',stats:[{title:'Total shots',stats:[14,9]}]}
        for item in lines:
            if not isinstance(item, dict):
                continue
            label = normalize_label(item.get("title") or item.get("key") or "")
            spec = MAP.get(label)
            if not spec:
                continue
            pair = item.get("stats")
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            if pair[0] is None or pair[1] is None:
                continue
            k1, k2, kind = spec
            for k, value in ((k1, number(pair[0],kind)), (k2, number(pair[1],kind))):
                if k in out and not math.isclose(out[k], value, abs_tol=1e-9):
                    raise ValueError("Conflicting duplicate stat: " + k)
                out[k] = value
    for side in ("home", "away"):
        if ("shots_" + side in out and "shots_on_target_" + side in out and
            out["shots_on_target_" + side] > out["shots_" + side]):
            raise ValueError("On target exceeds total shots")
    return out


def parse_matches(document):
    if not isinstance(document.get("leagues"), list):
        raise ValueError("Missing leagues list")
    found = []
    for league in document["leagues"]:
        if not isinstance(league, dict):
            continue
        try:
            league_id = int(league.get("primaryId", league.get("id")))
        except (TypeError, ValueError):
            continue
        if league_id not in LEAGUES:
            continue
        for game in league.get("matches", []):
            if not isinstance(game, dict):
                continue
            status = game.get("status") or {}
            if status.get("finished") is not True or type(game.get("id")) is not int:
                continue
            home, away = game.get("home"), game.get("away")
            if not (isinstance(home, dict) and isinstance(away, dict)):
                continue
            found.append({"id": game["id"], "league": LEAGUES[league_id],
                          "home": home.get("name"), "away": away.get("name")})
    return found


def run_probe(date, fetcher=get_json):
    dt.datetime.strptime(date, "%Y%m%d")
    # Strictly capped: 1 daily list request, then at most 1 details request.
    listing = fetcher("matches?date=" + date)
    leagues = listing.get("leagues")
    if not isinstance(leagues, list):
        raise ValueError("Invalid fixture response")
    finished = parse_matches(listing)
    report = {"source": "FotMob (unofficial, diagnostic only)", "date": date,
              "calendar_accessible": True, "league_groups": len(leagues),
              "finished_eligible_matches": len(finished),
              "details_attempted": False, "statistics": {}, "warning": None}
    if finished:
        item = finished[0]
        report["details_attempted"] = True
        detail = fetcher("matchDetails?matchId=" + str(item["id"]))
        try:
            stats = parse_match_stats(detail)
            report["statistics"] = stats
            report["details_league"] = item["league"]
            report["details_match"] = f"{item['home']} vs {item['away']}"
        except ValueError as exc:
            report["warning"] = f"Stats absent or changed format: {exc}"
    else:
        report["warning"] = "No finished matches in initial four leagues for this date"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="20261026", help="YYYYMMDD; one day, 2 calls max")
    args = parser.parse_args()
    try:
        result = run_probe(args.date)
        result["status"] = "ok" if result["statistics"] else "partial"
        print(json.dumps(result, ensure_ascii=False))
    except (AccessUnavailable, ValueError) as exc:
        print(json.dumps({"source": "FotMob", "status": "unavailable",
                          "reason": str(exc), "stopped_without_retry": True}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
