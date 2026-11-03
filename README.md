# Document pipeline research

## Baseline indexing dan retrieval BM25

Untuk pencarian interaktif, buka `review bm25.ipynb`, pilih kernel `.venv`, lalu
klik **Run All**. Isi query dan tekan Enter atau klik **Cari BM25**. Pilih Top-k,
lihat ringkasan ranking, buka panel hasil untuk teks lengkap dan metadata sumber,
atau tab JSON untuk hasil mentah. Notebook membaca indeks yang sudah dibangun,
tidak mengubah korpus dan tidak menjalankan API eksternal.

Bangun indeks dari chunk yang sudah divalidasi:

```powershell
.\.venv\Scripts\python.exe main.py index-bm25 data/chunks/sus/chunks.json --output data/indexes/sus/bm25.json
```

Indeks awal sudah dibuat dengan catatan bahwa pengguna mengonfirmasi validasi
lanjutan. Catatan ini terikat ke hash JSON chunk, tidak mengubah status historis
`needs_review` pada artefak sumber dan bukan evaluasi kualitas retrieval.
Gunakan `--validation-note "catatan validasi"` untuk mencatat validasi pada rebuild.
Tambahkan `--overwrite` untuk mengganti indeks lama.

Cari chunk:

```powershell
.\.venv\Scripts\python.exe main.py query "120 respondents questionnaire" --index data/indexes/sus/bm25.json --top-k 3
```

Tambahkan `--json` untuk hasil lengkap, termasuk isi chunk, sumber, matched terms,
dan metadata. Tampilan terminal biasa hanya menampilkan 700 karakter pertama per
hasil. Query tanpa kecocokan tidak mengembalikan chunk dengan skor nol.

Indeks JSON menyimpan inverted postings (posisi chunk dan frekuensi token), panjang
chunk, parameter, versi tokenizer, serta path relatif dan hash korpus. Teks sumber
tetap di `chunks.json`; indeks tidak menggantikannya. Retrieval memverifikasi hash
sebelum membaca hasil sehingga perubahan chunk membutuhkan pembangunan ulang.
Jika memindahkan data, pertahankan struktur path relatif atau bangun ulang indeks.

Baseline ini memakai Python standard library saja, sepenuhnya lokal. Tidak memakai
API, embedding, model, database eksternal, stemming, stopword removal, atau
terjemahan query. Normalisasi NFKC + casefold dan tokenisasi Unicode diterapkan
identik pada korpus dan query; angka desimal seperti 71.52 dipertahankan.
Karena artikel berbahasa Inggris, gunakan query Inggris untuk baseline langsung.
Kemunculan berulang kata query dihitung sekali. Parameter awal `k1=1.5`, `b=0.75`
dapat diubah saat indexing melalui `--k1` dan `--b`. Skor menggunakan IDF positif
`log(1 + (N - df + 0.5)/(df + 0.5))`; tie-break mengikuti urutan korpus.
Parameter ini belum dituning. Skor bukan probabilitas dan tidak dibandingkan
langsung antarquery. Isi visual hanya dapat ditemukan melalui teks/caption yang
tersedia, bukan lewat pemahaman gambar.

Pengujian meliputi skor acuan hitung manual, tokenisasi, tie-break, query tanpa
kecocokan, validasi input, proteksi overwrite, metadata sumber, dan indeks usang.
Recall@k/MRR belum dihitung. Filter hak akses belum diterapkan pada baseline ini.

## Chunking berdasarkan header saja

```powershell
.\.venv\Scripts\python.exe main.py chunk data/cleaned/sus/document.json --output data/chunks/sus/chunks.json
```

Tambahkan `--overwrite` untuk menjalankan ulang pada output yang sama.
Setiap heading (termasuk subheading) memulai chunk baru hingga heading berikutnya.
Tidak ada batas karakter, pemecahan recursive, atau overlap. Isi sebelum heading
pertama menjadi chunk pembuka dengan `section_path: []`. Heading tanpa isi tetap
disimpan. Isi subheading tidak diduplikasi ke chunk induk.

