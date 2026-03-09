# 🎬 Stream Getter

Download dan upload video HLS stream ke Streamtape secara otomatis.

## ✨ Features

- 🎯 Intercept HLS/m3u8 stream dari video page
- ⬇️ Download pake ffmpeg
- 📤 Auto upload ke Streamtape
- 📊 Proses batch dari CSV
- 🔄 Concurrent download & upload
- 🧹 Auto hapus file setelah upload
- 🌐 Domain Adapter System - auto-generate scraper untuk website baru

## 🚀 Cara Install

```bash
# Install dependencies
pip install -r requirements.txt

# Setup browser (Linux/Colab)
bash setup.sh
```

## 📖 Cara Pakai

### 1. Single URL

```bash
python -m stream_getter --url "https://example.com/video-page"
```

### 2. Langsung Download (Direct M3U8)

```bash
python -m stream_getter --direct "https://example.com/video.m3u8" -o video.mp4
```

### 3. Batch dari Text File

```bash
# Buat file urls.txt dengan 1 URL per baris
python -m stream_getter --batch urls.txt -d ./downloads
```

### 4. CSV Processing (Auto Upload)

```bash
# CSV wajib punya kolom 'url'
python -m stream_getter --csv hasil.csv --upload

# Dengan output directory custom
python -m stream_getter --csv hasil.csv --upload -d ./downloads

# Jika kolom URL namanya bukan 'url'
python -m stream_getter --csv hasil.csv --upload --csv-column link
```

### 5. Upload Saja

```bash
# Upload 1 file
python -m stream_getter --upload-only video.mp4

# Upload semua video di folder
python -m stream_getter --upload-only ./folder_video
```

### 6. Debug Mode

```bash
python -m stream_getter --debug "https://example.com/video"
```

### 7. Adapter Scout - Auto Generate Scraper

```bash
# Analisa website dan generate adapter otomatis
python -m stream_getter --scout "https://example.com/video-page"
```

### 8. CSV Getter - Scrape Video Listings ke CSV

```bash
# Ambil semua video dari halaman list ke CSV
python -m csv_getter "https://example.com/videos" -o videos.csv

# Dengan konkurensi
python -m csv_getter "https://example.com/videos" -o videos.csv -c 5

# Generate adapter untuk website baru
python -m csv_getter --scout "https://example.com/videos"
```

## 📊 Contoh CSV

```csv
url,title,status,streamtape
https://example.com/video1,,,
https://example.com/video2,,,
```

Setelah processing, CSV akan di-update:
```csv
url,title,status,streamtape
https://example.com/video1,Video Title 1,OK,https://streamtape.com/v/xxx
https://example.com/video2,Video Title 2,DOWNLOADED,
```

## ⚙️ Konfigurasi

Edit [`config.py`](config.py):

```python
# LOGGING
LOG_LEVEL = 'INFO'           # DEBUG | INFO | WARNING

# BROWSER
USER_AGENT = 'Mozilla/5.0 ...'
VIEWPORT = {'width': 1920, 'height': 1080}

# SCRAPING
PAGE_TIMEOUT = 60000         # milliseconds
PLAY_ATTEMPTS = 5

# DOWNLOAD
FFMPEG_TIMEOUT = 600         # seconds
DEFAULT_OUTPUT = 'video.mp4'

# UPLOAD (Streamtape)
STREAMTAPE_LOGIN = "your_login"
STREAMTAPE_KEY = "your_key"
STREAMTAPE_FOLDER = "folder_id"

# CONCURRENT
MAX_CONCURRENT_DOWNLOADS = 10
MAX_CONCURRENT_UPLOADS = 2

# FILES
DELETE_AFTER_UPLOAD = True   # Hapus file setelah upload
```

## 📁 Struktur Project

