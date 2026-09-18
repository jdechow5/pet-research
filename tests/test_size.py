import unittest

from doodle_scout.config import Config
from doodle_scout.models import SizeVerdict
from doodle_scout.size import classify

CONFIRMED = SizeVerdict.STANDARD_CONFIRMED
LIKELY = SizeVerdict.STANDARD_LIKELY
UNKNOWN = SizeVerdict.UNKNOWN
UNLIKELY = SizeVerdict.STANDARD_UNLIKELY
EXCLUDED = SizeVerdict.STANDARD_EXCLUDED


class TestSize(unittest.TestCase):
    def setUp(self):
        self.config = Config.load()

    def verdict(self, text):
        return classify([("https://example.test/p", text)], self.config).verdict

    # -- the word "standard" that does not mean a dog size ---------------
    def test_breed_standard_document_is_not_a_size_claim(self):
        self.assertEqual(
            self.verdict("We follow the ALAA breed standard in every pairing. "
                         "Our dogs meet the breed standard."),
            UNKNOWN,
        )

    def test_standard_poodle_is_not_a_size_claim(self):
        self.assertEqual(
            self.verdict("Our foundation dogs trace to a standard poodle."),
            UNKNOWN,
        )

    def test_boilerplate_is_not_a_size_claim(self):
        self.assertEqual(
            self.verdict("Our standard contract includes a standard two-year "
                         "health guarantee and standard health testing for "
                         "every puppy and dog."),
            UNKNOWN,
        )
        self.assertEqual(
            self.verdict("Standard vetting is included. Our standard process "
                         "takes four weeks for each puppy."),
            UNKNOWN,
        )

    # -- real size claims ------------------------------------------------
    def test_breed_as_a_verb_before_standard_still_counts(self):
        assessment = classify(
            [("u", "We breed standard size Australian Labradoodles, 21-24 "
                   "inches at the wither, 50-65 lbs.")],
            self.config,
        )
        self.assertEqual(assessment.verdict, CONFIRMED)
        self.assertEqual(assessment.confidence.value, "high")
        self.assertIn("Standard", assessment.sizes_seen)

    def test_size_list_counts(self):
        self.assertEqual(
            self.verdict("We offer two sizes: medium and standard. Our "
                         "standards mature around 55 pounds."),
            CONFIRMED,
        )

    def test_breed_noun_after_standard_counts(self):
        self.assertIn(self.verdict("Our standard girls are retiring this year."),
                      (CONFIRMED, LIKELY))

    # -- exclusions ------------------------------------------------------
    def test_mini_and_medium_only_is_excluded(self):
        assessment = classify(
            [("u", "We breed miniature and medium sizes only. No standards "
                   "are available.")],
            self.config,
        )
        self.assertEqual(assessment.verdict, EXCLUDED)
        # "No standards available" must not be read as offering standards.
        self.assertNotIn("Standard", assessment.sizes_seen)
        self.assertTrue(assessment.evidence[0].quote)

    def test_explicit_refusal_is_excluded(self):
        self.assertEqual(
            self.verdict("We do not breed standard Australian Labradoodles."),
            EXCLUDED,
        )

    def test_only_smaller_sizes_mentioned_is_unlikely(self):
        self.assertEqual(
            self.verdict("All of our puppies are miniature, 14-16 inches."),
            UNLIKELY,
        )

    def test_silent_site_is_unknown_not_excluded(self):
        # Never discard a program for saying nothing; ask instead.
        self.assertEqual(
            self.verdict("Welcome to our family program. Contact us about litters."),
            UNKNOWN,
        )

    def test_empty_input_is_unknown(self):
        self.assertEqual(classify([], self.config).verdict, UNKNOWN)

    def test_measurements_raise_confidence(self):
        low = classify([("u", "We raise standard size labradoodles.")], self.config)
        high = classify(
            [("u", "We raise standard size labradoodles; adults are 21-23 "
                   "inches and 55-60 lbs.")],
            self.config,
        )
        self.assertEqual(high.confidence.value, "high")
        self.assertNotEqual(low.confidence.value, "high")


if __name__ == "__main__":
    unittest.main()
