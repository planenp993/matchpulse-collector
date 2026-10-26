#!/usr/bin/env python3
"""Independent OpenFootball CC0 fixtures/results collector for MATCHPULSE."""
import argparse
import datetime as dt
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

SOURCE = "https://raw.githubusercontent.com/openfootball/football.json/master"
SEASON = "2026-27"
LEAGUES = {
    "E0": ("en.1", "England", "Premier League", "Europe/London"),
    "D1": ("de.1", "Germany", "Bundesliga", "Europe/Berlin"),
    "SP1": ("es.1", "Spain", "La Liga", "Europe/Madrid"),
    "I1": ("it.1", "Italy", "Serie A", "Europe/Rome"),
}
STATS = ("shots_home", "shots_away", "shots_on_target_home", "shots_on_target_away",
         "xg_home", "xg_away", "corners_home", "corners_away", "yellow_home",
         "yellow_away", "red_home", "red_away", "possession_home", "possession_away")


def match_id(league, season, date, home, away):
    raw = "|".join([league, season, date, home.strip().casefold(), away.strip().casefold()])
    return "mp:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def utc_kickoff(date, time, timezone):
    if not time:
        return None
    if not isinstance(time, str) or len(time) != 5:
        raise ValueError("Invalid kickoff time")
    local = dt.datetime.fromisoformat(f"{date}T{time}").replace(tzinfo=ZoneInfo(timezone))
    return local.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_source(raw, league, season=SEASON):
    if not isinstance(raw, dict) or not isinstance(raw.get("matches"), list):
        raise ValueError("Invalid source payload")
    slug, country, league_name, timezone = LEAGUES[league]
    parsed = []
    seen = set()
    for item in raw["matches"]:
        date, home, away = item["date"], item["team1"], item["team2"]
        dt.date.fromisoformat(date)
        if not all(isinstance(x, str) and x.strip() for x in (home, away)) or home == away:
            raise ValueError("Invalid clubs")
        score = item.get("score")
        ft = score.get("ft") if isinstance(score, dict) else None
        if ft is not None and (not isinstance(ft, list) or len(ft) != 2 or any(type(v) is not int or v < 0 for v in ft)):
            raise ValueError("Invalid final score")
        identity = match_id(league, season, date, home, away)
        if identity in seen:
            raise ValueError(f"Duplicate match ID: {identity}")
        seen.add(identity)
        time = item.get("time") or None
        parsed.append({
            "id": identity, "league_code": league, "league": league_name, "country": country,
            "season": season, "date": date, "time_local": time, "timezone": timezone,
            "kickoff_utc": utc_kickoff(date, time, timezone),
            "home": home, "away": away,
            "status": "finished" if ft is not None else "scheduled",
            "home_goals": ft[0] if ft is not None else None,
            "away_goals": ft[1] if ft is not None else None,
            "statistics": {},
            "source": "openfootball/football.json",
            "source_url": f"{SOURCE}/{season}/{slug}.json",
        })
    return parsed


def fetch_source(url, timeout=15):
    if not url.startswith(SOURCE + "/" + SEASON + "/"):
        raise ValueError("Unapproved provider URL")
    req = urllib.request.Request(url, headers={"User-Agent": "MatchpulseCollector/0.1 OpenFootball CC0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def import_authorized_stats(matches, payload):
    """Optional opt-in data import, never scrape protected services."""
    if not isinstance(payload, dict) or not payload.get("source") or not payload.get("permission_note"):
        raise ValueError("Statistics need source and permission_note")
    records = payload.get("matches")
    if not isinstance(records, list):
        raise ValueError("Invalid statistics records")
    indexed = {match["id"]: match for match in matches}
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("statistics"), dict):
            raise ValueError("Malformed statistics record")
        match = indexed.get(row.get("match_id"))
        if not match or match["status"] != "finished":
            raise ValueError("Unmatched or unfinished match")
        observations = {}
        for name, value in row["statistics"].items():
            if name not in STATS:
                raise ValueError(f"Unknown statistics field: {name}")
            if value is None:
                continue
            if type(value) not in (int, float) or not 0 <= value <= 10000:
                raise ValueError(f"Invalid statistic: {name}")
            if name.startswith("possession_") and value > 100:
                raise ValueError("Possession must be a percentage")
            observations[name] = value
        match["statistics"].update(observations)
        match["statistics_source"] = {"name": payload["source"], "permission_note": payload["permission_note"]}


def build_snapshot(raw_by_league, prior=None, stats_payload=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    matches, errors, successful = [], {}, set()
    for league in LEAGUES:
        raw = raw_by_league.get(league)
        if raw is None:
            errors[league] = "Source unavailable"
            continue
        try:
            parsed = parse_source(raw, league)
            if not parsed:
                raise ValueError("Empty league feed")
            matches.extend(parsed)
            successful.add(league)
        except (ValueError, KeyError, TypeError) as exc:
            errors[league] = f"Bad data: {exc}"
    current_by_id = {m["id"]: m for m in matches}
    if prior:
        for old in prior.get("matches", []):
            if old.get("league_code") not in LEAGUES:
                continue
            if old["league_code"] not in successful:
                if old["id"] not in current_by_id:
                    matches.append(old)
            elif old["id"] in current_by_id and old.get("statistics"):
                new = current_by_id[old["id"]]
                if (new["status"] == "finished" and
                    old.get("home_goals") == new["home_goals"] and
                    old.get("away_goals") == new["away_goals"]):
                    new["statistics"] = old["statistics"]
                    if old.get("statistics_source"):
                        new["statistics_source"] = old["statistics_source"]
    if not matches:
        raise RuntimeError("All feeds unavailable; existing data will not be overwritten")
    if stats_payload is not None:
        import_authorized_stats(matches, stats_payload)
    matches.sort(key=lambda m: (m["date"], m["time_local"] or "", m["league_code"], m["id"]))
    return {
        "schema_version": 1,
        "source": "openfootball/football.json",
        "license": "CC0-1.0; optional statistics retain their original permissions",
        "season": SEASON,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "status": "ok" if not errors else "partial",
        "errors": errors,
        "leagues_ok": len(successful),
        "matches_count": len(matches),
        "finished_count": sum(m["status"] == "finished" for m in matches),
        "scheduled_count": sum(m["status"] == "scheduled" for m in matches),
        "stats_count": sum(bool(m["statistics"]) for m in matches),
        "matches": matches,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--stats-file", help="Manually provided authorized statistics JSON")
    parser.add_argument("--output", default="data/latest.json")
    args = parser.parse_args()
    if not args.online:
        parser.error("Use --online to fetch public data")
    feeds = {}
    for code, (slug, _, _, _) in LEAGUES.items():
        try:
            feeds[code] = fetch_source(f"{SOURCE}/{SEASON}/{slug}.json")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            print(f"WARNING {code}: {exc}", file=sys.stderr)
    output = Path(args.output)
    previous = json.loads(output.read_text("utf-8")) if output.exists() else None
    stats = json.loads(Path(args.stats_file).read_text("utf-8")) if args.stats_file else None
    snapshot = build_snapshot(feeds, prior=previous, stats_payload=stats)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Status: {snapshot['status']}; games: {snapshot['matches_count']}; stats: {snapshot['stats_count']}")


if __name__ == "__main__":
    main()