```
.
├── main.py                  # Entry point
├── config.py                # Konfigurasi
├── stream_getter/
│   ├── __init__.py
│   ├── cli/                 # Command line interface
│   │   ├── main.py
│   │   ├── parser.py
│   │   └── scout.py         # Adapter Scout
│   ├── core/                # Core scraping
│   │   ├── browser.py
│   │   ├── interceptor.py
│   │   └── scraper.py
│   ├── adapters/            # Domain adapters
│   │   ├── __init__.py      # BaseAdapter & AdapterRegistry
│   │   └── domains/         # Domain-specific adapters
│   │       ├── indovidz.py
│   │       └── ...
│   ├── pipeline/            # Processing pipelines
│   │   ├── batch.py
│   │   ├── csv.py
│   │   ├── csv_helper.py
│   │   ├── downloader.py
│   │   └── uploader.py
│   └── utils/               # Utilities
│       ├── exceptions.py
│       ├── helpers.py
│       └── validators.py
├── csv_getter/              # Video listing to CSV
│   ├── __init__.py
│   ├── __main__.py
│   ├── scraper.py           # Main CSV scraper
│   ├── scout.py             # Adapter generator
│   └── adapters/            # Domain adapters for CSV
│       ├── __init__.py
│       └── domains/
└── requirements.txt
```

## 🔧 CLI Options

### stream_getter

| Option | Description |
|--------|-------------|
| `--url` | Single video URL |
| `--direct` | Direct M3U8 URL |
| `--batch` | Text file dengan list URL |
| `--csv` | CSV file untuk batch processing |
| `--upload-only` | Upload file/folder saja |
| `--scout` | Adapter Scout - auto generate scraper |
| `--debug` | Debug mode |
| `-o, --output` | Output filename |
| `-d, --output-dir` | Output directory |
| `-r, --referer` | Custom HTTP referer |
| `-u, --upload` | Upload setelah download |
| `--csv-column` | Nama kolom URL di CSV |

### csv_getter

| Option | Description |
|--------|-------------|
| `--scout` | Generate adapter untuk website |
| `-o, --output` | Output CSV filename |
| `-c, --concurrency` | Jumlah concurrent requests |
| `--page-selector` | CSS selector untuk video item |
| `--url-selector` | CSS selector untuk link video |
| `--title-selector` | CSS selector untuk title |
| `--next-selector` | CSS selector untuk next page button |

## 🌐 Domain Adapter System

### Cara Kerja

Adapter adalah class yang menangani cara scraping website tertentu. Setiap adapter mendefinisikan:
- Selector untuk elemen video
- Cara mengambil title
- Cara mengambil URL video

### Adapter yang Tersedia

- `indovidz.py` - IndoVids/NewVIDS
- `bokepindo.py` - BokepIndo
- `sebokep_com.py` - Sebokep.com

### Buat Adapter Baru

```bash
# Auto-generate dengan Scout
python -m stream_getter --scout "https://site baru.com/video"
```

Atau buat manual:

```python
from stream_getter.adapters import BaseAdapter

class MySiteAdapter(BaseAdapter):
    DOMAIN = "mysite.com"
    
    def get_video_url(self, page):
        # Return m3u8 URL
        return page.evaluate("""() => {
            return document.querySelector('video source').src;
        }""")
    
    def get_title(self, page):
        return page.title()
```

## 📝 Log Output

```
[18:40:28] [INFO] CSV: 100 videos, dl×10, up×2
⚡ [DL:1/10] [UP:0/2] 📥 Video title 1...
✅ Video title 1 → https://streamtape.com/v/xxx
⚡ [DL:2/10] [UP:1/2] 📥 Video title 2...
```

## ⚠️ Notes

- Wajib punya akun Streamtape dan isi API credentials di `config.py`
- CSV akan di-update in-place
- File video bisa dihapus otomatis setelah upload sukses
- Gunakan `--referer` jika site butuh validasi referer
- Gunakan `--scout` untuk membuat adapter otomatis untuk website baru

## 📜 License

MIT
