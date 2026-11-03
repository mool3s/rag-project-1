import unittest
from src.document_pipeline.chunking import chunk_document


def block(identifier, kind, text='', **extra):
    return dict(id=identifier, type=kind, text=text, source={'page':1}, **extra)


class HeaderChunkingTests(unittest.TestCase):
    def test_heading_boundaries_hierarchy_and_unlimited_length(self):
        doc = dict(document_id='d', source={}, blocks=[
            block('p','text','preamble'), block('h','heading','Parent',level=2),
            block('t','text','x'*10000), block('s','heading','Child',level=3),
            block('u','text','child text'), block('n','heading','Next',level=2)])
        chunks = chunk_document(doc)['chunks']
        self.assertEqual(len(chunks),4)
        self.assertEqual(chunks[0]['section_path'],[])
        self.assertIn('x'*10000,chunks[1]['text'])
        self.assertEqual(chunks[2]['section_path'],['Parent','Child'])
        self.assertEqual(chunks[3]['section_path'],['Next'])
        self.assertNotIn('child text',chunks[1]['text'])

    def test_exclusion_table_asset_and_permissions(self):
        doc = dict(document_id='d', source={}, status='needs_review', access={'groups':['test']}, blocks=[
            block('h','heading','Header',level=2), block('x','text','footer',excluded=True),
            block('t','table', columns=['A','B'], rows=[['1','2']]),
            block('i','image',asset_path='image.png')])
        result = chunk_document(doc)['chunks'][0]
        self.assertNotIn('footer',result['text'])
        self.assertIn('| 1 | 2 |',result['text'])
        self.assertEqual(result['asset_refs'],['image.png'])
        self.assertEqual(result['access'],{'groups':['test']})
        self.assertEqual(result['status'],'needs_review')
        self.assertEqual(result['cleaned_block_ids'],['h','t','i'])
