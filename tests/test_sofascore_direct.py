import io
import json
import unittest
import urllib.error

from scripts.sofascore_direct import (
    ProviderDenied, competition, fetch_json, run, scheduled_events, selected_finished
)


def event(id, status="finished", country="England", league="Premier League"):
    return {
        "id": id, "startTimestamp": 1780257600, "homeTeam": {"name": "Arsenal"},
        "awayTeam": {"name": "Chelsea"}, "status": {"type": status},
        "tournament": {"uniqueTournament": {"name": league},
                       "category": {"name": country}},
        "homeScore": {"current": 2}, "awayScore": {"current": 1}
    }


class DirectTests(unittest.TestCase):
    def test_competition_filter(self):
        self.assertEqual(competition(event(1)), ("england", "premier league"))
        self.assertEqual(len(selected_finished([event(1), event(2, "inprogress"),
                                                 event(3, country="Brazil")])), 1)

    def test_only_supported_endpoints(self):
        with self.assertRaises(ValueError):
            fetch_json("/../../private")
        with self.assertRaises(ValueError):
            fetch_json("/team/123")

    def test_deny_is_terminal(self):
        calls = []
        def denied(request, timeout):
            calls.append(request.full_url)
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", None, None)
        with self.assertRaises(ProviderDenied):
            fetch_json("/sport/football/scheduled-events/2026-10-26", opener=denied)
        self.assertEqual(len(calls), 1)

    def test_collect_normalizes_stats(self):
        calls = []
        def fake(path):
            calls.append(path)
            if "scheduled-events" in path:
                return {"events": [event(10), event(11)]}
            return {"statistics": [{"period": "ALL", "groups": [{"statisticsItems": [
                {"key": "totalShotsOnGoal", "homeValue": 12, "awayValue": 7},
                {"key": "shotsOnGoal", "homeValue": 5, "awayValue": 3},
                {"key": "expectedGoals", "homeValue": "1.4", "awayValue": "0.8"},
            ]}]}]}
        result = run("2026-10-26", mode="collect", max_stats=2,
                     fetcher=fake, sleeper=lambda seconds: None)
        self.assertEqual(result["events"][0]["normalized"]["shots_home"], 12)
        self.assertEqual(result["events"][0]["normalized"]["shots_on_target_home"], 5)
        self.assertEqual(result["events"][0]["normalized"]["xg_home"], 1.4)
        self.assertEqual(result["inspected_statistics"], 2)
        self.assertEqual(len(calls), 3)

    def test_probe_is_one_event_max(self):
        calls = []
        def fake(path):
            calls.append(path)
            if "scheduled-events" in path:
                return {"events": [event(10), event(11)]}
            return {"statistics": [{"period": "ALL", "groups": []}]}
        value = run("2026-10-26", mode="probe", fetcher=fake)
        self.assertEqual(len(calls), 2)
        self.assertEqual(value["events"], [])
        self.assertEqual(value["inspected_statistics"], 1)

    def test_empty_schedule_only_one_call(self):
        calls = []
        def fake(path):
            calls.append(path)
            return {"events": []}
        value = run("2026-10-26", fetcher=fake)
        self.assertEqual(len(calls), 1)
        self.assertEqual(value["finished_in_selected_leagues"], 0)

    def test_bad_schema_is_detected(self):
        with self.assertRaises(ValueError):
            scheduled_events("2026-10-26", fetcher=lambda path: {"unexpected": []})

    def test_limit_is_bounded(self):
        with self.assertRaises(ValueError):
            run("2026-10-26", max_stats=100, fetcher=lambda path: {"events": []})


if __name__ == "__main__":
    unittest.main()
