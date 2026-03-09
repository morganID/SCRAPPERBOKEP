#!/usr/bin/env python3
"""
CSV Helper - Baca, tulis, dan detect kolom CSV
"""

import csv
import os


def detect_url_column(fieldnames, preferred='url'):
    """Auto-detect kolom URL di CSV"""
    if preferred in fieldnames:
        return preferred

    candidates = ['url', 'URL', 'Url', 'link', 'Link', 'LINK',
                  'video_url', 'video_link', 'source', 'Source', 'href']
    for c in candidates:
        if c in fieldnames:
            return c

    return None


def read_csv(csv_file):
    """
    Baca CSV, return (fieldnames, rows)
    
    - Auto-detect delimiter (, ; tab |)
    - Support UTF-8 BOM
    """
    rows = []
    fieldnames = []

    with open(csv_file, 'r', newline='', encoding='utf-8-sig') as f:
        # Detect delimiter
        sample = f.read(4096)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel  # default comma

        reader = csv.DictReader(f, dialect=dialect)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            rows.append(dict(row))

    return fieldnames, rows


def save_csv(csv_file, fieldnames, rows):
    """Simpan CSV (overwrite)"""
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def ensure_columns(fieldnames, required=None):
    """
    Pastikan kolom-kolom tertentu ada di fieldnames.
    Return list kolom baru yang ditambahkan.
    """
    if required is None:
        required = ['title', 'status', 'streamtape']

    added = []
    for col in required:
        if col not in fieldnames:
            fieldnames.append(col)
            added.append(col)
    return added


def get_pending_rows(rows, url_column='url', done_column='streamtape'):
    """
    Return list index baris yang perlu diproses.
    Skip baris yang URL-nya kosong atau sudah punya link streamtape.
    """
    pending = []
    for i, row in enumerate(rows):
        url = row.get(url_column, '').strip()
        has_done = row.get(done_column, '').strip()
        if url and not has_done:
            pending.append(i)
    return pending


def print_summary(rows, skipped=0):
    """Print ringkasan status CSV"""
    count_ok = sum(1 for r in rows if r.get('status') == 'OK')
    count_dl = sum(1 for r in rows if r.get('status') == 'DOWNLOADED')
    count_fail = sum(1 for r in rows if r.get('status', '').startswith(
        ('ERROR', 'NO_M3U8', 'DOWNLOAD_FAILED', 'UPLOAD_FAILED')))

    print(f"  ✅ OK (uploaded)  : {count_ok}")
    print(f"  📥 Downloaded     : {count_dl}")
    print(f"  ⏭️  Skipped        : {skipped}")
    print(f"  ❌ Failed         : {count_fail}")
    print(f"  📄 Total baris    : {len(rows)}")

    # Tampilkan link streamtape
    st_links = [(r.get('title', '?'), r.get('streamtape', ''))
                for r in rows if r.get('streamtape', '').strip()]
    if st_links:
        print(f"\n📺 Streamtape Links:")
        for title, link in st_links:
            print(f"   {title[:40]:40s}  →  {link}")