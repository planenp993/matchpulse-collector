"""SofaScore direct endpoint experimental collector (no credential/bypass support).

One schedule request, then at most N detailed statistics requests for completed
matches in selected competitions. Not a licensed API. No retries, proxies,
browser impersonation or bypass attempts. Stop immediately on access denial.
Results are saved only under ignored local/ paths and never auto-published.
"""
import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.sofascore_adapter import normalize_event, normalize_statistics

BASE = "https://api.sofascore.com/api/v1"
USER_AGENT = "MATCHPULSE-collector/0.3 (experimental; no authentication)"
ALLOWED = {
    ("england", "premier league"),
    ("germany", "bundesliga"),
    ("spain", "laliga"),
    ("spain", "laliga ea sports"),
    ("spain", "primera division"),
    ("italy", "serie a"),
}
MAX_STATS_REQUESTS = 5


class ProviderDenied(Exception):
    pass


def fetch_json(path, *, opener=None):
    """One non-retried GET. Denials are terminal, not invitations to evade."""
    if not path.startswith("/") or "?" in path or ".." in path:
        raise ValueError("Disallowed endpoint path")
    if not (path.startswith("/sport/football/scheduled-events/") or
            path.startswith("/event/") and path.endswith("/statistics")):
        raise ValueError("Endpoint outside two necessary families")
    open_req = opener or urllib.request.urlopen
    request = urllib.request.Request(
        BASE + path,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        method="GET",
    )
    try:
        with open_req(request, timeout=12) as res:
            status = res.getcode()
            if status != 200:
                raise ProviderDenied("HTTP " + str(status))
            ct = res.headers.get("Content-Type", "")
            if "json" not in ct.lower():
                raise ValueError("Non-JSON content type; possible access block")
            payload = json.load(res)
            if not isinstance(payload, dict):
                raise ValueError("Expected JSON object")
            return payload
    except urllib.error.HTTPError as exc:
        raise ProviderDenied("HTTP " + str(exc.code) + "; stopped with no retry") from None
    except urllib.error.URLError as exc:
        raise ProviderDenied("Network error; stopped with no retry: " + str(exc.reason)) from None
    except TimeoutError:
        raise ProviderDenied("Provider timeout; stopped with no retry") from None


def scheduled_events(date, *, fetcher=fetch_json):
    dt.date.fromisoformat(date)
    data = fetcher("/sport/football/scheduled-events/" + date)
    events = data.get("events")
    if not isinstance(events, list):
        raise ValueError("No events array; provider schema may have changed")
    return events


def competition(event):
    tournament = event.get("tournament") or {}
    category = tournament.get("category") or {}
    unique = tournament.get("uniqueTournament") or {}
    name = unique.get("name") or tournament.get("name") or ""
    country = category.get("name") or ""
    return (country.strip().casefold(), name.strip().casefold())


def selected_finished(events):
    matches = []
    seen = set()
    for e in events:
        if not isinstance(e, dict):
            continue
        if competition(e) not in ALLOWED:
            continue
        if (e.get("status") or {}).get("type") != "finished":
            continue
        try:
            p = normalize_event(e)
        except (ValueError, TypeError):
            continue
        if p["source_event_id"] in seen:
            continue
        seen.add(p["source_event_id"])
        matches.append((e, p))
    return sorted(matches, key=lambda r: r[1]["kickoff_utc"])


def run(date, *, mode="probe", max_stats=2, fetcher=fetch_json, sleeper=time.sleep):
    if mode not in ("probe", "collect"):
        raise ValueError("Unknown mode")
    if type(max_stats) is not int or not 1 <= max_stats <= MAX_STATS_REQUESTS:
        raise ValueError("Limit must be 1..5")
    events = scheduled_events(date, fetcher=fetcher)
    picks = selected_finished(events)
    limit = 1 if mode == "probe" else max_stats
    observations = []
    errors = []
    for i, (event, info) in enumerate(picks[:limit]):
        if i:
            sleeper(3)  # non-burst pacing; no failed-request retries
        try:
            payload = fetcher(f"/event/{info['source_event_id']}/statistics")
        except ProviderDenied:
            raise  # access denial: stop immediately
        except ValueError as exc:
            errors.append(str(exc))
            continue
        try:
            metrics = normalize_statistics(payload)
        except ValueError as exc:
            errors.append(f"Statistics schema for event {info['source_event_id']}: {exc}")
            continue
        observations.append({
            "event": event, "statistics": payload,
            "preview": info, "normalized": metrics
        })
    return {
        "source": "SofaScore (unofficial endpoint experiment)",
        "date": date,
        "mode": mode,
        "events_in_schedule": len(events),
        "finished_in_selected_leagues": len(picks),
        "inspected_statistics": len(observations),
        "statistics_fields": sorted({k for x in observations for k in x["normalized"]}),
        "warnings": errors,
        "events": observations if mode == "collect" else [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("probe", "collect"), default="probe")
    parser.add_argument("--date", help="YYYY-MM-DD; default yesterday in Europe/Sofia")
    parser.add_argument("--max-stats", type=int, default=2, help="Maximum 1..5")
    parser.add_argument("--out", type=Path, help="For collect only; ignored local/ path")
    args = parser.parse_args()
    today = dt.datetime.now(ZoneInfo("Europe/Sofia")).date()
    date = args.date or (today - dt.timedelta(days=1)).isoformat()
    try:
        outcome = run(date, mode=args.mode, max_stats=args.max_stats)
    except (ProviderDenied, ValueError) as exc:
        print(json.dumps({"status": "blocked_or_unavailable", "reason": str(exc),
                          "date": date, "automated_retries": 0}, ensure_ascii=False))
        return 2
    summary = {k: v for k, v in outcome.items() if k != "events"}
    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))
    if args.mode == "collect":
        out = args.out or Path(f"local/sofascore_{date}.json")
        if not str(out).startswith("local/"):
            parser.error("Raw data must stay in ignored local/ directory")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(outcome, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Private sample only: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
