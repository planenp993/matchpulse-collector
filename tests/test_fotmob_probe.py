import io
import json
import unittest
import urllib.error
from scripts.fotmob_probe import (AccessUnavailable, get_json, number,
                                  parse_match_stats, parse_matches, run_probe)

def example_stats():
    return {"content": {"stats": {"Periods": {"All": {"stats": [
        {"title": "Top stats", "stats": [
            {"title": "Expected goals (xG)", "stats": ["1.72", "0.84"]},
            {"title": "Ball possession", "stats": ["60%", "40%"]},
        ]},
        {"title": "Shots", "stats": [
            {"title": "Total shots", "stats": [16, 8]},
            {"title": "Shots on target", "stats": [5, 2]},
            {"title": "Corner kicks", "stats": [7, 3]},
        ]},
        {"title": "Discipline", "stats": [
            {"title": "Yellow cards", "stats": [2, 3]},
            {"title": "Red cards", "stats": [0, 0]},
        ]},
    ]}}}}}

def example_list():
    return {"date": "20261026", "leagues": [
        {"primaryId": 47, "name": "Premier League", "matches": [
            {"id": 5795427, "home": {"name": "Chelsea"}, "away": {"name": "Brighton"},
             "status": {"finished": True}}]},
        {"primaryId": 200, "name": "Other", "matches": [
            {"id": 1234567, "home": {}, "away": {}, "status": {"finished": True}}]},
    ]}

class FotmobTests(unittest.TestCase):
    def test_parse_keys(self):
        value = parse_match_stats(example_stats())
        self.assertEqual(value["xg_home"], 1.72)
        self.assertEqual(value["shots_home"], 16)
        self.assertEqual(value["shots_on_target_away"], 2)
        self.assertEqual(value["corners_home"], 7)
        self.assertEqual(value["red_home"], 0)
        self.assertEqual(value["possession_away"], 40)
        self.assertEqual(len(value), 14)

    def test_missing_xg_remains_absent(self):
        x = example_stats()
        x["content"]["stats"]["Periods"]["All"]["stats"][0]["stats"].pop(0)
        self.assertNotIn("xg_home", parse_match_stats(x))

    def test_only_full_match(self):
        x = example_stats()
        x["content"]["stats"]["Periods"]["FirstHalf"] = {"stats": [
            {"title": "Top stats", "stats": [{"title": "Expected goals (xG)", "stats": [9, 9]}]}]}
        self.assertEqual(parse_match_stats(x)["xg_home"], 1.72)

    def test_no_stats_rejected(self):
        with self.assertRaises(ValueError):
            parse_match_stats({"content": {"stats": {"Periods": {"FirstHalf": {}}}}})

    def test_no_target_exceeds_total(self):
        x = example_stats()
        x["content"]["stats"]["Periods"]["All"]["stats"][1]["stats"][1]["stats"] = [18, 2]
        with self.assertRaises(ValueError):
            parse_match_stats(x)

    def test_invalid_values(self):
        for bad in (-1, "N/A", True, "4/6"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                number(bad, "integer")

    def test_match_filter(self):
        self.assertEqual(len(parse_matches(example_list())), 1)

    def test_probe_limit_and_result(self):
        paths = []
        def fetch(path):
            paths.append(path)
            return example_list() if path.startswith("matches?") else example_stats()
        outcome = run_probe("20261026", fetch)
        self.assertEqual(len(paths), 2)
        self.assertEqual(outcome["statistics"]["xg_away"], 0.84)

    def test_empty_list_does_not_fetch_details(self):
        paths = []
        def fetch(path):
            paths.append(path)
            return {"leagues": []}
        self.assertEqual(run_probe("20261026", fetch)["finished_eligible_matches"], 0)
        self.assertEqual(len(paths), 1)

    def test_denied_without_retry(self):
        seen = []
        def denied(request, timeout):
            seen.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", None, None)
        with self.assertRaises(AccessUnavailable):
            get_json("matches?date=20261026", opener=denied)
        self.assertEqual(len(seen), 1)

    def test_no_arbitrary_endpoint(self):
        with self.assertRaises(ValueError):
            get_json("../etc/passwd")

if __name__ == "__main__":
    unittest.main()
