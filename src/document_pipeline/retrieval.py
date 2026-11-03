"""Pencarian chunk dari indeks BM25; verifikasi hash korpus sebelum retrieval."""
import hashlib
import json
from pathlib import Path

from .indexing.bm25 import rank, tokenize


def search(index_path, query, top_k=5):
    index_path = Path(index_path)
    index = json.loads(index_path.read_text(encoding='utf-8'))
    if index.get('method') != 'bm25' or index.get('schema_version') != '1.0':
        raise ValueError('Format indeks BM25 tidak didukung.')
    corpus_path = (index_path.parent / index['corpus']['path']).resolve()
    raw = corpus_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != index['corpus']['sha256']:
        raise ValueError('JSON chunk berubah sejak indexing. Bangun ulang indeks agar hasil tetap konsisten.')
    corpus = json.loads(raw.decode('utf-8-sig'))
    if [c['chunk_id'] for c in corpus['chunks']] != index['chunk_ids']:
        raise ValueError('Urutan/ID chunk tidak cocok dengan indeks.')
    hits = []
    for rank_number, hit in enumerate(rank(index, query, top_k), 1):
        chunk = corpus['chunks'][hit['position']]
        hits.append(dict(rank=rank_number, score=hit['score'], chunk_id=chunk['chunk_id'],
                         text=chunk['text'], section_path=chunk.get('section_path', []),
                         pages=chunk.get('pages', []), source=corpus.get('source'),
                         source_block_ids=chunk.get('source_block_ids', []),
                         content_types=chunk.get('content_types', []), asset_refs=chunk.get('asset_refs', []),
                         status=chunk.get('status'), access=chunk.get('access'), matched_terms=hit['matched_terms']))
    return dict(method='bm25', query=query, query_tokens=sorted(set(tokenize(query))), top_k=top_k,
                corpus_sha256=index['corpus']['sha256'], parameters=index['parameters'],
                validation=index.get('validation'), results=hits)
