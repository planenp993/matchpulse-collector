import copy
import datetime as dt
import unittest

from scripts.collector import import_authorized_stats
from scripts.sofascore_adapter import convert_bundle, normalize_statistics, normalize_event, verify_join


def stat(key, h, a):
    return {"key": key, "homeValue": h, "awayValue": a}


def event():
    return {
        "id": 12345, "startTimestamp": 1780257600,
        "homeTeam": {"name": "Arsenal"}, "awayTeam": {"name": "Chelsea"},
        "status": {"type": "finished"}, "tournament": {"name": "Premier League"},
        "homeScore": {"current": 2}, "awayScore": {"current": 1},
    }


class SofaTests(unittest.TestCase):
    def setUp(self):
        self.raw = {"statistics": [
            {"period": "1ST", "groups": [{"statisticsItems": [stat("expectedGoals", 9, 9)]}]},
            {"period": "ALL", "groups": [
                {"statisticsItems": [
                    stat("totalShotsOnGoal", 14, 10), stat("shotsOnGoal", 6, 3),
                    stat("expectedGoals", 1.72, 0.88), stat("cornerKicks", 7, 2),
                    stat("yellowCards", 2, 4), stat("redCards", 0, 0),
                    stat("ballPossession", 61, 39)]},
                {"statisticsItems": [stat("expectedGoals", "1.72", "0.88")]},
            ]},
            {"period": "2ND", "groups": [{"statisticsItems": [stat("expectedGoals", 5, 5)]}]},
        ]}
        match_date = dt.datetime.fromtimestamp(event()["startTimestamp"], tz=dt.timezone.utc).date().isoformat()
        self.match = {"id": "mp:fixture", "home": "Arsenal FC", "away": "Chelsea FC",
                      "date": match_date, "status": "finished", "home_goals": 2,
                      "away_goals": 1, "statistics": {}}

    def test_exact_full_time_and_correct_shot_keys(self):
        stats = normalize_statistics(self.raw)
        self.assertEqual(stats["shots_home"], 14)
        self.assertEqual(stats["shots_on_target_home"], 6)
        self.assertEqual(stats["xg_home"], 1.72)
        self.assertEqual(stats["red_home"], 0)
        self.assertEqual(len(stats), 14)

    def test_missing_xg_remains_missing(self):
        raw = {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
            stat("cornerKicks", 4, 3),
            {"key": "expectedGoals", "home": "1.5", "away": "2.3"}]}]}]}
        metrics = normalize_statistics(raw)
        self.assertNotIn("xg_home", metrics)
        self.assertEqual(metrics["corners_home"], 4)

    def test_reject_conflicting_duplicate(self):
        with self.assertRaises(ValueError):
            normalize_statistics({"statistics": [{"period": "ALL", "groups": [{
                "statisticsItems": [stat("shotsOnGoal", 5, 2), stat("shotsOnGoal", 6, 2)]}]}]})

    def test_invalid_counts_and_missing_full_time(self):
        for value in (-1, "6/8", True, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_statistics({"statistics": [{"period": "ALL", "groups": [{
                    "statisticsItems": [stat("cornerKicks", value, 1)]}]}]})
        with self.assertRaises(ValueError):
            normalize_statistics({"statistics": [{"period": "1ST", "groups": []}]})

    def test_target_shots_cannot_exceed_total(self):
        with self.assertRaises(ValueError):
            normalize_statistics({"statistics": [{"period": "ALL", "groups": [{
                "statisticsItems": [stat("shotsOnGoal", 7, 2), stat("totalShotsOnGoal", 6, 3)]}]}]})

    def test_strict_match_validation(self):
        verify_join(event(), self.match)
        other = dict(self.match, away="Fulham")
        with self.assertRaises(ValueError):
            verify_join(event(), other)
        other = dict(self.match, home_goals=3)
        with self.assertRaises(ValueError):
            verify_join(event(), other)

    def test_offline_join_with_existing_collector(self):
        data = convert_bundle({"events": [{"event": event(), "statistics": self.raw}]},
                              {"12345": "mp:fixture"}, {"matches": [self.match]}, "Authorized test data")
        self.assertEqual(data["coverage"]["with_xg"], 1)
        match = copy.deepcopy(self.match)
        import_authorized_stats([match], data)
        self.assertEqual(match["statistics"]["shots_on_target_away"], 3)

    def test_unmapped_fixture_preview_and_duplicate(self):
        bundle = {"events": [{"event": event(), "statistics": self.raw}]}
        data = convert_bundle(bundle, {}, {"matches": [self.match]}, "Authorized sample")
        self.assertEqual(data["matches"], [])
        self.assertTrue(normalize_event(event())["kickoff_sofia"])
        with self.assertRaises(ValueError):
            convert_bundle({"events": bundle["events"] * 2}, {}, {"matches": []}, "Authorized sample")

    def test_wrong_target_refused(self):
        with self.assertRaises(ValueError):
            convert_bundle({"events": [{"event": event(), "statistics": self.raw}]},
                           {"12345": "mp:unknown"}, {"matches": [self.match]}, "Authorized sample")


if __name__ == "__main__":
    unittest.main()
