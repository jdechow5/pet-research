import unittest
from pathlib import Path

from doodle_scout.http_client import Response
from doodle_scout.sources.alaa import detect_awards, parse_listing
from doodle_scout.sources.wala import _merge, normalize_rating, parse_breeder_page
from doodle_scout.dom import parse

FIXTURES = Path(__file__).parent / "fixtures"


def response_for(name, url):
    return Response(url=url, status=200,
                    text=(FIXTURES / name).read_text(),
                    retrieved_at="2026-09-18T00:00:00+00:00")


class TestAlaa(unittest.TestCase):
    def setUp(self):
        self.records = parse_listing(
            response_for("alaa_listing.html",
                         "https://ilainc.net/guest/breedersearch.aspx"),
            "https://ilainc.net",
        )
        self.by_name = {r.kennel: r for r in self.records}

    def test_duplicate_rows_collapse_by_registry_id(self):
        self.assertEqual(len(self.records), 5)

    def test_reads_id_state_city_and_contacts(self):
        record = self.by_name["Tamarack Bend Labradoodles"]
        self.assertEqual(record.registry_id, "100002")
        self.assertEqual((record.city, record.region), ("Wickford", "OH"))
        self.assertEqual(record.domain, "tamarackbend.example")
        self.assertEqual(record.email, "hello@tamarackbend.example")
        self.assertEqual(record.phone, "440-555-0188")

    def test_kennel_name_cannot_manufacture_an_award(self):
        # "Silver Marsh" holds a Platinum paw and no Silver paw.
        awards = self.by_name["Silver Marsh Labradoodles"].awards
        self.assertEqual(awards, ["Platinum (image)"])

    def test_word_boundary_stops_golden_matching_gold(self):
        awards = self.by_name["Goldenrod Meadow Doodles"].awards
        self.assertEqual(awards, ["Gold (image)"])

    def test_text_only_award_is_marked_as_weaker_evidence(self):
        self.assertEqual(self.by_name["Quillfeather Labradoodles"].awards,
                         ["Platinum (text_paw)"])

    def test_no_award_means_no_award(self):
        self.assertEqual(self.by_name["Ondwood Labradoodles"].awards, [])

    def test_bare_text_mention_is_flagged_not_trusted(self):
        block = parse("<tr><td>Platinum Hollow Kennels</td><td>silver</td></tr>")
        awards = dict(detect_awards(block, "Platinum Hollow Kennels"))
        self.assertEqual(awards.get("Silver"), "text_bare")
        self.assertNotIn("Platinum", awards)


class TestWala(unittest.TestCase):
    def test_rating_normalization(self):
        cases = {"Three Diamond Breeder": "Three Diamond", "2 Diamond": "Two Diamond",
                 "One Diamond Award": "One Diamond", "All-Star Breeder": "All Star",
                 "THREE DIAMONDS": "Three Diamond", "WALA member": ""}
        for text, expected in cases.items():
            self.assertEqual(normalize_rating(text), expected, text)

    def test_table_layout(self):
        records = parse_breeder_page(
            response_for("wala_allstar.html",
                         "https://www.walalabradoodles.org/walabreeder-1/"
                         "all-star-breeders-of-labradoodles"),
            "All Star",
        )
        self.assertEqual(len(records), 3)
        first = records[0]
        self.assertEqual(first.registry_id, "WALA-0101-00002")
        self.assertEqual(first.kennel, "Harrowgate Fen Labradoodles")
        self.assertEqual(first.owner, "Wren Aldacott")
        self.assertEqual((first.city, first.region), ("Kestrelton", "MN"))
        self.assertEqual(first.awards, ["All Star"])

    def test_repeater_layout_and_per_record_tier(self):
        records = parse_breeder_page(
            response_for("wala_diamond.html",
                         "https://www.walalabradoodles.org/about-wala/"
                         "diamond-rewards-program")
        )
        tiers = {r.kennel: r.awards for r in records}
        self.assertEqual(tiers["Harrowgate Fen Labradoodles"], ["Three Diamond"])
        self.assertEqual(tiers["Pemberly Downs Australian Labradoodles"],
                         ["Two Diamond"])

    def test_merge_keeps_strongest_rating_first(self):
        allstar = parse_breeder_page(
            response_for("wala_allstar.html", "https://x/all-star-breeders"), "All Star")
        diamond = parse_breeder_page(
            response_for("wala_diamond.html", "https://x/diamond-rewards-program"))
        merged = {r.registry_id: r.awards for r in _merge(allstar + diamond)}
        self.assertEqual(merged["WALA-0101-00002"][0], "Three Diamond")


if __name__ == "__main__":
    unittest.main()
