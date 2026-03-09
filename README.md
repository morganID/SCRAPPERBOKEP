# 🎬 Stream Getter

Download dan upload video HLS stream ke Streamtape secara otomatis.

## ✨ Features

- 🎯 Intercept HLS/m3u8 stream dari video page
- ⬇️ Download pake ffmpeg
- 📤 Auto upload ke Streamtape
- 📊 Proses batch dari CSV
- 🔄 Concurrent download & upload
- 🧹 Auto hapus file setelah upload

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
│   │   └── parser.py
│   ├── core/                # Core scraping
│   │   ├── browser.py
│   │   ├── interceptor.py
│   │   └── stream_getter.py
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
└── requirements.txt
```

## 🔧 CLI Options

| Option | Description |
|--------|-------------|
| `--url` | Single video URL |
| `--direct` | Direct M3U8 URL |
| `--batch` | Text file dengan list URL |
| `--csv` | CSV file untuk batch processing |
| `--upload-only` | Upload file/folder saja |
| `--debug` | Debug mode |
| `-o, --output` | Output filename |
| `-d, --output-dir` | Output directory |
| `-r, --referer` | Custom HTTP referer |
| `-u, --upload` | Upload setelah download |
| `--csv-column` | Nama kolom URL di CSV |

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

## 📜 License

MIT
