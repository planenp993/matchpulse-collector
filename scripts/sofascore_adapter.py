"""Offline SofaScore-format adapter. No provider requests, scraping or redistribution.

Accepts locally supplied exports only when use is authorized. A verified event-ID
crosswalk, exact club identities, date and score checks prevent unsafe joins.
"""
import argparse
import datetime as dt
import json
import math
import re
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

# IMPORTANT: totalShotsOnGoal is ALL attempts in SofaScore; shotsOnGoal is on-target.
KEYS = {
    "totalShotsOnGoal": ("shots_home", "shots_away", "int"),
    "shotsOnGoal": ("shots_on_target_home", "shots_on_target_away", "int"),
    "expectedGoals": ("xg_home", "xg_away", "float"),
    "cornerKicks": ("corners_home", "corners_away", "int"),
    "yellowCards": ("yellow_home", "yellow_away", "int"),
    "redCards": ("red_home", "red_away", "int"),
    "ballPossession": ("possession_home", "possession_away", "percent"),
}


def parse_number(value, kind):
    if type(value) is bool:
        raise ValueError("Boolean is not a statistic")
    if isinstance(value, str):
        if not re.fullmatch(r"\d+(?:\.\d+)?", value.strip()):
            raise ValueError("Unparseable numeric statistic")
        value = float(value)
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid numeric statistic")
    if value > (100 if kind == "percent" else 30 if kind == "float" else 500):
        raise ValueError("Statistic outside range")
    if kind == "int" and int(value) != value:
        raise ValueError("Fractional count")
    return int(value) if kind == "int" else float(value)


def normalize_statistics(payload):
    """Full-time ALL only, not 1ST+2ND; duplicate overview keys checked for agreement."""
    if not isinstance(payload, dict) or not isinstance(payload.get("statistics"), list):
        raise ValueError("Invalid statistics document")
    periods = [p for p in payload["statistics"] if isinstance(p, dict) and p.get("period") == "ALL"]
    if len(periods) != 1:
        raise ValueError("Exactly one ALL period required")
    out = {}
    for group in periods[0].get("groups", []):
        if not isinstance(group, dict):
            raise ValueError("Invalid statistics group")
        for item in group.get("statisticsItems", []):
            if not isinstance(item, dict):
                raise ValueError("Invalid item")
            definition = KEYS.get(item.get("key"))
            if not definition:
                continue
            if "homeValue" not in item or "awayValue" not in item:
                continue
            if item["homeValue"] is None or item["awayValue"] is None:
                continue
            home_key, away_key, kind = definition
            for key, value in ((home_key, parse_number(item["homeValue"], kind)),
                               (away_key, parse_number(item["awayValue"], kind))):
                if key in out and not math.isclose(out[key], value, abs_tol=1e-9):
                    raise ValueError("Conflicting duplicate statistic: " + key)
                out[key] = value
    for side in ("home", "away"):
        if ("shots_" + side in out and "shots_on_target_" + side in out
                and out["shots_on_target_" + side] > out["shots_" + side]):
            raise ValueError("On-target shots exceed total shots")
    return out


def normalize_event(event):
    if not isinstance(event, dict) or type(event.get("id")) is not int:
        raise ValueError("Missing event ID")
    stamp = event.get("startTimestamp")
    if type(stamp) is not int or not 946684800 <= stamp <= 4102444800:
        raise ValueError("Invalid event UTC timestamp")
    teams = [event.get("homeTeam"), event.get("awayTeam")]
    names = [t.get("name") if isinstance(t, dict) else None for t in teams]
    if not all(isinstance(n, str) and n.strip() for n in names) or names[0] == names[1]:
        raise ValueError("Invalid clubs")
    utc = dt.datetime.fromtimestamp(stamp, tz=dt.timezone.utc)
    sofia = utc.astimezone(ZoneInfo("Europe/Sofia"))
    status = event.get("status")
    tournament = event.get("tournament")
    return {
        "source_event_id": event["id"], "home": names[0].strip(), "away": names[1].strip(),
        "league": tournament.get("name") if isinstance(tournament, dict) else None,
        "kickoff_utc": utc.isoformat().replace("+00:00", "Z"),
        "kickoff_sofia": sofia.isoformat(), "date_sofia": sofia.date().isoformat(),
        "status": status.get("type", "unknown") if isinstance(status, dict) else "unknown",
    }


