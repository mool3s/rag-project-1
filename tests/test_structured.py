import tempfile
from pathlib import Path
import unittest

from src.document_pipeline.parsing.pdf_structured import extract_rows, parse_pdf, markdown


class FakePage:
    def extract_words(self):
        return [dict(text=t, x0=x, x1=x+8, top=y, bottom=y+8)
                for t,x,y in [('No',10,5), ('1',10,20), ('A',40,20), ('continued',40,30), ('2',10,40), ('B',40,40)]]


class StructuredTests(unittest.TestCase):
    def test_coordinate_columns_and_continuation(self):
        spec = dict(bbox=[0,0,100,60], data_top=15, columns=['No','Text'],
                    column_edges=[30], merge_continuations=True)
        self.assertEqual(extract_rows(FakePage(), spec), [['1','A continued'],['2','B']])

    def test_wrong_profile_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source.pdf'
            source.write_bytes(b'not a pdf')
            with self.assertRaises(ValueError):
                parse_pdf(source,root/'parsed',root/'clean',root/'assets',{'source_sha256':'wrong'})
            self.assertFalse((root/'parsed').exists())

    def test_excluded_blocks_do_not_render(self):
        doc = dict(source={'name':'Demo'}, blocks=[dict(id='a',type='text',text='secret',excluded=True)])
        self.assertNotIn('secret', markdown(doc,Path('out.md')))


if __name__ == '__main__':
    unittest.main()
