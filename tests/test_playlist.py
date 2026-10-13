import random
import unittest

from app.services.playlist import Playlist


def row(key, duration=10, **settings):
    return {"key": key, "duration_seconds": duration, "settings": settings}


class PlaylistTests(unittest.TestCase):
    def test_order_and_no_mid_slot_interruption(self):
        playlist = Playlist()
        rows = [row("clock", 8), row("asset-a", 20), row("weather", 10)]
        self.assertEqual(playlist.select(rows, 0)["key"], "clock")
        self.assertEqual(playlist.select(rows, 8)["key"], "asset-a")
        self.assertEqual(playlist.select(rows, 27)["key"], "asset-a")
        self.assertEqual(playlist.select(rows, 28)["key"], "weather")

    def test_priority_waits_until_loop_completion(self):
        playlist = Playlist()
        rows = [row("asset-a", 50), row("clock", 8, priority_every=20), row("weather", 10)]
        self.assertEqual(playlist.select(rows, 0)["key"], "asset-a")
        playlist.finish_cycle(12)
        self.assertEqual(playlist.deadline, 60)
        self.assertEqual(playlist.select(rows, 59)["key"], "asset-a")
        self.assertEqual(playlist.select(rows, 60)["key"], "clock")
        self.assertEqual(playlist.select(rows, 68)["key"], "weather")

    def test_shuffle_is_inserted_without_losing_regular_order(self):
        playlist = Playlist(random.Random(0))
        rows = [row("a"), row("b"), row("c"), row("bonus", shuffle=True)]
        self.assertEqual([playlist.select(rows, t)["key"] for t in (0, 10, 20, 30, 40)], ["a", "b", "c", "bonus", "a"])

    def test_all_shuffle_and_disabled_current_are_handled(self):
        playlist = Playlist(random.Random(0))
        rows = [row("a", shuffle=True), row("b", shuffle=True)]
        first = playlist.select(rows, 0)
        self.assertNotEqual(first, playlist.select(rows, 10))
        self.assertEqual(playlist.select([row("remaining")], 11)["key"], "remaining")
        self.assertIsNone(playlist.select([], 12))

    def test_elapsed_is_not_wall_clock_and_visits_rotate(self):
        playlist = Playlist()
        rows = [row("clock", 2)]
        playlist.select(rows, 100)
        playlist.select(rows, 102)
        self.assertEqual(playlist.visits["clock"], 2)
        self.assertEqual(playlist.started, 102)
