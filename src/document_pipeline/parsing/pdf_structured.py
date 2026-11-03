"""Ekstraksi PDF lokal berbasis koordinat; hasil heuristik selalu perlu review."""
import copy
import hashlib
from html import escape
from importlib.metadata import version
import json
import os
from pathlib import Path
import re

import pdfplumber

from ..cleaning import heading


def bbox(item):
    return [round(float(item[k]), 3) for k in ('x0', 'top', 'x1', 'bottom')]


def inside(item, box):
    x = (item['x0'] + item['x1']) / 2
    y = (item['top'] + item['bottom']) / 2
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def extract_rows(page, spec):
    """Kolom eksplisit berasal dari profil; baris lanjutan tanpa ID digabung."""
    words = [w for w in page.extract_words() if inside(w, spec['bbox']) and w['top'] >= spec.get('data_top', spec['bbox'][1])]
    groups = []
    for word in sorted(words, key=lambda w: (w['top'], w['x0'])):
        if not groups or abs(word['top'] - groups[-1][0]['top']) > 3:
            groups.append([])
        groups[-1].append(word)
    rows = []
    for group in groups:
        cells = [''] * len(spec['columns'])
        for word in sorted(group, key=lambda w: w['x0']):
            center = (word['x0'] + word['x1']) / 2
            col = sum(center > edge for edge in spec['column_edges'])
            cells[col] = (cells[col] + ' ' + word['text']).strip()
        if not cells[0] and rows and spec.get('merge_continuations', False):
            rows[-1] = [(a + ' ' + b).strip() for a, b in zip(rows[-1], cells)]
        else:
            rows.append(cells)
    return rows


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def table_html(block):
    cells = lambda values, tag: ''.join(f'<{tag}>{escape(str(v))}</{tag}>' for v in values)
    lines = ['<table>', '<thead><tr>' + cells(block['columns'], 'th') + '</tr></thead>', '<tbody>']
    lines += ['<tr>' + cells(row, 'td') + '</tr>' for row in block['rows']]
    return '\n'.join(lines + ['</tbody>', '</table>'])


def table_preview(document):
    parts = ['<!doctype html><html lang="id"><meta charset="utf-8">',
             '<title>Review tabel dokumen</title>',
             '<style>body{font-family:Arial,sans-serif;margin:32px;color:#222}table{border-collapse:collapse;margin:16px 0 32px}th,td{border:1px solid #aaa;padding:8px;text-align:left}th{background:#eee}</style>',
             '<h1>Review tabel dokumen</h1><p>Status: needs_review. Nomor halaman mengacu pada PDF.</p>']
    for block in document['blocks']:
        if block['type'] != 'table' or block.get('excluded'):
            continue
        parts += [f"<h2>{escape(block['label'])} — PDF page {block['source']['page']}</h2>", table_html(block)]
        for summary in block.get('summary_rows', []):
            parts.append('<p>' + escape(' '.join(c for c in summary if c)) + '</p>')
    return '\n'.join(parts + ['</html>'])


def markdown(document, output):
    parts = ['# ' + document['source']['name'], '',
             '> Hasil ekstraksi lokal — needs_review. Nomor halaman adalah urutan halaman PDF.', '']
    for block in document['blocks']:
        if block.get('excluded'):
            continue
        loc = block['source']
        parts += [f"<!-- {block['id']} | PDF page {loc['page']} | {block['type']} -->"]
        kind = block['type']
        if kind == 'heading':
            parts.append('#' * block['level'] + ' ' + block['text'])
        elif kind == 'table':
            parts.append('**' + block.get('label', 'Table') + '**')
            if block.get('caption_id'):
                parts.append('*Caption: ' + block['caption_text'] + '*')
            parts.append('')
            def markdown_cell(value):
                return str(value).replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')

            parts.append('| ' + ' | '.join(markdown_cell(c) for c in block['columns']) + ' |')
            parts.append('| ' + ' | '.join('---' for _ in block['columns']) + ' |')
            for row in block['rows']:
                parts.append('| ' + ' | '.join(markdown_cell(c) for c in row) + ' |')
            parts.append('')
            for summary in block.get('summary_rows', []):
                parts.append('Ringkasan tabel (posisi sel asli tersimpan di JSON): ' + ' '.join(c for c in summary if c))
            if block.get('continuation_of'):
                parts.append('Lanjutan blok: `' + block['continuation_of'] + '` (sesuai profil, perlu review).')
        elif kind == 'image':
            relative = Path(os.path.relpath(block['asset_path'], output.parent)).as_posix()
            parts.append(f"![{block['id']}]({relative})")
            if block.get('caption_id'):
                parts.append('*Kandidat caption: ' + block['caption_text'] + '*')
        elif kind == 'equation_candidate':
            parts += ['```text', block['text'], '```', '*Persamaan: belum diverifikasi terhadap sumber.*']
        elif kind == 'caption':
            parts.append('*' + block['text'] + '*')
        else:
            parts.append(block['text'])
        parts.append('')
    return '\n'.join(parts)


