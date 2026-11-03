import copy
import hashlib
import json
from pathlib import Path


def block_text(block):
    if block['type'] == 'table':
        cell = lambda v: str(v).replace('|', '\\|').replace('\n', ' ')
        lines = [block.get('label', 'Table'),
                 '| ' + ' | '.join(map(cell, block['columns'])) + ' |',
                 '| ' + ' | '.join('---' for _ in block['columns']) + ' |']
        lines += ['| ' + ' | '.join(map(cell, row)) + ' |' for row in block['rows']]
        lines += [' '.join(v for v in row if v) for row in block.get('summary_rows', [])]
        return '\n'.join(lines)
    # Isi visual tidak diterjemahkan menjadi teks; aset tersedia di blocks/asset_refs.
    return block.get('text', '')


def chunk_document(document):
    chunks, pending, stack = [], [], []

    def flush():
        if not pending:
            return
        index = len(chunks) + 1
        kinds = sorted({b['type'] for b in pending})
        chunks.append(dict(
            chunk_id=f"{document['document_id']}_chunk_{index:04d}",
            content_type='section', content_types=kinds,
            text='\n\n'.join(t for b in pending if (t := block_text(b))),
            source_block_ids=[sid for b in pending for sid in b.get('source_block_ids', [b['id']])],
            cleaned_block_ids=[b['id'] for b in pending],
            pages=sorted({b['source']['page'] for b in pending}),
            section_path=[title for _, title in stack],
            heading_id=pending[0]['id'] if pending[0]['type'] == 'heading' else None,
            asset_refs=[b['asset_path'] for b in pending if b.get('asset_path')],
            status='needs_review' if document.get('status') == 'needs_review' or
                   any(b.get('status') == 'needs_review' for b in pending) else 'chunked_not_validated',
            access=copy.deepcopy(document.get('access')),
            blocks=copy.deepcopy(pending)))
        pending.clear()

    for block in document['blocks']:
        if block.get('excluded'):
            continue
        if block['type'] == 'heading':
            flush()
            stack = [(level, title) for level, title in stack if level < block['level']]
            stack.append((block['level'], block['text']))
        pending.append(block)
    flush()
    return dict(schema_version='1.0', document_id=document['document_id'],
                source=copy.deepcopy(document['source']),
                chunking=dict(method='header_based', version='0.1.0',
                              config=dict(boundary='every_heading', max_characters=None, overlap_characters=0,
                                          preamble='separate_chunk', include_child_sections=False)),
                chunks=chunks)


def chunk_file(source, target, overwrite=False):
    source, target = Path(source), Path(target)
    if source.resolve() == target.resolve():
        raise ValueError('Output tidak boleh menimpa sumber.')
    if target.exists() and not overwrite:
        raise FileExistsError('Output sudah ada; gunakan --overwrite atau lokasi lain.')
    raw = source.read_bytes()
    result = chunk_document(json.loads(raw.decode('utf-8-sig')))
    result['input_artifact'] = dict(path=str(source), sha256=hashlib.sha256(raw).hexdigest())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result
