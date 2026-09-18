import unittest

from doodle_scout.dom import parse


class TestDom(unittest.TestCase):
    def test_unclosed_table_cells(self):
        doc = parse("<table><tr><td>a<td>b<tr><td>c<td>d</table>")
        self.assertEqual([[c.text for c in row] for row in doc.rows()],
                         [["a", "b"], ["c", "d"]])

    def test_script_and_style_are_not_text(self):
        doc = parse("<div>keep<script>var secret=1</script><style>p{}</style></div>")
        self.assertEqual(doc.text, "keep")

    def test_block_text_preserves_line_breaks(self):
        doc = parse("<td>Kennel Name<br>Portland, OR<br>503-555-0100</td>")
        self.assertEqual(
            doc.find("td").block_text.splitlines(),
            ["Kennel Name", "Portland, OR", "503-555-0100"],
        )

    def test_nbsp_is_normal_space(self):
        self.assertEqual(parse("<p>Chagrin&nbsp;Falls</p>").text, "Chagrin Falls")

    def test_attribute_and_class_queries(self):
        doc = parse('<img class="paw emblem" alt="Platinum Paw" src="/p.png">')
        img = doc.find("img", class_="paw")
        self.assertIsNotNone(img)
        self.assertEqual(img.get("alt"), "Platinum Paw")
        self.assertTrue(img.has_class("EMBLEM"))

    def test_find_parent(self):
        doc = parse("<table><tr><td><a href='#'>x</a></td></tr></table>")
        self.assertEqual(doc.find("a").find_parent("tr").tag, "tr")

    def test_malformed_input_does_not_raise(self):
        for bad in ("<<<>>", "<div><p>unclosed", "", "<a href=>x</a>", "<!-- -->"):
            self.assertIsNotNone(parse(bad))


if __name__ == "__main__":
    unittest.main()
