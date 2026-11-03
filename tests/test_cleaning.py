import unittest
from src.document_pipeline.cleaning import clean_text


class CleaningTests(unittest.TestCase):
    def test_section_removal_stops_before_next_peer(self):
        text = '# Artikel\n## Daftar Isi\nPendahuluan ... 1\n### Sub\nx\n## Pendahuluan\nPenting\n'
        cleaned, report = clean_text(text, {"exclude_sections": ["Daftar Isi"]})
        self.assertNotIn('Pendahuluan ...', cleaned)
        self.assertIn('## Pendahuluan\nPenting', cleaned)
        self.assertEqual(report['changes'][0]['rule'], 'exclude_section')

    def test_uncertain_plain_heading_never_deletes_body(self):
        text = 'Daftar Isi\nPendahuluan 1\nPenting\n'
        cleaned, report = clean_text(text, {"exclude_sections": ["Daftar Isi"]})
        self.assertIn('Penting', cleaned)
        self.assertTrue(any(r['kind'] == 'section_boundary_uncertain' for r in report['review_items']))

    def test_numeric_tables_symbols_and_references_preserved(self):
        text = '992\n1 2 3 71.52\n| A | B |\n| - | - |\nREFERENCES\n[1] Source\nα = 0.05\n\uf061\n'
        cleaned, report = clean_text(text)
        for value in ['992', '1 2 3 71.52', '| A | B |', '[1] Source', 'α = 0.05', '\uf061']:
            self.assertIn(value, cleaned)
        self.assertEqual(report['status'], 'needs_review')

    def test_source_mapping_after_profile_removal(self):
        cleaned, report = clean_text('Header\nText\n', {'remove_line_patterns': ['Header']})
        self.assertEqual(cleaned, 'Text\n')
        self.assertEqual(report['source_mapping']['lines'], [{'output_line': 1, 'source_lines': [2]}])

    def test_fenced_code_is_not_cleaned_or_used_as_boundary(self):
        text = '```text\nHeader\nREFERENCES\n\n\n```\nBody\n'
        cleaned, _ = clean_text(text, {'remove_line_patterns': ['Header']})
        self.assertEqual(cleaned, text)

    def test_decimal_in_body_is_not_a_heading(self):
        text = '0.010. The W value, being close to 1, indicates normality\n'
        cleaned, _ = clean_text(text)
        self.assertEqual(cleaned, text)


if __name__ == '__main__':
    unittest.main()
