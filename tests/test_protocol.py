"""End-to-end protocol test against bundled fixtures.

This proves the funnel, the joining, the size filter, the scoring and the
report. It does not prove that the live ALAA or WALA markup looks like the
fixtures; only a live run can do that.
"""

import json
import tempfile
import unittest
from pathlib import Path

from doodle_scout.config import Config
from doodle_scout.protocol import run
from doodle_scout.report import render_html, write_outputs
from doodle_scout.testing import FixtureClient


class TestProtocolEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Config.load()
        cls.result = run(FixtureClient(), cls.config, read_sites=True)

    def test_funnel_narrows_at_every_stage(self):
        counts = [entry["remaining"] for entry in self.result.funnel]
        self.assertEqual(counts, [5, 3, 2, 1])
        self.assertEqual(
            [e["stage"][:1] for e in self.result.funnel], ["0", "1", "2", "3"]
        )

    def test_only_platinum_survives_stage_one(self):
        # The fixture has a Gold breeder and an unawarded breeder.
        names = {c.kennel for c in self.result.shortlist + self.result.near_misses}
        self.assertNotIn("Goldenrod Meadow Doodles", names)

    def test_mini_and_medium_program_is_excluded_at_stage_three(self):
        excluded = {c.kennel: c for c in self.result.near_misses}
        silver = excluded["Silver Marsh Labradoodles"]
        self.assertEqual(silver.size.verdict.value, "standard_excluded")
        self.assertTrue(any("size assessment" in r for r in silver.exclusion_reasons))

    def test_platinum_without_a_wala_match_becomes_a_near_miss(self):
        near = {c.kennel for c in self.result.near_misses}
        self.assertIn("Tamarack Bend Labradoodles", near)

    def test_shortlist_entry_is_fully_evidenced(self):
        self.assertEqual(len(self.result.shortlist), 1)
        candidate = self.result.shortlist[0]
        self.assertEqual(candidate.kennel, "Quillfeather Labradoodles")
        self.assertEqual(candidate.match.status, "matched")
        self.assertEqual(candidate.size.verdict.value, "standard_confirmed")
        self.assertTrue(candidate.size.evidence)
        found = {s.key for s in candidate.signals if s.points >= 0.99}
        for expected in ("raised_in_home", "early_development_curriculum",
                         "temperament_testing", "breeding_dog_transparency",
                         "health_guarantee", "litter_cadence_disclosed"):
            self.assertIn(expected, found)

    def test_legacy_all_star_rating_triggers_a_followup(self):
        candidate = self.result.shortlist[0]
        self.assertTrue(
            any("legacy 'All Star'" in f for f in candidate.followups),
            candidate.followups,
        )

    def test_ofa_check_is_unverified_until_a_human_confirms(self):
        signal = self.result.shortlist[0].signal("ofa_verified")
        self.assertFalse(signal.verified)
        self.assertEqual(signal.points, 0.0)

    def test_verification_links_are_offered(self):
        links = self.result.shortlist[0].verification_links
        self.assertTrue(any("OFA" in label for label in links))
        self.assertTrue(any("ALAA" in label for label in links))

    def test_appearance_is_never_scored(self):
        keys = {s.key for s in self.result.shortlist[0].signals}
        for forbidden in ("beauty", "appearance", "looks", "conformation", "coat"):
            self.assertNotIn(forbidden, keys)

    def test_outputs_are_written_and_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = write_outputs(self.result, Path(tmp))
            self.assertEqual(set(written), {"html", "json", "csv"})
            html = written["html"].read_text()
            self.assertIn("Quillfeather Labradoodles", html)
            self.assertNotIn("<script", html.lower())
            self.assertNotIn("http://localhost", html)
            payload = json.loads(written["json"].read_text())
            self.assertEqual(len(payload["shortlist"]), 1)
            self.assertEqual(len(payload["funnel"]), 4)
            self.assertIn("rank,kennel", written["csv"].read_text())

    def test_report_states_what_it_cannot_measure(self):
        html = render_html(self.result)
        self.assertIn("Appearance is not scored", html)
        self.assertIn("membership organizations", html)


class TestEmptyRun(unittest.TestCase):
    def test_no_sources_produces_an_honest_empty_report(self):
        class DeadClient(FixtureClient):
            def _resolve(self, url):
                return None

        result = run(DeadClient(), Config.load(), read_sites=False)
        self.assertEqual(result.shortlist, [])
        html = render_html(result)
        self.assertIn("as likely to mean a source did not parse", html)
        self.assertTrue(any("UNREACHABLE" in n or "unreachable" in n
                            for n in result.notes))


if __name__ == "__main__":
    unittest.main()


class TestManualOverlay(unittest.TestCase):
    """The overlay file is hand-edited, so it has to tolerate mistakes."""

    def _load(self, text):
        from doodle_scout.protocol import load_manual_overlay

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.json"
            path.write_text(text)
            return load_manual_overlay(path)

    def test_comment_keys_and_scalars_are_ignored(self):
        overlay = self._load(
            '{"_about": "a note, not a kennel",'
            ' "oops": 7,'
            ' "Quillfeather Labradoodles": {"ofa_verified": true}}'
        )
        self.assertEqual(overlay, {"quillfeather labradoodles": {"ofa_verified": True}})

    def test_malformed_json_does_not_stop_a_run(self):
        self.assertEqual(self._load("{not json"), {})

    def test_top_level_list_is_ignored(self):
        self.assertEqual(self._load('["nope"]'), {})

    def test_shipped_starter_file_is_loadable(self):
        from doodle_scout.cli import cmd_init
        from doodle_scout.config import PROJECT_ROOT
        from doodle_scout.protocol import load_manual_overlay

        cmd_init(None)
        overlay = load_manual_overlay(PROJECT_ROOT / "data" / "manual" / "notes.json")
        self.assertIsInstance(overlay, dict)
        for value in overlay.values():
            self.assertIsInstance(value, dict)

    def test_exclude_flag_removes_a_kennel_from_the_shortlist(self):
        from doodle_scout.config import Config
        from doodle_scout.protocol import run
        from doodle_scout.testing import FixtureClient

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.json"
            path.write_text('{"quillfeather labradoodles": {"exclude": true}}')
            result = run(FixtureClient(), Config.load(), manual_path=path)
        self.assertEqual(result.shortlist, [])
        self.assertTrue(any("excluded 1 kennel" in n for n in result.notes))


class TestSampleDataIsLabelled(unittest.TestCase):
    """A fixture run must never be mistakable for real findings."""

    def test_banner_appears_only_when_flagged(self):
        from doodle_scout.config import Config
        from doodle_scout.protocol import run
        from doodle_scout.testing import FixtureClient

        flagged = render_html(
            run(FixtureClient(), Config.load(), read_sites=False, sample_data=True)
        )
        self.assertIn("Sample data, not real breeders", flagged)

        unflagged = render_html(
            run(FixtureClient(), Config.load(), read_sites=False)
        )
        self.assertNotIn("Sample data, not real breeders", unflagged)

    def test_fixtures_use_only_reserved_example_domains(self):
        from pathlib import Path as _Path
        import re as _re

        fixtures = _Path(__file__).parent / "fixtures"
        hosts = set()
        for path in fixtures.rglob("*.html"):
            for match in _re.finditer(r"https?://([\w.-]+)", path.read_text()):
                hosts.add(match.group(1).lower())
        offenders = [h for h in hosts if not h.endswith(".example")]
        self.assertEqual(offenders, [], f"non-.example hosts in fixtures: {offenders}")
