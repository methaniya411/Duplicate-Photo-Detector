# Duplicate Photo Detector

A Flask-based web application that finds and manages duplicate photos using perceptual hashing. Features a modern dark UI with drag-and-drop folder support.

## Features

- **Perceptual Hashing**: Uses pHash, dHash, aHash, and wHash algorithms to find both exact and near-duplicate images
- **Drag & Drop**: Simply drag a folder into the browser to start scanning
- **Visual Results**: Side-by-side comparison with thumbnails, file sizes, and dimensions
- **Smart Keeper Selection**: Automatically keeps the highest quality image in each duplicate group
- **Batch Actions**: Delete or move all duplicates with one click
- **Real-time Progress**: Live progress bar during scanning

## Installation

### Prerequisites

- Python 3.8+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/methaniya411/Duplicate-Photo-Detector.git
cd Duplicate-Photo-Detector

# Install dependencies
pip install flask pillow imagehash
```

## Usage

```bash
# Start the server (default: http://localhost:5000)
python app.py

# Custom port
python app.py --port 8080
```

Open http://localhost:5000 in your browser.

## How It Works

1. **Select a folder** — drag & drop, browse, or paste the path
2. **Configure settings** — adjust similarity threshold (0–64) and hash algorithm
3. **Scan** — the app finds exact duplicates (MD5) and near-duplicates (perceptual hash)
4. **Review results** — see duplicate groups with the best image marked as "Keep"
5. **Take action** — delete or move duplicates to clean up your storage

### Hash Algorithms

| Algorithm | Best For |
|-----------|----------|
| **pHash** (default) | General purpose, good balance |
| **dHash** | Resized images |
| **aHash** | Fast, less accurate |
| **wHash** | Cropped images |

### Similarity Threshold

- Lower values (0–5): Only very similar images
- Default (10): Good balance of accuracy
- Higher values (20–40): More aggressive matching

## Project Structure

```
├── app.py                      # Flask backend & scan logic
├── duplicate_photo_detector.py # Standalone CLI detector
├── templates/
│   └── index.html              # Web UI
├── doges/                      # Sample photos
└── .gitignore
```

## Supported Image Formats

JPG, JPEG, PNG, WebP, BMP, GIF

## License

MIT
