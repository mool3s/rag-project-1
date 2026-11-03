"""Baseline BM25 lokal: indeks inverted JSON, tanpa model atau layanan eksternal."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import unicodedata

TOKEN_PATTERN = r"\d+(?:\.\d+)+|[^\W_]+(?:['’][^\W_]+)*"


def tokenize(text):
    return re.findall(TOKEN_PATTERN, unicodedata.normalize('NFKC', text).casefold())


def build_index(document, k1=1.5, b=0.75):
    if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
        raise ValueError('k1 harus positif dan finite; b harus dalam [0, 1].')
    chunks = document.get('chunks')
    if not isinstance(chunks, list) or not chunks:
        raise ValueError('Korpus harus memiliki list chunks yang tidak kosong.')
    lengths, postings, identifiers = [], defaultdict(list), []
    for position, chunk in enumerate(chunks):
        identifier, text = chunk.get('chunk_id'), chunk.get('text')
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise ValueError('Setiap chunk_id wajib berupa string unik dan tidak kosong.')
        if not isinstance(text, str):
            raise ValueError(f'Text pada {identifier} harus berupa string.')
        identifiers.append(identifier)
        terms = tokenize(text)
        lengths.append(len(terms))
        for term, frequency in Counter(terms).items():
            postings[term].append([position, frequency])
    if not sum(lengths):
        raise ValueError('Tidak ada token yang dapat diindeks.')
    return dict(schema_version='1.0', method='bm25', implementation_version='0.1.0',
                created_at=datetime.now(timezone.utc).isoformat(),
                parameters=dict(k1=k1, b=b),
                preprocessing=dict(normalization='NFKC + casefold', token_pattern=TOKEN_PATTERN,
                                   stopwords=False, stemming=False, query_term_frequency='binary'),
                scoring=dict(idf='log(1 + (N - df + 0.5) / (df + 0.5))',
                             term_score='idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))'),
                document_count=len(chunks), average_document_length=sum(lengths)/len(lengths),
                chunk_ids=identifiers, document_lengths=lengths, postings=dict(postings))


def index_file(source, output, k1=1.5, b=0.75, overwrite=False, validation_note=None):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError('Indeks tidak boleh menimpa JSON chunk.')
    if output.exists() and not overwrite:
        raise FileExistsError('Indeks sudah ada; gunakan --overwrite atau lokasi lain.')
    raw = source.read_bytes()
    document = json.loads(raw.decode('utf-8-sig'))
    index = build_index(document, k1=k1, b=b)
    index['corpus'] = dict(path=Path(os.path.relpath(source.resolve(), output.parent.resolve())).as_posix(),
                           sha256=hashlib.sha256(raw).hexdigest(), document_id=document.get('document_id'))
    index['validation'] = dict(note=validation_note, origin='user_provided' if validation_note else None,
                               scope='indexed_chunks_sha256', artifact_status_unchanged=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
    return index


def rank(index, query, top_k=5):
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
        raise ValueError('top_k harus bilangan bulat positif.')
    scores, matched = defaultdict(float), defaultdict(list)
    n = index['document_count']
    avgdl = index['average_document_length']
    k1, b = index['parameters']['k1'], index['parameters']['b']
    for term in sorted(set(tokenize(query))):
        postings = index['postings'].get(term, [])
        df = len(postings)
        if not df:
            continue
        idf = math.log1p((n - df + 0.5) / (df + 0.5))
        for position, tf in postings:
            dl = index['document_lengths'][position]
            scores[position] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
            matched[position].append(term)
    # Tie-break berdasarkan urutan korpus agar eksperimen dapat diulang.
    ordered = sorted(scores, key=lambda position: (-scores[position], position))[:top_k]
    return [dict(position=position, score=scores[position], matched_terms=matched[position]) for position in ordered]