Tabel, gambar, caption, dan kandidat persamaan tetap menjadi blok terstruktur di
dalam chunk section, bukan dibuang. `text` menyediakan representasi teks/tabel
untuk indexing; isi visual tidak diklaim terbaca. `blocks` menyimpan struktur
lengkap dan locator, sedangkan `asset_refs` menunjuk aset. Status review dan
metadata akses dokumen diwariskan; akses yang tidak tersedia tetap null.
Chunk ID mengikuti urutan pada input yang sama, bukan ID permanen lintas revisi.
Ukuran chunk belum dibatasi: kompatibilitas dengan panjang input model embedding
perlu dievaluasi nanti. Command ini tidak menjalankan indexing atau API eksternal.

Pipeline mencakup parsing terstruktur, cleaning, chunking header-based, dan BM25.
Utilitas cleaning Markdown memakai Python standard library dan berjalan lokal.

## Parsing terstruktur PDF SUS (alur utama terbaru)

Hasil utama setelah parsing menggunakan nama cleaned.md. Untuk memisahkan konten
gunakan perintah berikut, dari root proyek:

```powershell
.\.venv\Scripts\python.exe main.py parse-pdf "data/raw/A Statistical Analysis of System Usability Scale (SUS) _Ozzi Suria.pdf" --profile config/parsing_sus.json --parsed-dir data/parsed/sus --cleaned-dir data/cleaned/sus --assets-dir data/assets/sus
```

Tambahkan `--overwrite` untuk mengganti keluaran terstruktur yang sudah ada.
`original.md` dan hasil cleaning lama tidak diubah oleh perintah ini.

Alur: PDF → blok berdasarkan koordinat → tabel/gambar/caption/kandidat persamaan
→ simpan parsed JSON → filter header/footer dan gabungkan baris teks berdekatan
→ simpan cleaned JSON, Markdown tampilan, dan laporan review.

Keluaran utama:

- `data/parsed/sus/document.json`: blok sebelum cleaning, dengan ID dan locator PDF.
- `data/assets/sus/*.png`: crop halaman pada area objek gambar, bukan gambar asli
  hasil decoding stream. Logo/lisensi mungkin ikut terdeteksi, jadi perlu review.
- `data/cleaned/sus/document.json`: blok setelah cleaning; blok header/footer
  ditandai `excluded`, tidak dihapus dari JSON audit.
- `data/cleaned/sus/cleaned.md`: tampilan baca utama terbaru, termasuk tabel dan gambar.
- `data/cleaned/sus/cleaned.report.json`: perubahan dan temuan review.

Dependensi yang dipakai tersedia di `.venv`: pdfplumber 0.11.10, pypdfium2 5.14.0
beserta dependensinya. Tidak ada instalasi/unduhan tambahan atau panggilan API
dalam command ini. Parser ini menggunakan Python dan PDFium lokal.

Profil `parsing_sus.json` berisi area tabel, batas kolom, label kolom, dan hubungan
lanjutan yang ditentukan khusus dari dokumen uji, **bukan keluaran deteksi otomatis**.
Hash SHA-256 wajib cocok sebelum pemrosesan. Untuk dokumen lain, buat profil
terpisah atau teliti parser layout lain; jangan memakai profil SUS secara umum.

Table 2 disimpan dalam dua blok yang dihubungkan `continuation_of`. Baris elipsis
dipertahankan; responden yang tidak dicantumkan dalam artikel tidak direkonstruksi.
Baris ringkasan disimpan terpisah di `summary_rows` karena labelnya membentang
di beberapa kolom. Heading dan caption dideteksi heuristik. Hubungan caption
berstatus kandidat terdekat pada halaman yang sama, belum validasi semantik.

Semua keluaran berstatus `needs_review`. Susunan multikolom, caption beberapa
baris, persamaan, dan hubungan gambar perlu ditinjau manual. Paragraf lintas
halaman belum digabung. Tidak ada OCR/VLM, chunking, indexing, atau retrieval
yang dijalankan. Penghapusan section berbasis heading saat ini hanya tersedia
pada command `clean` lama; parser terstruktur mempertahankan seluruh section.

## Utilitas cleaning Markdown (opsional, terpisah dari alur utama)

