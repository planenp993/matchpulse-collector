"""One-off Cornerflick quality audit: all season indexes + bounded detailed sample.

Only aggregates are published; no original match files or statistics values stored.
All unknown or suspected club IDs remain blocked from MATCHPULSE ingestion.
"""
import argparse
import collections
import datetime as dt
import json
import time
import urllib.error
from pathlib import Path
from scripts.audit_leagues_full import COMPETITIONS
from scripts.cornerflick_source import BASE, fetch_json, parse_match, safe_public_url

COUNTRIES = {"angola","brazil","portugal","argentina","england","spain",
             "germany","france","italy","mexico","nigeria","japan"}
METRICS = {
    "xg": ("xg_home","xg_away"),
    "shots": ("shots_home","shots_away"),
    "on_target": ("shots_on_target_home","shots_on_target_away"),
    "corners": ("corners_home","corners_away"),
    "yellow": ("yellow_home","yellow_away"),
    "red": ("red_home","red_away"),
    "possession": ("possession_home","possession_away"),
}


def scan_index(rows):
    """Inspect every row, not a sample. Structural quality is not identity proof."""
    seen_ids, seen_games = set(), set()
    counts = collections.Counter()
    examples = []
    for r in rows:
        counts["records"] += 1
        errors = set()
        if not isinstance(r, dict):
            errors.add("invalid_row")
            continue
        rid, home, away = r.get("id"), r.get("home_team"), r.get("away_team")
        if not isinstance(rid,str) or not rid.strip():
            errors.add("missing_id")
        elif rid in seen_ids:
            errors.add("duplicate_id")
        else:
            seen_ids.add(rid)
        if not all(isinstance(t,str) and t.strip() for t in (home,away)):
            errors.add("missing_team")
        else:
            if home.casefold() == away.casefold():
                errors.add("same_team")
            if home.strip().casefold() in COUNTRIES or away.strip().casefold() in COUNTRIES:
                errors.add("country_in_club_competition")
        if type(r.get("home_score")) is not int or type(r.get("away_score")) is not int:
            errors.add("invalid_score")
        elif r["home_score"] < 0 or r["away_score"] < 0:
            errors.add("negative_score")
        stamp = r.get("kickoff_at")
        try:
            parsed = dt.datetime.fromisoformat(stamp.replace("Z","+00:00"))
            if parsed.tzinfo is None:
                errors.add("missing_timezone")
        except (ValueError,TypeError,AttributeError):
            errors.add("invalid_kickoff")
        if isinstance(home,str) and isinstance(away,str) and isinstance(stamp,str):
            key = (home.casefold(), away.casefold(), stamp[:10])
            if key in seen_games:
                errors.add("duplicate_fixture")
            seen_games.add(key)
        try:
            safe_public_url(r.get("dataset_url", ""))
        except ValueError:
            errors.add("invalid_dataset_url")
        if r.get("status") != "finished":
            errors.add("not_finished")
        if errors:
            counts["flagged"] += 1
            for issue in errors:
                counts[issue] += 1
            if len(examples) < 8:
                examples.append({"id": rid, "home": home, "away": away, "reasons": sorted(errors)})
        else:
            counts["structurally_plausible"] += 1
    return {"counts":dict(counts),"examples":examples}


def reviewed_team_id(competition,name,manifest):
    """No fuzzy reconciliation, no inferred team IDs and no automatic fixes."""
    if not isinstance(manifest,dict):
        raise ValueError("Manifest required")
    team = manifest.get(competition,{}).get(name)
    if not isinstance(team,dict) or team.get("reviewed") is not True:
        raise ValueError("Unverified team identity, quarantine")
    ident = team.get("team_id")
    if not isinstance(ident,str) or not ident:
        raise ValueError("No canonical team ID")
    if name.strip().casefold() in COUNTRIES:
        raise ValueError("Country named as club, quarantine")
    return ident


