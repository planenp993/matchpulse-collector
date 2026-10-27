import unittest
from scripts.audit_leagues_full import normalize, compare_league, COMPETITIONS

class FullAuditTests(unittest.TestCase):
    def test_catalog_count(self):
        self.assertEqual(len(COMPETITIONS), 18)
    def test_normalize_unicode(self):
        self.assertEqual(normalize("Atlético"), normalize("Atletico"))
    def test_independent_score_compares(self):
        local = [{"kickoff_at":"2026-09-10T17:00:00Z", "home_team":"Atlético",
                  "away_team":"Sevilla", "home_score":2, "away_score":0}]
        ref = [{"date":"2026-09-10","home":"Atletico","away":"Sevilla",
                "home_goals":2,"away_goals":1}]
        c=compare_league(local, ref)
        self.assertEqual(c["score_disagreement"], 1)
        self.assertEqual(c["match_not_identified_in_reference"], 0)
    def test_nonmatch_is_not_score_disagreement(self):
        local = [{"kickoff_at":"2026-09-10T17:00:00Z", "home_team":"Angola",
                  "away_team":"Sevilla", "home_score":2, "away_score":0}]
        ref = [{"date":"2026-09-10","home":"Atletico","away":"Sevilla",
                "home_goals":2,"away_goals":0}]
        c=compare_league(local, ref)
        self.assertEqual(c["score_disagreement"], 0)
        self.assertEqual(c["match_not_identified_in_reference"], 1)
