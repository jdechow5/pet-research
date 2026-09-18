import unittest

from doodle_scout import normalize as n


class TestNormalize(unittest.TestCase):
    def test_same_kennel_variants_score_high(self):
        for left, right in (
            ("Quillfeather Labradoodles", "Quillfeather Australian Labradoodles, LLC"),
            ("Ondwood Doodles", "Ondwood Labradoodles"),
            ("Harrow Gate Labradoodles", "Harrowgate Australian Labradoodles"),
            ("Pemberly's Crossing Australian Labradoodles", "Pemberlys Crossing"),
        ):
            self.assertGreaterEqual(n.name_similarity(left, right), 0.90, (left, right))

    def test_different_kennels_score_low(self):
        for left, right in (
            ("Tamarack Bend Labradoodles", "Tamarack Ridge Labradoodles"),
            ("Ondwood Labradoodles", "Silver Marsh Australian Labradoodles"),
        ):
            self.assertLess(n.name_similarity(left, right), 0.72, (left, right))

    def test_single_shared_token_stays_in_review_band(self):
        # "Willow" alone must not auto-join to "Willow Creek".
        score = n.name_similarity("Tamarack Labradoodles", "Tamarack Bend Labradoodles")
        self.assertTrue(0.72 <= score < 0.90, score)

    def test_registrable_domain(self):
        self.assertEqual(n.registrable_domain("https://WWW.Foo.com/a?b=1"), "foo.com")
        self.assertEqual(n.registrable_domain("breeders.alaa-labradoodles.com"),
                         "alaa-labradoodles.com")
        # co.uk is the public suffix, so eTLD+1 drops the "a" label.
        self.assertEqual(n.registrable_domain("https://a.b.co.uk"), "b.co.uk")
        self.assertEqual(n.registrable_domain("https://kennel.com.au"), "kennel.com.au")
        self.assertEqual(n.registrable_domain(""), "")
        self.assertEqual(n.registrable_domain("not a url"), "")

    def test_region_code(self):
        for value, expected in (
            ("Oregon", "OR"), ("Portland, OR", "OR"), ("OH", "OH"),
            ("British Columbia", "BC"), ("Bend OR 97701", "OR"),
            ("", ""), ("Nowhere", ""),
        ):
            self.assertEqual(n.region_code(value), expected, value)

    def test_phone_digits_ignores_formatting(self):
        self.assertEqual(n.phone_digits("+1 (503) 555-0142"), "5035550142")
        self.assertEqual(n.phone_digits("503.555.0142"), "5035550142")
        self.assertEqual(n.phone_digits("555-0142"), "")

    def test_core_tokens_never_empty(self):
        self.assertTrue(n.core_tokens("The Australian Labradoodles"))


if __name__ == "__main__":
    unittest.main()
