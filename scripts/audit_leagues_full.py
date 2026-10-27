"""One-off factual coverage audit of Cornerflick public competition exports.

Reads published season indexes for 18 catalogue competitions and 2 match
records per competition. Crosschecks four leagues vs public-domain
OpenFootball results, and highlights anomalies. Only aggregate diagnostic
metadata is printed; no third-party records are stored or redistributed.
No retries, bypass, proxy or authentication. No scheduled execution.
"""
import collections
import datetime as dt
import json
import re
import unicodedata
import urllib.error
import urllib.request

from scripts.cornerflick_source import BASE, fetch_json, parse_match

COMPETITIONS = {
    "Premier League": "premier-league",
    "La Liga": "la-liga",
    "Serie A": "serie-a",
    "Bundesliga": "bundesliga",
    "Ligue 1": "ligue-1",
    "Champions League": "champions-league",
    "Europa League": "europa-league",
    "Conference League": "conference-league",
    "Eredivisie": "eredivisie",
    "Süper Lig": "super-lig",
    "Saudi Pro League": "saudi-pro-league",
    "J1 League": "j1-league",
    "AFC Champions League": "afc-champions-league",
    "Africa Cup of Nations": "africa-cup-of-nations",
    "Copa Libertadores": "copa-libertadores",
    "Brasileirão": "brasileirao",
    "MLS": "mls",
    "Primeira Liga": "primeira-liga",
}
OPENFOOTBALL = {
    "Premier League": "en.1",
    "La Liga": "es.1",
    "Serie A": "it.1",
    "Bundesliga": "de.1",
}
SOURCE_PREFIX = "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/"

def normalize(s):
    s = "".join(x for x in unicodedata.normalize("NFKD", s) if not unicodedata.combining(x))
    return "".join(re.findall(r"[a-z0-9]+", s.lower()))

def compare_pair(a, b):
    """Exact normalized clubs, calendar date within 1 day, same score."""
    if normalize(a["home"]) != normalize(b["home"]) or normalize(a["away"]) != normalize(b["away"]):
        return False
    if abs((dt.date.fromisoformat(a["date"]) - dt.date.fromisoformat(b["date"])).days) > 1:
        return False
    return True

