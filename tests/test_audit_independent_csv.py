import unittest
from scripts.audit_independent_csv import close_team, compare
class CheckTests(unittest.TestCase):
    def test_clubs_fuzzy_and_aliases(self):
        self.assertTrue(close_team("Hull City","Hull"))
        self.assertTrue(close_team("Inter","Internazionale"))
        self.assertFalse(close_team("Manchester City","Manchester United"))
    def test_score_comparison(self):
        idx=[{"status":"finished","kickoff_at":"2026-10-25T12:00:00Z","home_team":"Hull City","away_team":"Brentford","home_score":1,"away_score":1}]
        rows=[{"date":"2026-10-25","home":"Hull","away":"Brentford","ft_home":"1","ft_away":"1"}]
        got=compare(idx,rows)["coverage"]
        self.assertEqual(got["matched"],1)
        self.assertEqual(got["results_agree"],1)
    def test_disagreements_separate_from_nonmatch(self):
        idx=[{"status":"finished","kickoff_at":"2026-10-25T12:00:00Z","home_team":"Hull City","away_team":"Brentford","home_score":3,"away_score":1}]
        rows=[{"date":"2026-10-25","home":"Hull","away":"Brentford","ft_home":"1","ft_away":"1"}]
        got=compare(idx,rows)["coverage"]
        self.assertEqual(got["results_disagree"],1)