def club_identity(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c)).casefold()
    return " ".join(token for token in re.sub("[^a-z0-9 ]", " ", name).split()
                    if token not in ("fc", "cf"))


def verify_join(event, match):
    fixture = normalize_event(event)
    if match.get("status") != "finished":
        raise ValueError("Only finished matches can be enriched")
    for k in ("home", "away"):
        if club_identity(fixture[k]) != club_identity(match.get(k, "")):
            raise ValueError("Different " + k + " club")
    date = dt.date.fromisoformat(match["date"])
    kickoff_date = dt.datetime.fromisoformat(fixture["kickoff_utc"].replace("Z", "+00:00")).date()
    if abs((date - kickoff_date).days) > 1:
        raise ValueError("Dates do not match")
    for k, target in (("homeScore", "home_goals"), ("awayScore", "away_goals")):
        score = event.get(k)
        score = score.get("current") if isinstance(score, dict) else None
        if score is not None and score != match[target]:
            raise ValueError("Conflicting final score")
    return fixture


def convert_bundle(bundle, mapping, snapshot, permission_note):
    if not isinstance(permission_note, str) or not permission_note.strip():
        raise ValueError("Permission note required")
    if not isinstance(bundle, dict) or not isinstance(bundle.get("events"), list):
        raise ValueError("Need events array")
    if not isinstance(mapping, dict) or not isinstance(snapshot, dict):
        raise ValueError("Invalid crosswalk or collector snapshot")
    matches = {m["id"]: m for m in snapshot.get("matches", [])}
    previews, imports, seen_events, used_targets = [], [], set(), set()
    for entry in bundle["events"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("event"), dict):
            raise ValueError("Invalid event document")
        event = entry["event"]
        preview = normalize_event(event)
        event_id = str(preview["source_event_id"])
        if event_id in seen_events:
            raise ValueError("Duplicate event")
        seen_events.add(event_id)
        stats = normalize_statistics(entry["statistics"]) if "statistics" in entry else {}
        preview["statistics_fields"] = len(stats)
        previews.append(preview)
        if event_id not in mapping:
            continue
        target_id = mapping[event_id]
        if target_id in used_targets:
            raise ValueError("Duplicate target match")
        used_targets.add(target_id)
        match = matches.get(target_id)
        if match is None:
            raise ValueError("Unknown target match")
        verify_join(event, match)
        if stats:
            imports.append({"match_id": target_id, "source_event_id": int(event_id), "statistics": stats})
    return {
        "source": "SofaScore-format authorized local export",
        "permission_note": permission_note,
        "matches": imports,
        "fixture_previews": previews,
        "coverage": {
            "events": len(previews), "explicitly_mapped": sum(str(p["source_event_id"]) in mapping for p in previews),
            "enriched_matches": len(imports),
            "with_xg": sum("xg_home" in m["statistics"] and "xg_away" in m["statistics"] for m in imports),
            "with_shots": sum("shots_home" in m["statistics"] and "shots_away" in m["statistics"] for m in imports),
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--snapshot", type=Path, default=Path("data/latest.json"))
    parser.add_argument("--permission-note", required=True)
    parser.add_argument("--output", type=Path, default=Path("local/sofascore_import.json"))
    args = parser.parse_args()
    converted = convert_bundle(json.loads(args.input.read_text("utf-8")),
                               json.loads(args.mapping.read_text("utf-8")),
                               json.loads(args.snapshot.read_text("utf-8")),
                               args.permission_note)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(converted, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print("SofaScore-format:", converted["coverage"])


if __name__ == "__main__":
    main()