def get_openfootball(slug):
    req = urllib.request.Request(SOURCE_PREFIX + slug + ".json", headers={
        "User-Agent": "MATCHPULSE-collector/0.1 (one-time independent results validation)",
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as res:
        raw = json.loads(res.read(1500000))
    result = []
    for x in raw.get("matches", []):
        score = x.get("score", {}).get("ft") if isinstance(x.get("score"), dict) else None
        if not isinstance(score, list) or len(score) != 2:
            continue
        result.append({"date": x["date"], "home": x["team1"], "away": x["team2"],
                       "home_goals": score[0], "away_goals": score[1]})
    return result

def compare_league(rows, reference):
    ref_index = collections.defaultdict(list)
    for r in reference:
        ref_index[(normalize(r["home"]), normalize(r["away"]))].append(r)
    matched = 0
    discrepant = []
    unmatched = []
    for m in rows:
        options = ref_index.get((normalize(m["home_team"]), normalize(m["away_team"])), [])
        options = [o for o in options if abs((dt.date.fromisoformat(m["kickoff_at"][:10]) -
                                             dt.date.fromisoformat(o["date"])).days) <= 1]
        if not options:
            unmatched.append({"date": m["kickoff_at"][:10], "teams": m["home_team"] + " / " + m["away_team"]})
            continue
        if any((o["home_goals"], o["away_goals"]) == (m["home_score"], m["away_score"]) for o in options):
            matched += 1
        else:
            discrepant.append({"date": m["kickoff_at"][:10],
                               "clubs": m["home_team"] + " / " + m["away_team"],
                               "corner_score": str(m["home_score"]) + "-" + str(m["away_score"]),
                               "reference_score": str(options[0]["home_goals"]) + "-" + str(options[0]["away_goals"])})
    return {"score_agreement": matched, "score_disagreement": len(discrepant),
            "match_not_identified_in_reference": len(unmatched),
            "score_disagreement_examples": discrepant[:3],
            "nonmatched_examples": unmatched[:3]}

def audit(fetch=fetch_json):
    references = {}
    for name, slug in OPENFOOTBALL.items():
        try:
            references[name] = get_openfootball(slug)
            print(json.dumps({"stage": "reference", "league": name, "reference_results": len(references[name])}))
        except (ValueError, KeyError, TypeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            print(json.dumps({"stage": "reference", "league": name, "error": type(exc).__name__}))

    total_records, audited = 0, 0
    for name, slug in COMPETITIONS.items():
        summary = {"stage": "league", "league": name, "slug": slug}
        try:
            season = fetch(f"{BASE}/football/leagues/{slug}/results/season.json")
            items = season.get("matches")
            if not isinstance(items, list):
                raise ValueError("Season index lacks match list")
            total_records += len(items)
            summary["index_records"] = len(items)
            summary["source"] = (season.get("meta") or {}).get("source")
            summary["updated"] = (season.get("meta") or {}).get("last_updated_at")
            summary["finished_records"] = sum(x.get("status") == "finished" for x in items)
            summary["duplicate_ids"] = len(items) - len({x.get("id") for x in items})
            summary["unique_clubs"] = len({x.get(k) for x in items for k in ("home_team", "away_team") if x.get(k)})
            dates = sorted(x.get("kickoff_at", "")[:10] for x in items if x.get("kickoff_at"))
            summary["oldest"] = dates[0] if dates else None
            summary["newest"] = dates[-1] if dates else None
            # A country masquerading as a club is strongly suspicious in a domestic club competition.
            bad_names = {"angola", "brazil", "portugal", "argentina", "england",
                         "spain", "germany", "france", "italy", "mexico"}
            summary["suspicious_country_club_records"] = [
                {"date": x.get("kickoff_at", "")[:10],
                 "home": x.get("home_team"), "away": x.get("away_team")}
                for x in items if x.get("home_team", "").casefold() in bad_names
                             or x.get("away_team", "").casefold() in bad_names
            ][:4]
            if name in references:
                summary["independent_check"] = compare_league(items, references[name])
            latest = sorted((m for m in items if m.get("status") == "finished" and
                             isinstance(m.get("dataset_url"), str)),
                            key=lambda m: m.get("kickoff_at", ""), reverse=True)
            checks = []
            for entry in latest[:2]:
                try:
                    m = parse_match(fetch(entry["dataset_url"]))
                    checks.append({"result": "ok", "field_count": len(m["statistics"]),
                                   "has_xg": all("xg_" + t in m["statistics"] for t in ("home", "away")),
                                   "has_shots": all("shots_" + t in m["statistics"] for t in ("home", "away")),
                                   "has_corners": all("corners_" + t in m["statistics"] for t in ("home", "away")),
                                   "has_cards": all("yellow_" + t in m["statistics"] for t in ("home", "away")),
                                   "same_teams": m["home"] == entry["home_team"] and m["away"] == entry["away_team"],
                                   "same_score": (m["home_goals"], m["away_goals"]) ==
                                                 (entry["home_score"], entry["away_score"])})
                except (ValueError, KeyError, TypeError, urllib.error.URLError, TimeoutError, OSError) as exc:
                    checks.append({"result": "error", "reason": type(exc).__name__})
            summary["sample_matches"] = checks
            summary["status"] = "audited"
            audited += 1
        except (ValueError, KeyError, TypeError, urllib.error.URLError, TimeoutError, OSError) as exc:
            summary["status"] = "unavailable"
            summary["reason"] = type(exc).__name__
            summary["http_code"] = getattr(exc, "code", None)
        print(json.dumps(summary, ensure_ascii=False))
    print(json.dumps({"stage": "overall", "league_indexes_read": audited,
                      "league_candidates": len(COMPETITIONS), "total_index_records": total_records,
                      "special_world_cup_hub": "not a regular league season index"}))

if __name__ == "__main__":
    audit()
