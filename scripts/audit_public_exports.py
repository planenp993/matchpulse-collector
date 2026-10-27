"""One-time audit of expressly published CSV download endpoints.

No scraping, proxy, credentials, repeated requests, data saving, or scheduled
harvesting. Prints only diagnostic status and aggregate coverage statistics.
Open-matchday is RESEARCH/NONCOMMERCIAL ONLY; never mix into commercial feeds.
"""
import csv
import io
import json
import urllib.error
import urllib.request

URLS = {
    "cornerflick_england": "https://cornerflick.com/football/leagues/premier-league/results/season.csv",
    "cornerflick_spain": "https://cornerflick.com/football/leagues/la-liga/results/season.csv",
    "open_matchday_england_research_only": "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data/ENG_1_premier-league/results_2627.csv",
    "open_matchday_germany_research_only": "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data/GER_1_bundesliga/results_2627.csv",
    "open_matchday_spain_research_only": "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data/ESP_1_la-liga/results_2627.csv",
    "open_matchday_build_summary_research_only": "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/build_summary.json",
}
MAX_BYTES = 3000000

def check(name, url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "MATCHPULSE-collector/0.1 (one-off public export audit)",
        "Accept": "text/csv,application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status = response.getcode()
            payload = response.read(MAX_BYTES + 1)
            ctype = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as err:
        return {"dataset": name, "status": "http_error", "http": err.code}
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return {"dataset": name, "status": "network_error", "error": type(err).__name__}
    if status != 200 or len(payload) > MAX_BYTES:
        return {"dataset": name, "status": "unexpected_response", "http": status,
                "oversized": len(payload) > MAX_BYTES}
    if name.endswith("build_summary_research_only"):
        try:
            data = json.loads(payload)
            return {"dataset": name, "status": "ok", "generated_utc": data.get("generated_utc"),
                    "league_count": len(data.get("leagues", []))}
        except (ValueError, TypeError):
            return {"dataset": name, "status": "invalid_json"}
    text = payload.decode("utf-8-sig", errors="replace")
    try:
        lines = [s for s in text.splitlines() if not s.startswith("#")]
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
        headers = reader.fieldnames or []
        if not headers or ("html" in text[:200].lower()):
            return {"dataset": name, "status": "not_csv", "content_type": ctype}
        rows = list(reader)
        if "open_matchday" in name:
            keys = ["home_shots", "home_target", "home_corners", "home_yellow"]
        else:
            keys = [s for s in headers if any(t in s.lower() for t in ["shot", "corner", "yellow", "xg", "expected"])]
        filled = {k: sum(bool(row.get(k, "").strip()) for row in rows) for k in keys}
        dates = sorted(row.get("date", "") for row in rows if row.get("date"))
        return {"dataset": name, "status": "ok", "rows": len(rows),
                "first_date": dates[0] if dates else None,
                "last_date": dates[-1] if dates else None,
                "stat_coverage": filled, "stat_columns": keys[:25],
                "important_notice": "noncommercial research only" if "open_matchday" in name
                    else "CC-BY compilation; upstream rights still apply"}
    except (csv.Error, UnicodeError) as err:
        return {"dataset": name, "status": "csv_parse_error", "error": type(err).__name__}

def main():
    for name, url in URLS.items():
        print(json.dumps(check(name, url), ensure_ascii=False))

if __name__ == "__main__":
    main()