Jalankan dari root proyek melalui PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py clean data/parsed/sus/original.md --output data/cleaned/markdown_baseline/sus/cleaned.md --config config/cleaning_sus.json
```

Keluaran:

- `data/cleaned/markdown_baseline/sus/cleaned.md`: hasil utilitas Markdown opsional.
- `data/cleaned/markdown_baseline/sus/cleaned.report.json`: aturan dan versinya, hash sumber,
  setiap perubahan beserta teks sebelum/sesudah, pemetaan baris, dan temuan review.

Sumber tidak ditimpa. Output yang sudah ada ditolak kecuali memakai `--overwrite`.
Pemetaan baris mengacu pada Markdown awal, **bukan nomor halaman PDF**.
Report juga mengandung teks sumber; perlakukan sebagai data sensitif.

Profil SUS hanya cocok untuk artikel jurnal yang sedang diuji. Profil menghapus
header/footer jurnal yang sudah diamati dan menggabungkan satu heading terpisah
yang sudah diverifikasi. Baris angka tidak dihapus secara umum. DOI, informasi
penulis, lisensi, referensi, caption, dan isi tabel tetap disimpan.

## Menghapus section yang dipilih

Daftar isi dapat dikeluarkan dari korpus retrieval karena berisi navigasi, tetapi
bukan berarti informasinya tidak valid. Nilai section ditentukan oleh kebutuhan
retrieval. Tidak ada section yang dihapus secara default.

```powershell
.\.venv\Scripts\python.exe main.py clean data/parsed/contoh.md --output data/cleaned/contoh.md --exclude-section "Daftar Isi"
```

Judul dicocokkan persis (tanpa membedakan kapital dan nomor heading), bukan
substring. Flag dapat diulang atau diisi melalui `exclude_sections` pada profil
JSON. Penghapusan membutuhkan heading Markdown eksplisit, misalnya
`## Daftar Isi`, dan berhenti pada heading eksplisit berikutnya yang levelnya
sama/lebih tinggi atau akhir file. Dokumen dengan campuran heading eksplisit dan
heading biasa perlu diperiksa batasnya sebelum fitur ini digunakan. Jika judul
hanya dikenali dari teks biasa, isi dipertahankan dengan status `needs_review`.

## Batas tahap ini

- Baris paragraf belum digabung otomatis: ekstraksi ini juga mengandung tabel
  teks biasa dan persamaan, sehingga penggabungan umum dapat merusak struktur.
- Tabel, persamaan, dan karakter font khusus ditandai untuk review, tidak direka ulang.
- Caption gambar tanpa tautan aset ditandai; script tidak mengekstraksi gambar.
- Status `cleaned_not_validated` berarti tidak ada temuan otomatis, bukan jaminan
  bahwa isi sudah benar. Review terhadap PDF tetap diperlukan.
- Nomor bagian dipertahankan, termasuk jika penomoran sumber tampak tidak konsisten.

## Pengujian

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Template dataset evaluasi Gemini

Evaluasi terstruktur seperti eksperimen chunking/retrieval tersedia di
`evaluasi_gemini.ipynb`. Buka notebook tersebut di VS Code, pilih kernel
`.venv`, jalankan cell berurutan, lalu masukkan API key Gemini ketika diminta.
Notebook membandingkan tiga metode (`recursive`, `header_recursive`, dan
`header_only`) pada pertanyaan yang sama. Hasil jawaban disimpan ke
`reports/gemini_evaluation.json` dan `reports/gemini_evaluation.csv`.

Template pertanyaan tersedia di
`data/evaluation/questions.jsonl.example`. Salin menjadi
`data/evaluation/questions.jsonl`, lalu isi satu objek JSON per baris:

- `id`: ID unik pertanyaan.
- `question`: pertanyaan yang akan diuji.
- `relevant_chunk_ids`: daftar `chunk_id` yang benar-benar relevan untuk
  menghitung Recall@k dan MRR.
- `reference_answer`: jawaban acuan berdasarkan dokumen.
- `answer`: jawaban dari aplikasi RAG yang akan dinilai. Kosongkan jika jawaban
  akan dibuat oleh Gemini dari hasil retrieval.

Ambil nilai `chunk_id` dari `data/chunks/sus/chunks.json`. Jangan menaruh API key
di file JSON atau notebook. Atur API key hanya pada environment variable sebelum
menjalankan evaluator, misalnya di PowerShell:

```powershell
$env:GEMINI_API_KEY = "isi_api_key_di_sini"
```

File dataset evaluasi dapat memuat teks jawaban dan sebaiknya tidak di-commit
jika berisi data sensitif.
