import json
import math
from pathlib import Path
import tempfile
import unittest

from src.document_pipeline.indexing.bm25 import build_index, index_file, rank, tokenize
from src.document_pipeline.retrieval import search


def corpus(*texts):
    return dict(source={'name':'test.pdf'}, document_id='d', chunks=[
        dict(chunk_id=f'c{i}', text=text, pages=[i+1], section_path=[f'Section {i}'])
        for i,text in enumerate(texts)])


class BM25Tests(unittest.TestCase):
    def test_score_matches_hand_calculation_and_ranking(self):
        index = build_index(corpus('alpha alpha', 'beta beta'))
        hits = rank(index, 'alpha')
        self.assertEqual(hits[0]['position'],0)
        self.assertAlmostEqual(hits[0]['score'],math.log(2)*2*2.5/(2+1.5))
        self.assertEqual(hits,rank(index,'alpha alpha'))

    def test_unknown_empty_query_and_ties(self):
        index = build_index(corpus('shared', 'shared', ''))
        self.assertEqual(rank(index,'unknown'),[])
        self.assertEqual(rank(index,''),[])
        self.assertEqual([r['position'] for r in rank(index,'shared')],[0,1])
        with self.assertRaises(ValueError):rank(index,'shared',0)

    def test_tokenization_preserves_decimal_and_normalizes_case(self):
        self.assertEqual(tokenize('SUS 71.52 ＡＢＣ'),['sus','71.52','abc'])

    def test_invalid_corpus_and_parameters(self):
        for doc in [corpus(),corpus(''),{'chunks':[{'chunk_id':'x','text':'a'},{'chunk_id':'x','text':'b'}]}]:
            with self.assertRaises(ValueError):build_index(doc)
        for k1,b in [(0,.75),(1.5,2),(float('nan'),.75)]:
            with self.assertRaises(ValueError):build_index(corpus('a'),k1,b)

    def test_disk_index_metadata_hash_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'chunks.json';target=root/'indexes'/'bm25.json'
            source.write_text(json.dumps(corpus('alpha','beta')),encoding='utf-8')
            before=source.read_bytes()
            index_file(source,target)
            result=search(target,'beta',1)['results'][0]
            self.assertEqual(result['chunk_id'],'c1')
            self.assertEqual(result['pages'],[2])
            self.assertEqual(source.read_bytes(),before)
            with self.assertRaises(FileExistsError):index_file(source,target)
            source.write_text(json.dumps(corpus('different','beta')),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'berubah'):search(target,'beta')