def sample_positions(n,maximum):
    if not 1 <= maximum <= 6:
        raise ValueError("Limit must be 1..6")
    if n <= maximum:
        return list(range(n))
    return sorted({round(i*(n-1)/(maximum-1)) for i in range(maximum)})


def audit(maximum=6, fetcher=fetch_json, sleeper=time.sleep):
    summary={"scan":"all_index_rows_plus_stratified_detail_sample",
             "full_match_statistics_completeness_proven":False,
             "source_rights":"Cornerflick CC BY compilation; upstream rights unresolved",
             "competitions":{}, "totals":{}}
    totals=collections.Counter()
    access_denied=False
    for league,slug in COMPETITIONS.items():
        entry={"slug":slug,"status":"unavailable"}
        if access_denied:
            entry["status"]="skipped_after_access_denial"
            summary["competitions"][league]=entry
            continue
        try:
            data=fetcher(f"{BASE}/football/leagues/{slug}/results/season.json")
            rows=data["matches"]
            if not isinstance(rows,list):
                raise ValueError("Missing matches list")
            scan=scan_index(rows)
            entry.update({"status":"ok","indexed":len(rows),"index_qa":scan,
                          "sampled":0,"valid_sample":0,"bad_sample":0,
                          "metrics":{k:0 for k in METRICS}})
            totals["indexed"]+=len(rows)
            totals["flagged"]+=scan["counts"].get("flagged",0)
            eligible=sorted((r for r in rows if isinstance(r,dict) and
                             r.get("status")=="finished" and
                             isinstance(r.get("dataset_url"),str)),
                            key=lambda r:r.get("kickoff_at",""))
            for pos in sample_positions(len(eligible),maximum):
                index=eligible[pos]
                entry["sampled"]+=1
                totals["sampled"]+=1
                try:
                    safe_public_url(index["dataset_url"])
                    sleeper(0.4)
                    detail=parse_match(fetcher(index["dataset_url"]))
                    consistent = (detail["home"]==index["home_team"]
                                  and detail["away"]==index["away_team"]
                                  and detail["home_goals"]==index["home_score"]
                                  and detail["away_goals"]==index["away_score"])
                    if not consistent:
                        raise ValueError("Index/detail disagreement")
                    entry["valid_sample"]+=1
                    totals["valid_sample"]+=1
                    for metric,pair in METRICS.items():
                        if all(key in detail["statistics"] for key in pair):
                            entry["metrics"][metric]+=1
                            totals["metric_"+metric]+=1
                except urllib.error.HTTPError as exc:
                    entry["bad_sample"]+=1
                    totals["bad_sample"]+=1
                    if exc.code in (401,403,429):
                        entry["status"]="access_denied"
                        access_denied=True
                        break
                except (ValueError,KeyError,TypeError,urllib.error.URLError,TimeoutError,OSError):
                    entry["bad_sample"]+=1
                    totals["bad_sample"]+=1
        except urllib.error.HTTPError as exc:
            entry["status"]="http_error"
            entry["http"]=exc.code
            access_denied=exc.code in (401,403,429)
        except (KeyError,TypeError,ValueError,urllib.error.URLError,TimeoutError,OSError) as exc:
            entry["status"]="read_error"
            entry["error_type"]=type(exc).__name__
        summary["competitions"][league]=entry
    summary["totals"]=dict(totals)
    summary["access_denied"]=access_denied
    summary["production_ingestion_enabled"]=False
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sample",type=int,default=6)
    args=p.parse_args()
    result=audit(args.sample)
    out=Path("reports/CORNERFLICK_QUALITY_SAMPLE.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"totals":result["totals"],"access_denied":result["access_denied"],
        "leagues":{k:{"indexed":v.get("indexed",0),
                       "flagged":v.get("index_qa",{}).get("counts",{}).get("flagged",0),
                       "sampled":v.get("sampled",0),
                       "xg_present":v.get("metrics",{}).get("xg",0),
                       "status":v["status"]}
                   for k,v in result["competitions"].items()}},ensure_ascii=False))


if __name__=="__main__":
    main()
