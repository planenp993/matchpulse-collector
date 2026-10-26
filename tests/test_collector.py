import unittest
from scripts.collector import build_snapshot, import_authorized_stats, parse_source, utc_kickoff

RAW = {"matches": [
    {"date": "2026-10-31", "time": "15:30", "team1": "Alpha", "team2": "Beta"},
    {"date": "2026-08-30", "time": "17:00", "team1": "Gamma", "team2": "Delta", "score": {"ft": [2, 1]}},
]}


class CollectorTests(unittest.TestCase):
    def test_parse_schedule_and_results(self):
        games = parse_source(RAW, "D1")
        self.assertEqual(len(games), 2)
        self.assertEqual(games[0]["kickoff_utc"], "2026-10-31T14:30:00Z")
        self.assertIsNone(games[0]["home_goals"])
        self.assertEqual(games[1]["away_goals"], 1)
        self.assertEqual(games[1]["statistics"], {})

    def test_reject_duplicate(self):
        with self.assertRaises(ValueError):
            parse_source({"matches": [RAW["matches"][0]] * 2}, "D1")

    def test_reject_negative_score(self):
        with self.assertRaises(ValueError):
            parse_source({"matches": [dict(RAW["matches"][0], score={"ft": [-1, 1]})]}, "D1")

    def test_no_empty_overwrite(self):
        with self.assertRaises(RuntimeError):
            build_snapshot({})

    def test_keep_last_good_data(self):
        prior = build_snapshot({"D1": RAW})
        result = build_snapshot({}, prior=prior)
        self.assertEqual(prior["matches_count"], result["matches_count"])
        self.assertEqual(result["status"], "partial")

    def test_authorized_stats(self):
        games = parse_source(RAW, "D1")
        import_authorized_stats(games, {
            "source": "authorized sample", "permission_note": "unit test",
            "matches": [{"match_id": games[1]["id"], "statistics": {"shots_home": 11, "xg_home": 1.4}}],
        })
        self.assertEqual(games[1]["statistics"]["xg_home"], 1.4)
        self.assertEqual(games[0]["statistics"], {})

    def test_no_unsupported_stats(self):
        games = parse_source(RAW, "D1")
        with self.assertRaises(ValueError):
            import_authorized_stats(games, {
                "source": "test", "permission_note": "test",
                "matches": [{"match_id": games[1]["id"], "statistics": {"fake_stat": 4}}],
            })

    def test_timezones(self):
        self.assertEqual(utc_kickoff("2026-10-26", "20:30", "Europe/Berlin"), "2026-10-26T19:30:00Z")


if __name__ == "__main__":
    unittest.main()
