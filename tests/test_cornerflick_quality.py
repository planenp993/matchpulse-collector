import unittest
from scripts.cornerflick_quality import scan_index, sample_positions, reviewed_team_id, audit
from scripts.cornerflick_source import BASE

URL=BASE+"/football/mls/matches/a-v-angola-2026-10-26/data.json"
ROW={"id":"cf1","home_team":"LAFC","away_team":"Angola","home_score":2,
     "away_score":2,"kickoff_at":"2026-10-26T01:00:00+00:00",
     "status":"finished","dataset_url":URL}

class QualityTests(unittest.TestCase):
    def test_countries_are_quarantined(self):
        v=scan_index([ROW])
        self.assertEqual(v["counts"]["country_in_club_competition"],1)
        self.assertEqual(v["counts"]["flagged"],1)

    def test_duplicate_ids_and_matches(self):
        v=scan_index([ROW,ROW])
        self.assertEqual(v["counts"]["duplicate_id"],1)
        self.assertEqual(v["counts"]["duplicate_fixture"],1)

    def test_no_silent_team_mapping(self):
        with self.assertRaises(ValueError):
            reviewed_team_id("mls","Angola",{"mls":{"Angola":{"reviewed":True,"team_id":"LA Galaxy"}}})
        with self.assertRaises(ValueError):
            reviewed_team_id("mls","LAFC",{})
        self.assertEqual(reviewed_team_id("mls","LAFC",{"mls":{"LAFC":{
            "reviewed":True,"team_id":"LAFC-verified"}}}),"LAFC-verified")

    def test_sampling_spans_whole_season(self):
        self.assertEqual(sample_positions(10,3),[0,4,9])
        self.assertEqual(sample_positions(0,6),[])
        with self.assertRaises(ValueError):
            sample_positions(2000,2000)

    def test_local_stub_end_to_end(self):
        def fake(url):
            return {"matches":[ROW]} if url.endswith("season.json") and "mls" in url else (
                {"matches":[]} if url.endswith("season.json") else {
                 "match":{"id":"cf1","status":"finished","kickoff_at":ROW["kickoff_at"],
                          "score":{"home":2,"away":2}},
                 "teams":{"home":{"name":"LAFC"},"away":{"name":"Angola"}},
                 "statistics":[{"label":"xG","home":1.5,"away":1.1}],
                 "meta":{"source":"api-football"}})
        v=audit(2,fetcher=fake,sleeper=lambda _:None)
        self.assertEqual(v["totals"]["indexed"],1)
        self.assertEqual(v["totals"]["sampled"],1)
        self.assertEqual(v["totals"]["metric_xg"],1)
        self.assertFalse(v["production_ingestion_enabled"])
