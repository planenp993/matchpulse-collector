import unittest
from scripts.fotmob_adapter import parse_stats

class FotMobAdapterTests(unittest.TestCase):
    def test_extract_core_stats(self):
        doc = {"content":{"stats":{"Periods":{"All":[{"stats":[
            {"title":"Expected goals (xG)","stats":["1.75","0.92"]},
            {"title":"Total shots","stats":["15","9"]},
            {"title":"Shots on target","stats":["7","4"]},
            {"title":"Ball possession","stats":["55%","45%"]}
        ]}]}}}}
        got = parse_stats(doc)
        self.assertEqual(got["xg_home"], 1.75)
        self.assertEqual(got["shots_on_target_away"], 4)
        self.assertEqual(got["possession_home"], 55)
    def test_missing_stays_missing(self):
        self.assertEqual(parse_stats({}), {})
    def test_reject_conflict(self):
        doc = {"content":{"stats":{"Periods":{"All":[{"stats":[
            {"title":"Total shots","stats":[10,9]},
            {"title":"Total shots","stats":[11,9]}
        ]}]}}}}
        with self.assertRaises(ValueError):
            parse_stats(doc)
