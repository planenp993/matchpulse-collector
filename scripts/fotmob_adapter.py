"""Offline FotMob-format match statistics adapter; does not access FotMob servers."""
import json
from pathlib import Path

FIELD_MAP = {
    "Expected goals (xG)": ("xg_home", "xg_away"),
    "Total shots": ("shots_home", "shots_away"),
    "Shots on target": ("shots_on_target_home", "shots_on_target_away"),
    "Corner kicks": ("corners_home", "corners_away"),
    "Yellow cards": ("yellow_home", "yellow_away"),
    "Red cards": ("red_home", "red_away"),
    "Ball possession": ("possession_home", "possession_away"),
}

def parse_stats(document):
    """Accept locally provided, authorized matchDetails-like JSON.
    Schema varies; reject unexpected layouts rather than invent values.
    """
    groups = document.get("content", {}).get("stats", {}).get("Periods", {})
    overall = groups.get("All", [])
    if not isinstance(overall, list):
        raise ValueError("Invalid FotMob statistics layout")
    out = {}
    for group in overall:
        for row in group.get("stats", []):
            name = row.get("title")
            if name not in FIELD_MAP:
                continue
            values = row.get("stats")
            if not isinstance(values, list) or len(values) != 2:
                continue
            keys = FIELD_MAP[name]
            for key, raw in zip(keys, values):
                if raw is None:
                    continue
                if isinstance(raw, bool):
                    raise ValueError("Invalid boolean statistic")
                try:
                    value = float(str(raw).replace("%", ""))
                except (ValueError, TypeError):
                    continue
                if not 0 <= value <= (100 if "possession" in key else 1000):
                    raise ValueError("Out-of-range statistic")
                if key in out and out[key] != value:
                    raise ValueError("Conflicting duplicate statistic")
                out[key] = value
    return out

def from_file(path, permission_note):
    if not permission_note.strip():
        raise ValueError("Permission note required")
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {"source": "FotMob-format authorized local export",
            "permission_note": permission_note,
            "statistics": parse_stats(doc)}
