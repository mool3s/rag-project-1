import argparse
import json
from pathlib import Path

from src.document_pipeline.cleaning import clean_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index-bm25", help="Bangun indeks BM25 lokal dari JSON chunk")
    index.add_argument("input", type=Path)
    index.add_argument("--output", type=Path, required=True)
    index.add_argument("--k1", type=float, default=1.5)
    index.add_argument("--b", type=float, default=0.75)
    index.add_argument("--validation-note")
    index.add_argument("--overwrite", action="store_true")
    query = commands.add_parser("query", help="Cari chunk menggunakan indeks BM25")
    query.add_argument("query")
    query.add_argument("--index", type=Path, required=True)
    query.add_argument("--top-k", type=int, default=5)
    query.add_argument("--json", action="store_true", help="Tampilkan hasil JSON lengkap")
    chunk = commands.add_parser("chunk", help="Chunking berdasarkan setiap heading, tanpa batas ukuran")
    chunk.add_argument("input", type=Path)
    chunk.add_argument("--output", type=Path, required=True)
    chunk.add_argument("--overwrite", action="store_true")
    structured = commands.add_parser("parse-pdf", help="Parsing terstruktur PDF memakai profil area")
    structured.add_argument("input", type=Path)
    structured.add_argument("--profile", type=Path, required=True)
    structured.add_argument("--parsed-dir", type=Path, required=True)
    structured.add_argument("--cleaned-dir", type=Path, required=True)
    structured.add_argument("--assets-dir", type=Path, required=True)
    structured.add_argument("--overwrite", action="store_true")
    clean = commands.add_parser("clean", help="Cleaning Markdown tanpa mengubah sumber")
    clean.add_argument("input", type=Path)
    clean.add_argument("--output", type=Path, required=True)
    clean.add_argument("--config", type=Path, help="Profil aturan JSON; tanpa profil hanya aturan umum")
    clean.add_argument("--exclude-section", action="append", default=[], help="Judul section persis; dapat diulang")
    clean.add_argument("--overwrite", action="store_true", help="Izinkan penggantian hasil sebelumnya")
    args = parser.parse_args()
    if args.command == "index-bm25":
        from src.document_pipeline.indexing.bm25 import index_file
        result = index_file(args.input, args.output, args.k1, args.b, args.overwrite, args.validation_note)
        print(f"Indeks: {args.output}; chunk: {result['document_count']}; kosakata: {len(result['postings'])}")
        return
    if args.command == "query":
        from src.document_pipeline.retrieval import search
        result = search(args.index, args.query, args.top_k)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif not result['results']:
            print("Tidak ada token query yang cocok dengan korpus.")
        else:
            for hit in result['results']:
                section = ' > '.join(hit['section_path']) or 'Pembuka'
                print(f"\n{hit['rank']}. {hit['chunk_id']} | skor {hit['score']:.4f}")
                print(f"Section: {section} | halaman PDF: {hit['pages']}")
                print(f"Sumber: {hit['source'].get('name', '')} | status artefak: {hit['status']}")
                print(hit['text'][:700] + (' ...' if len(hit['text']) > 700 else ''))
        return
    if args.command == "chunk":
        from src.document_pipeline.chunking import chunk_file
        result = chunk_file(args.input, args.output, args.overwrite)
        print(f"Hasil: {args.output}; jumlah chunk: {len(result['chunks'])}; metode: header_based")
        return
    if args.command == "parse-pdf":
        from src.document_pipeline.parsing.pdf_structured import parse_pdf
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        document, report = parse_pdf(args.input, args.parsed_dir, args.cleaned_dir, args.assets_dir, profile, args.overwrite)
        print(f"Status: {document['status']}; blok: {len(document['blocks'])}; review: {len(report['review_items'])}")
        print(f"Hasil: {args.cleaned_dir / 'cleaned.md'}")
        return
    config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
    config["exclude_sections"] = config.get("exclude_sections", []) + args.exclude_section
    result = clean_file(args.input, args.output, config, overwrite=args.overwrite)
    print(f"Hasil: {args.output}")
    print(f"Status: {result['status']}; perubahan: {len(result['changes'])}; review: {len(result['review_items'])}")


if __name__ == "__main__":
    main()
