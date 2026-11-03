import hashlib
import json
import re
from collections import Counter
from pathlib import Path

VERSION = "0.1.0"
NAMED = {"abstract": 2, "abstrak": 2, "references": 2, "referensi": 2,
         "daftar pustaka": 2, "daftar isi": 2, "table of contents": 2, "contents": 2}


def heading(text):
    """Kenali heading eksplisit, judul bernomor bertitik, atau label yang dikenal."""
    match = re.fullmatch(r"(#{1,6})\s+(.+?)(?:\s+#+)?", text)
    if match:
        return len(match[1]), match[2]
    match = re.fullmatch(r"([1-9]\d*(?:\.\d+)*)(\.)?\s+([A-Z][^\n]{0,79})", text)
    if match and len(match[3].split()) <= 10 and not match[3].endswith((".", ",", ";")) and (match[2] or "." in match[1]):
        return min(6, match[1].count(".") + 2), text
    if text.casefold() in NAMED:
        return NAMED[text.casefold()], text
    return None


def title_key(text):
    return re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text).strip().casefold()


def clean_text(text, config=None):
    config = config or {}
    original = text.splitlines()
    changes, review = [], []
    rows = []
    patterns = [(p, re.compile(p)) for p in config.get("remove_line_patterns", [])]
    excluded = {title_key(s) for s in config.get("exclude_sections", [])}

    def change(rule, source_lines, before, after=""):
        changes.append(dict(rule=rule, source_lines=source_lines, before=before, after=after))

    fence = None
    for number, before in enumerate(original, 1):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", before)
        protected = fence is not None or marker is not None or before.startswith(("    ", "\t"))
        if marker:
            token = marker[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not before[marker.end():].strip():
                fence = None
        if protected:
            rows.append(dict(text=before, source_lines=[number], protected=True))
            continue
        after = before.rstrip()
        # Dua spasi terakhir adalah hard break Markdown yang sah.
        if before.endswith("  ") and after:
            after += "  "
        # Pertahankan indentasi: dapat bermakna kode, daftar, atau persamaan.
        matched = next((p for p, compiled in patterns if compiled.fullmatch(after.strip())), None)
        if matched:
            change("remove_profile_line", [number], before)
            continue
        if after != before:
            change("trim_trailing_whitespace", [number], before, after)
        rows.append(dict(text=after, source_lines=[number]))

    # Gabungkan hanya nomor heading terpisah yang disetujui dalam profil.
    approved = config.get("split_headings", {})
    joined = []
    i = 0
    while i < len(rows):
        row = rows[i]
        j = i + 1
        while j < len(rows) and not rows[j]["text"].strip():
            j += 1
        expected = approved.get(row["text"].strip())
        if expected and not row.get("protected") and j < len(rows) and not rows[j].get("protected") and rows[j]["text"].strip() == expected:
            ids = [n for item in rows[i:j+1] for n in item["source_lines"]]
            value = row["text"].strip() + " " + expected
            change("join_approved_heading", ids, "\n".join(r["text"] for r in rows[i:j+1]), value)
            joined.append(dict(text=value, source_lines=ids))
            i = j + 1
        else:
            joined.append(row)
            i += 1
    rows = joined

    # Heading hasil inferensi dari teks biasa tidak aman sebagai batas penghapusan.
    # Section harus memiliki batas heading Markdown eksplisit (atau akhir file).
    remove = set()
    for i, row in enumerate(rows):
        h = None if row.get("protected") else heading(row["text"])
        if not h or title_key(h[1]) not in excluded or i in remove:
            continue
        explicit = re.match(r"^#{1,6}\s", row["text"])
        end = None
        if explicit:
            end = len(rows)
            for j in range(i+1, len(rows)):
                following = None if rows[j].get("protected") else re.match(r"^(#{1,6})\s", rows[j]["text"])
                if following and len(following[1]) <= h[0]:
                    end = j
                    break
        if end is None:
            review.append(dict(kind="section_boundary_uncertain", source_lines=row["source_lines"],
                               detail="Section diminta dihapus tetapi batasnya belum eksplisit; isi dipertahankan."))
        else:
            ids = [n for r in rows[i:end] for n in r["source_lines"]]
            change("exclude_section", ids, "\n".join(r["text"] for r in rows[i:end]))
            remove.update(range(i, end))

    output = []
    for i, row in enumerate(rows):
        if i in remove:
            continue
        value = row["text"]
        h = None if row.get("protected") else heading(value)
        if h and not value.startswith("#") and not value.startswith((" ", "\t")):
            updated = "#" * h[0] + " " + h[1]
            change("format_heading", row["source_lines"], value, updated)
            row = dict(text=updated, source_lines=row["source_lines"])
        if not row.get("protected") and not row["text"] and (not output or not output[-1]["text"]):
            change("collapse_blank_line", row["source_lines"], row["text"])
            continue
        output.append(row)

    for row in output:
        value, ids = row["text"], row["source_lines"]
        if any(0xE000 <= ord(c) <= 0xF8FF or c == "\ufffd" for c in value):
            review.append(dict(kind="unresolved_character", source_lines=ids, detail=value))
        if re.match(r"^(Table|Tabel)\s+\d+\.", value):
            review.append(dict(kind="table_requires_source_check", source_lines=ids, detail=value))
        if any(c in value for c in ("∑", "⬚")):
            review.append(dict(kind="equation_requires_source_check", source_lines=ids, detail=value))
    if re.search(r"^Figure\s+\d+\.", text, re.M) and not re.search(r"!\[.*?\]\(", text):
        review.append(dict(kind="figure_assets_unverified", source_lines=[],
                           detail="Caption ditemukan tanpa tautan gambar Markdown; ekstraksi aset perlu diverifikasi."))
    cleaned = "\n".join(row["text"] for row in output) + ("\n" if output else "")
    report = dict(schema_version="1.0", cleaner_version=VERSION,
                  status="needs_review" if review else "cleaned_not_validated",
                  config=config, changes=changes, review_items=review,
                  summary=dict(input_lines=len(original), output_lines=len(output),
                               changes_by_rule=dict(Counter(c["rule"] for c in changes))),
                  source_mapping=dict(type="parsed_markdown_lines_not_pdf_pages", lines=[
                      dict(output_line=i, source_lines=row["source_lines"]) for i, row in enumerate(output, 1)]))
    return cleaned, report


def clean_file(source, target, config=None, overwrite=False):
    source, target = Path(source), Path(target)
    audit = target.with_name(target.stem + ".report.json")
    if source.resolve() in (target.resolve(), audit.resolve()):
        raise ValueError("Output tidak boleh menimpa sumber.")
    if not overwrite and (target.exists() or audit.exists()):
        raise FileExistsError("Hasil sudah ada. Gunakan output lain atau --overwrite.")
    raw = source.read_bytes()
    cleaned, report = clean_text(raw.decode("utf-8-sig"), config)
    report.update(source=str(source), output=str(target), source_sha256=hashlib.sha256(raw).hexdigest())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(cleaned, encoding="utf-8")
    audit.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
