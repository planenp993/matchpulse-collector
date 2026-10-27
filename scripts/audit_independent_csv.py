"""Quality verification against independent published open-matchday results CSV.

This is an inspection only, not permission to ingest open-matchday (NC-only).
No external records are persisted; only league aggregates printed.
"""
import collections
import csv
import difflib
import io
import json
import urllib.error
import urllib.request

from scripts.audit_leagues_full import COMPETITIONS, normalize
from scripts.cornerflick_source import BASE, fetch_json

BASE_CSV = "https://raw.githubusercontent.com/oladeeayo/open-matchday/master/data/"
LEAGUES = {
    "Premier League": ("premier-league", "ENG_1_premier-league"),
    "La Liga": ("la-liga", "ESP_1_la-liga"),
    "Bundesliga": ("bundesliga", "GER_1_bundesliga"),
    "Serie A": ("serie-a", "ITA_1_serie-a"),
    "Ligue 1": ("ligue-1", "FRA_1_ligue-1"),
    "Primeira Liga": ("primeira-liga", "POR_1_primeira-liga"),
    "Eredivisie": ("eredivisie", "NED_1_eredivisie"),
    "Süper Lig": ("super-lig", "TUR_1_super-lig"),
}
ALIASES = {
    "manutd": "manchesterunited", "manunited": "manchesterunited",
    "mancity": "manchestercity", "nottmforest": "nottinghamforest",
    "leeds": "leedsunited", "hull": "hullcity", "ipswich": "ipswichtown",
    "brighton": "brightonandhovealbion", "westham": "westhamunited",
    "inter": "internazionale", "acmilan": "milan", "roma": "asroma",
    "napoli": "napoli", "fcbarcelona": "barcelona",
    "bayernmunchen": "fcbayernmunchen",
    "fcbayernmunchen": "bayernmunchen",
    "1fckoln": "koln",
    "tsghoffenheim": "1899hoffenheim",
    "fcunionberlin": "unionberlin",
    "sporting": "sportingcp",
}

def clean(team):
    x=normalize(team)
    return ALIASES.get(x,x)

def close_team(a,b):
    a,b=clean(a),clean(b)
    return a==b or difflib.SequenceMatcher(None,a,b).ratio() >= 0.78

def load_csv(folder):
    url=BASE_CSV+folder+"/results_2627.csv"
    request=urllib.request.Request(url,headers={"User-Agent":"MATCHPULSE/0.1 published-file verification","Accept":"text/csv"})
    with urllib.request.urlopen(request,timeout=15) as res:
        raw=res.read(1500000).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(raw)))

def date_near(a,b):
    import datetime as dt
    try:
        return abs((dt.date.fromisoformat(a)-dt.date.fromisoformat(b)).days)<=1
    except ValueError:
        return False

def compare(index, rows):
    aggregates=collections.Counter()
    warnings=[]
    used=set()
    for match in index:
        if match.get("status")!="finished":
            continue
        date=match.get("kickoff_at","")[:10]
        possibilities=[]
        for i,row in enumerate(rows):
            if i in used or not date_near(date,row.get("date","")):
                continue
            if close_team(match.get("home_team",""),row.get("home","")) and close_team(match.get("away_team",""),row.get("away","")):
                possibilities.append((i,row))
        if not possibilities:
            aggregates["unmatched"]+=1
            continue
        if len(possibilities)>1:
            aggregates["ambiguous"]+=1
            continue
        i,row=possibilities[0]
        used.add(i)
        aggregates["matched"]+=1
        source=(str(match.get("home_score")),str(match.get("away_score")))
        reference=(row.get("ft_home"),row.get("ft_away"))
        if source==reference:
            aggregates["results_agree"]+=1
        else:
            aggregates["results_disagree"]+=1
            if len(warnings)<4:
                warnings.append({"date":date,"teams":match["home_team"]+" / "+match["away_team"],
                                 "cornerflick":list(source),"research_archive":list(reference)})
        # Only compare fields that the season index and research CSV actually contain:
        # season JSON lacks shots, corners, xG; these are audited separately via match JSON.
    return {"coverage":dict(aggregates),"score_mismatch_examples":warnings,
            "research_rows":len(rows),"cornerflick_rows":len(index)}

def main():
    for title,(slug,folder) in LEAGUES.items():
        try:
            index=fetch_json(f"{BASE}/football/leagues/{slug}/results/season.json")["matches"]
            rows=load_csv(folder)
            output={"league":title,"status":"ok",**compare(index,rows)}
        except (ValueError,KeyError,TypeError,urllib.error.URLError,TimeoutError,OSError) as exc:
            output={"league":title,"status":"error","kind":type(exc).__name__,"http":getattr(exc,"code",None)}
        print(json.dumps(output,ensure_ascii=False))

if __name__=="__main__":
    main()
