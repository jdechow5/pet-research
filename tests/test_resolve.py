import unittest

from doodle_scout.config import Config
from doodle_scout.models import BreederRecord, Registry
from doodle_scout.resolve import resolve, score_pair


def alaa(kennel, region="", domain="", phone="", email=""):
    return BreederRecord(registry=Registry.ALAA, kennel=kennel, region=region,
                         domain=domain, website=f"https://{domain}" if domain else "",
                         phone=phone, email=email)


def wala(kennel, region="", domain="", phone="", email="", awards=("Three Diamond",)):
    return BreederRecord(registry=Registry.WALA, kennel=kennel, region=region,
                         domain=domain, website=f"https://{domain}" if domain else "",
                         phone=phone, email=email, awards=list(awards))


class TestResolve(unittest.TestCase):
    def setUp(self):
        self.config = Config.load()

    def test_shared_domain_is_conclusive_even_with_different_names(self):
        score, basis = score_pair(
            alaa("Draycot Meadows", "MA", "draycotmeadows.com"),
            wala("DM Australian Labradoodles", "MA", "draycotmeadows.com"),
            self.config,
        )
        self.assertEqual(score, 1.0)
        self.assertIn("same website domain (draycotmeadows.com)", basis)

    def test_shared_phone_is_near_conclusive(self):
        score, basis = score_pair(
            alaa("Cascade Summit", "OR", phone="(503) 555-0142"),
            wala("Cascade Summit ALDs", "OR", phone="503.555.0142"),
            self.config,
        )
        self.assertGreaterEqual(score, 0.95)
        self.assertIn("same phone number", basis)

    def test_state_disagreement_is_penalised(self):
        score, basis = score_pair(
            alaa("Willow Creek Labradoodles", "OR"),
            wala("Willow Creek Labradoodles", "VA"),
            self.config,
        )
        self.assertLess(score, 0.72)
        self.assertTrue(any("state disagrees" in b for b in basis))

    def test_name_only_match_without_state_needs_confirmation(self):
        result = resolve([alaa("Hastings Hollow Labradoodles")],
                         [wala("Hastings Hollow Labradoodles")],
                         self.config)
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.pairs[0][2].status, "review")
        self.assertEqual(result.matched, [])

    def test_name_and_state_match_is_accepted(self):
        result = resolve([alaa("Hastings Hollow Labradoodles", "MN")],
                         [wala("Hastings Hollow Australian Labradoodles", "MN")],
                         self.config)
        self.assertEqual(result.pairs[0][2].status, "matched")

    def test_unrelated_kennels_do_not_join(self):
        result = resolve([alaa("Long Bay Labradoodles", "CA")],
                         [wala("Sea Spray Australian Labradoodles", "CA")],
                         self.config)
        self.assertEqual(result.pairs, [])
        self.assertEqual(len(result.alaa_only), 1)
        self.assertEqual(len(result.wala_only), 1)

    def test_two_wala_records_cannot_both_claim_one_alaa_record(self):
        target = alaa("Willow Creek Labradoodles", "OR", "willowcreekald.com")
        result = resolve(
            [target],
            [wala("Willow Creek Labradoodles", "OR", "willowcreekald.com"),
             wala("Willow Creek Australian Labradoodles", "OR")],
            self.config,
        )
        statuses = sorted(info.status for _, _, info in result.pairs)
        self.assertEqual(statuses, ["matched", "review"])
        self.assertEqual(len(result.matched), 1)
        self.assertTrue(any("matched this ALAA record more strongly" in b
                            for _, _, i in result.pairs for b in i.basis))

    def test_runners_up_are_recorded(self):
        result = resolve(
            [alaa("Cascade Summit Labradoodles", "OR"),
             alaa("Cascade Summit Doodles", "OR")],
            [wala("Cascade Summit Australian Labradoodles", "OR")],
            self.config,
        )
        self.assertTrue(result.pairs[0][2].runners_up)


if __name__ == "__main__":
    unittest.main()