def parse_pdf(source, parsed_dir, cleaned_dir, assets_dir, profile, overwrite=False):
    source, parsed_dir, cleaned_dir, assets_dir = map(Path, (source, parsed_dir, cleaned_dir, assets_dir))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != profile.get('source_sha256'):
        raise ValueError('Profil tidak cocok dengan hash PDF; buat profil dokumen yang sesuai.')
    outputs = [parsed_dir/'document.json', cleaned_dir/'document.json',
               cleaned_dir/'cleaned.md', cleaned_dir/'cleaned.report.json', cleaned_dir/'tables.html']
    if source.resolve() in [p.resolve() for p in outputs]:
        raise ValueError('Output tidak boleh menimpa sumber.')
    if not overwrite and (any(p.exists() for p in outputs) or (assets_dir.exists() and any(assets_dir.iterdir()))):
        raise FileExistsError('Output/aset sudah ada; gunakan lokasi lain atau --overwrite.')
    for directory in (parsed_dir, cleaned_dir, assets_dir):
        directory.mkdir(parents=True, exist_ok=True)
    blocks, reviews = [], []
    with pdfplumber.open(source) as pdf:
        for page_number, page in enumerate(pdf.pages, 1):
            specs = [s for s in profile.get('tables', []) if s['page'] == page_number]
            page_blocks = []

            def add(kind, box, **fields):
                block = dict(type=kind, source=dict(page=page_number, bbox=box,
                             coordinate_system='pdf_points_top_left'), **fields)
                page_blocks.append(block)
                return block

            for spec in specs:
                rows = extract_rows(page, spec)
                summaries = [r for r in rows if any('AVERAGE' in cell for cell in r)]
                rows = [r for r in rows if r not in summaries]
                add('table', spec['bbox'], text='', label=spec['label'],
                    table_key=spec['table_key'], columns=spec['columns'], rows=rows,
                    summary_rows=summaries,
                    continuation_key=spec.get('continuation_key'),
                    extraction_method='profile_word_coordinates', status='needs_review')

            for index, image in enumerate(page.images, 1):
                box = [max(0, image['x0']), max(0, image['top']),
                       min(page.width, image['x1']), min(page.height, image['bottom'])]
                if box[2] <= box[0] or box[3] <= box[1]:
                    reviews.append(dict(kind='invalid_image_bbox', page=page_number))
                    continue
                asset = assets_dir / f'page_{page_number:03d}_image_{index:02d}.png'
                # Crop mempertahankan tampilan komposit, bukan byte gambar tertanam.
                page.crop(box).to_image(resolution=130).save(asset)
                add('image', [round(v, 3) for v in box], text='', asset_path=str(asset),
                    asset_kind='rendered_page_crop', caption_id=None, status='needs_review')

            if not page.chars:
                reviews.append(dict(kind='no_digital_text', page=page_number, detail='OCR belum diterapkan.'))
            for line in page.extract_text_lines():
                # Hanya kata dalam area tabel yang dikeluarkan dari alur teks.
                if any(inside(line, spec['bbox']) for spec in specs):
                    continue
                value = line['text']
                h = heading(value)
                caption = re.fullmatch(r'(Figure|Table|Gambar|Tabel)\s+(\d+)\.\s+(.+)', value)
                if caption:
                    add('caption', bbox(line), text=value, label=f'{caption[1]} {caption[2]}',
                        status='needs_review')
                elif h:
                    add('heading', bbox(line), text=h[1], level=h[0])
                elif len(value) < 100 and (any(c in value for c in ('∑', '⬚')) or
                     re.match(r'^(Qo\s*=|Qe\s*=|SUS\s*=|S\s*=|i=|Si$|n$|\(\d+\)$)', value)):
                    add('equation_candidate', bbox(line), text=value, status='needs_review')
                else:
                    add('text', bbox(line), text=value)
            page_blocks.sort(key=lambda b: (b['source']['bbox'][1], b['source']['bbox'][0]))
            blocks.extend(page_blocks)
        page_count = len(pdf.pages)
    for i, block in enumerate(blocks, 1):
        block['id'] = f'{digest[:12]}_b{i:04d}'

    # Caption hanya kandidat; jangan menyatakan relasi ini telah tervalidasi.
    for block in blocks:
        if block['type'] not in ('table', 'image'):
            continue
        page = block['source']['page']
        box = block['source']['bbox']
        candidates = []
        for caption in blocks:
            if caption['type'] != 'caption' or caption['source']['page'] != page:
                continue
            if block['type'] == 'table' and caption['label'] != block['label']:
                continue
            if block['type'] == 'image' and not caption['label'].startswith(('Figure', 'Gambar')):
                continue
            cb = caption['source']['bbox']
            distance = min(abs(cb[1]-box[3]), abs(box[1]-cb[3]))
            if distance <= 65:
                candidates.append((distance, caption))
        if candidates:
            candidates.sort(key=lambda c: c[0])
            block.update(caption_id=candidates[0][1]['id'], caption_text=candidates[0][1]['text'],
                         caption_relation='candidate_nearby_same_page')
        if block['type'] == 'table' and block.get('continuation_key'):
            previous = [b for b in blocks if b['type'] == 'table' and b['table_key'] == block['continuation_key']
                        and b['source']['page'] < page]
            block['continuation_of'] = previous[-1]['id'] if previous else None
    document = dict(schema_version='1.0', status='needs_review', document_id=digest[:12],
                    source=dict(path=str(source), name=source.name, sha256=digest, page_count=page_count),
                    parser=dict(name='pdfplumber_profile', version=version('pdfplumber'),
                                pipeline_version='0.1.0', network_used=False), profile=profile, blocks=blocks)
    write_json(parsed_dir/'document.json', document)

    cleaned = copy.deepcopy(document)
    patterns = [re.compile(p) for p in profile.get('remove_line_patterns', [])]
    changes = []
    section = []
    merged = []
    for block in cleaned['blocks']:
        is_footer_number = any(block['source']['page'] == rule['page'] and
                               block['source']['bbox'][1] >= rule['min_top'] and block['text'] == rule['text']
                               for rule in profile.get('remove_positioned_lines', []))
        if block['type'] in ('text', 'heading') and (any(p.fullmatch(block['text'].strip()) for p in patterns) or is_footer_number):
            block['excluded'] = True
            changes.append(dict(rule='profile_header_footer', block_id=block['id'], before=block['text']))
        if block['type'] == 'heading' and not block.get('excluded'):
            section = [s for s in section if s[0] < block['level']] + [(block['level'], block['text'])]
        block['section_path'] = [s[1] for s in section]
        block['source_block_ids'] = [block['id']]
        if merged and block['type'] == 'text' and not block.get('excluded'):
            previous = merged[-1]
            a, b = previous['source'], block['source']
            gap = b['bbox'][1] - a['bbox'][3]
            if previous['type'] == 'text' and not previous.get('excluded') and a['page'] == b['page'] and 0 <= gap < 4:
                previous['text'] += ' ' + block['text']
                previous['source_block_ids'].append(block['id'])
                a['bbox'] = [min(a['bbox'][0], b['bbox'][0]), a['bbox'][1],
                             max(a['bbox'][2], b['bbox'][2]), b['bbox'][3]]
                changes.append(dict(rule='join_close_text_lines', block_id=block['id'], target=previous['id']))
                continue
        merged.append(block)
    cleaned['blocks'] = merged
    for block in merged:
        if block.get('excluded'):
            continue
        if block['type'] in ('table', 'image', 'equation_candidate', 'caption'):
            reviews.append(dict(kind=block['type']+'_requires_review', block_id=block['id'], source=block['source']))
        if any(0xE000 <= ord(c) <= 0xF8FF or c == '\ufffd' for c in block['text']):
            reviews.append(dict(kind='unresolved_character', block_id=block['id']))
    write_json(cleaned_dir/'document.json', cleaned)
    md = cleaned_dir/'cleaned.md'
    md.write_text(markdown(cleaned, md), encoding='utf-8')
    (cleaned_dir/'tables.html').write_text(table_preview(cleaned), encoding='utf-8')
    report = dict(status='needs_review', changes=changes, review_items=reviews,
                  notes=['Reading order is top-to-bottom heuristic; not validated for multiple columns.',
                         'Page fragments remain separate; missing table rows are not reconstructed.',
                         'Table column names and continuation come from document-specific profile.',
                         'Image crops can include overlays; caption associations are candidates.'])
    write_json(cleaned_dir/'cleaned.report.json', report)
    return cleaned, report
