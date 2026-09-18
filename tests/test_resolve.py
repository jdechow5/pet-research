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
            alaa("Quillfeather Labradoodles", "MA", "quillfeather.example"),
            wala("DM Australian Labradoodles", "MA", "quillfeather.example"),
            self.config,
        )
        self.assertEqual(score, 1.0)
        self.assertIn("same website domain (quillfeather.example)", basis)

    def test_shared_phone_is_near_conclusive(self):
        score, basis = score_pair(
            alaa("Pemberly Downs", "OR", phone="(503) 555-0142"),
            wala("Pemberly Downs ALDs", "OR", phone="503.555.0142"),
            self.config,
        )
        self.assertGreaterEqual(score, 0.95)
        self.assertIn("same phone number", basis)

    def test_state_disagreement_is_penalised(self):
        score, basis = score_pair(
            alaa("Tamarack Bend Labradoodles", "OR"),
            wala("Tamarack Bend Labradoodles", "VA"),
            self.config,
        )
        self.assertLess(score, 0.72)
        self.assertTrue(any("state disagrees" in b for b in basis))

    def test_name_only_match_without_state_needs_confirmation(self):
        result = resolve([alaa("Harrowgate Fen Labradoodles")],
                         [wala("Harrowgate Fen Labradoodles")],
                         self.config)
        self.assertEqual(len(result.pairs), 1)
        self.assertEqual(result.pairs[0][2].status, "review")
        self.assertEqual(result.matched, [])

    def test_name_and_state_match_is_accepted(self):
        result = resolve([alaa("Harrowgate Fen Labradoodles", "MN")],
                         [wala("Harrowgate Fen Australian Labradoodles", "MN")],
                         self.config)
        self.assertEqual(result.pairs[0][2].status, "matched")

    def test_unrelated_kennels_do_not_join(self):
        result = resolve([alaa("Ondwood Labradoodles", "CA")],
                         [wala("Silver Marsh Australian Labradoodles", "CA")],
                         self.config)
        self.assertEqual(result.pairs, [])
        self.assertEqual(len(result.alaa_only), 1)
        self.assertEqual(len(result.wala_only), 1)

    def test_two_wala_records_cannot_both_claim_one_alaa_record(self):
        target = alaa("Tamarack Bend Labradoodles", "OR", "tamarackbend.example")
        result = resolve(
            [target],
            [wala("Tamarack Bend Labradoodles", "OR", "tamarackbend.example"),
             wala("Tamarack Bend Australian Labradoodles", "OR")],
            self.config,
        )
        statuses = sorted(info.status for _, _, info in result.pairs)
        self.assertEqual(statuses, ["matched", "review"])
        self.assertEqual(len(result.matched), 1)
        self.assertTrue(any("matched this ALAA record more strongly" in b
                            for _, _, i in result.pairs for b in i.basis))

    def test_runners_up_are_recorded(self):
        result = resolve(
            [alaa("Pemberly Downs Labradoodles", "OR"),
             alaa("Pemberly Downs Doodles", "OR")],
            [wala("Pemberly Downs Australian Labradoodles", "OR")],
            self.config,
        )
        self.assertTrue(result.pairs[0][2].runners_up)


if __name__ == "__main__":
    unittest.main()
