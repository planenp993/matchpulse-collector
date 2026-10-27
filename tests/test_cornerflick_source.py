import unittest
from scripts.cornerflick_source import parse_match, newest_finished, safe_public_url


def sample():
    return {
        "meta": {"publisher": "Cornerflick", "source": "API-Football", "license": "CC BY 4.0"},
        "match": {"id": "test", "status": "finished",
                  "kickoff_at": "2026-08-21T19:00:00+00:00",
                  "competition": {"name": "Premier League"},
                  "score": {"home": 3, "away": 0}},
        "teams": {"home": {"name": "Team A"}, "away": {"name": "Team B"}},
        "statistics": [
            {"label": "Shots", "home": 19, "away": 4},
            {"label": "Shots on Target", "home": 6, "away": 1},
            {"label": "xG", "home": 1.77, "away": 0.2},
            {"label": "Corners", "home": 8, "away": 2},
            {"label": "Yellow Cards", "home": 1, "away": 1},
            {"label": "Possession", "home": 64, "away": 36},
        ],
    }


class CornerflickTests(unittest.TestCase):
    def test_parse_complete_match(self):
        m = parse_match(sample())
        self.assertEqual(m["home_goals"], 3)
        self.assertEqual(m["statistics"]["xg_home"], 1.77)
        self.assertEqual(m["statistics"]["shots_on_target_away"], 1)
        self.assertEqual(m["provenance"]["origin"], "API-Football")

    def test_missing_is_not_fabricated(self):
        d = sample()
        d["statistics"] = [d["statistics"][0]]
        stats = parse_match(d)["statistics"]
        self.assertNotIn("xg_home", stats)
        self.assertNotIn("corners_home", stats)

    def test_reject_invalid_goal_count(self):
        d = sample()
        d["match"]["score"]["home"] = -1
        with self.assertRaises(ValueError):
            parse_match(d)

    def test_reject_shots_inconsistent(self):
        d = sample()
        d["statistics"][1]["home"] = 99
        with self.assertRaises(ValueError):
            parse_match(d)

    def test_allowlist(self):
        safe_public_url("https://cornerflick.com/football/leagues/la-liga/results/season.json")
        safe_public_url("https://cornerflick.com/football/premier-league/matches/a-v-b-2026-08-21/data.json")
        for url in ("https://api.sofascore.com/api/v1/anything",
                    "https://cornerflick.com/admin/data.json",
                    "http://cornerflick.com/football/leagues/a/results/season.json"):
            with self.assertRaises(ValueError):
                safe_public_url(url)

    def test_season_explicit_dataset_url(self):
        url = "https://cornerflick.com/football/premier-league/matches/a-v-b-2026-08-21/data.json"
        link, count = newest_finished({"matches": [{"status": "finished", "kickoff_at": "2026-08-21T19:00:00Z",
                                                   "dataset_url": url}]})
        self.assertEqual(count, 1)
        self.assertEqual(link, url)
