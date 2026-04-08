#!/usr/bin/env python3
"""
Duplicate Photo Detector - Web Frontend
=======================================
A Flask-based web UI for scanning directories and managing duplicate photos.
Mobile-ready PWA with offline support.

Usage:
    python app.py              # Starts server on http://0.0.0.0:5000
    python app.py --port 8080  # Custom port
"""

import argparse
import hashlib
import os
import shutil
import sys
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory
from PIL import Image
import imagehash

app = Flask(__name__, static_folder="static")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

scan_results: dict = {}


def compute_perceptual_hash(filepath: str, hash_type: str = "phash"):
    try:
        with Image.open(filepath) as img:
            img = img.convert("L")
            if hash_type == "dhash":
                return imagehash.dhash(img)
            elif hash_type == "ahash":
                return imagehash.average_hash(img)
            elif hash_type == "whash":
                return imagehash.whash(img)
            return imagehash.phash(img)
    except Exception:
        return None


def get_image_quality(filepath: str):
    try:
        size = os.path.getsize(filepath)
        with Image.open(filepath) as img:
            width, height = img.size
        return (size, width, height)
    except Exception:
        return (0, 0, 0)


def get_image_thumbnail(filepath: str, size=(200, 200)):
    try:
        with Image.open(filepath) as img:
            img.thumbnail(size)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            import io
            import base64
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            buf.seek(0)
            return base64.b64encode(buf.read()).decode()
    except Exception:
        return None


def collect_image_files(root_dir: str):
    image_files = []
    root = Path(root_dir).resolve()
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                image_files.append(os.path.join(dirpath, filename))
    return sorted(image_files)


def find_duplicates(root_dir: str, threshold: int = 10, hash_type: str = "phash", progress=None):
    image_files = collect_image_files(root_dir)
    total = len(image_files)

    if progress:
        progress["total"] = total
        progress["status"] = "scanning"

    if not image_files:
        return []

    exact_groups = defaultdict(list)
    for i, filepath in enumerate(image_files):
        try:
            file_hash = hashlib.md5(Path(filepath).read_bytes()).hexdigest()
            exact_groups[file_hash].append(filepath)
        except Exception:
            pass
        if progress:
            progress["current"] = i + 1
            progress["pct"] = round((i + 1) / total * 30)

    duplicate_groups = []
    exact_duplicate_files = set()

    for md5_hash, files in exact_groups.items():
        if len(files) > 1:
            keeper = max(files, key=get_image_quality)
            dupes = [f for f in files if f != keeper]
            duplicate_groups.append({"keeper": keeper, "duplicates": dupes, "type": "exact"})
            exact_duplicate_files.update(files)

    unique_files = [f for f in image_files if f not in exact_duplicate_files]

    if progress:
        progress["status"] = "hashing"

    perceptual_hashes = []
    for i, filepath in enumerate(unique_files):
        phash = compute_perceptual_hash(filepath, hash_type)
        if phash is not None:
            perceptual_hashes.append((filepath, phash))
        if progress:
            progress["current"] = len(exact_groups) + i + 1
            progress["pct"] = round(30 + (i + 1) / max(len(unique_files), 1) * 40)

    parent = {fp: fp for fp, _ in perceptual_hashes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    pairs_found = 0
    ph_count = len(perceptual_hashes)
    for i in range(ph_count):
        for j in range(i + 1, ph_count):
            fp_a, hash_a = perceptual_hashes[i]
            fp_b, hash_b = perceptual_hashes[j]
            if find(fp_a) == find(fp_b):
                continue
            if (hash_a - hash_b) <= threshold:
                union(fp_a, fp_b)
                pairs_found += 1
        if progress:
            progress["pct"] = round(70 + (i + 1) / max(ph_count, 1) * 20)

    groups = defaultdict(list)
    for fp, _ in perceptual_hashes:
        groups[find(fp)].append(fp)

    for group_files in groups.values():
        if len(group_files) > 1:
            keeper = max(group_files, key=get_image_quality)
            dupes = [f for f in group_files if f != keeper]
            duplicate_groups.append({"keeper": keeper, "duplicates": dupes, "type": "near-duplicate"})

    if progress:
        progress["pct"] = 100
        progress["status"] = "done"

    return duplicate_groups


def find_duplicates_from_files(image_files: list, threshold: int = 10, hash_type: str = "phash", progress=None):
    total = len(image_files)

    if progress:
        progress["total"] = total
        progress["status"] = "scanning"

    if not image_files:
        return []

    exact_groups = defaultdict(list)
    for i, filepath in enumerate(image_files):
        try:
            file_hash = hashlib.md5(Path(filepath).read_bytes()).hexdigest()
            exact_groups[file_hash].append(filepath)
        except Exception:
            pass
        if progress:
            progress["current"] = i + 1
            progress["pct"] = round((i + 1) / total * 30)

    duplicate_groups = []
    exact_duplicate_files = set()

    for md5_hash, files in exact_groups.items():
        if len(files) > 1:
            keeper = max(files, key=get_image_quality)
            dupes = [f for f in files if f != keeper]
            duplicate_groups.append({"keeper": keeper, "duplicates": dupes, "type": "exact"})
            exact_duplicate_files.update(files)

    unique_files = [f for f in image_files if f not in exact_duplicate_files]

    if progress:
        progress["status"] = "hashing"

    perceptual_hashes = []
    for i, filepath in enumerate(unique_files):
        phash = compute_perceptual_hash(filepath, hash_type)
        if phash is not None:
            perceptual_hashes.append((filepath, phash))
        if progress:
            progress["current"] = len(exact_groups) + i + 1
            progress["pct"] = round(30 + (i + 1) / max(len(unique_files), 1) * 40)

    parent = {fp: fp for fp, _ in perceptual_hashes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    ph_count = len(perceptual_hashes)
    for i in range(ph_count):
        for j in range(i + 1, ph_count):
            fp_a, hash_a = perceptual_hashes[i]
            fp_b, hash_b = perceptual_hashes[j]
            if find(fp_a) == find(fp_b):
                continue
            if (hash_a - hash_b) <= threshold:
                union(fp_a, fp_b)
        if progress:
            progress["pct"] = round(70 + (i + 1) / max(ph_count, 1) * 20)

    groups = defaultdict(list)
    for fp, _ in perceptual_hashes:
        groups[find(fp)].append(fp)

    for group_files in groups.values():
        if len(group_files) > 1:
            keeper = max(group_files, key=get_image_quality)
            dupes = [f for f in group_files if f != keeper]
            duplicate_groups.append({"keeper": keeper, "duplicates": dupes, "type": "near-duplicate"})

    if progress:
        progress["pct"] = 100
        progress["status"] = "done"

    return duplicate_groups


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(".", "manifest.json")


@app.route("/sw.js")
def service_worker():
    return send_from_directory(".", "sw.js")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    data = request.json
    directory = data.get("directory", "")
    threshold = int(data.get("threshold", 10))
    hash_type = data.get("hash_type", "phash")

    if not os.path.isdir(directory):
        return jsonify({"error": f"Invalid directory: {directory}"}), 400

    scan_id = str(uuid.uuid4())
    progress = {"total": 0, "current": 0, "pct": 0, "status": "starting"}
    scan_results[scan_id] = {"progress": progress, "groups": None, "done": False}

    def run_scan():
        groups = find_duplicates(directory, threshold, hash_type, progress)
        for group in groups:
            keeper = group["keeper"]
            kq = get_image_quality(keeper)
            group["keeper_info"] = {
                "path": keeper,
                "name": os.path.basename(keeper),
                "size": kq[0],
                "width": kq[1],
                "height": kq[2],
                "thumb": get_image_thumbnail(keeper),
            }
            group["duplicates_info"] = []
            for d in group["duplicates"]:
                dq = get_image_quality(d)
                group["duplicates_info"].append({
                    "path": d,
                    "name": os.path.basename(d),
                    "size": dq[0],
                    "width": dq[1],
                    "height": dq[2],
                    "thumb": get_image_thumbnail(d),
                })
        scan_results[scan_id]["groups"] = groups
        scan_results[scan_id]["done"] = True

    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({"scan_id": scan_id})


@app.route("/api/upload-scan", methods=["POST"])
def api_upload_scan():
    if "photos" not in request.files:
        return jsonify({"error": "No photos uploaded"}), 400

    files = request.files.getlist("photos")
    if not files or len(files) == 0:
        return jsonify({"error": "No photos uploaded"}), 400

    threshold = int(request.form.get("threshold", 10))
    hash_type = request.form.get("hash_type", "phash")

    upload_id = str(uuid.uuid4())
    upload_dir = os.path.join("uploads", upload_id)
    os.makedirs(upload_dir, exist_ok=True)

    saved_files = []
    file_counter = 0
    for f in files:
        if f.filename:
            ext = os.path.splitext(f.filename)[1].lower()
            if ext in IMAGE_EXTENSIONS or f.content_type.startswith("image/"):
                original_name = f.filename.replace('\\', '/').lstrip('/')
                name_part = os.path.splitext(original_name)[0]
                ext_part = ext or '.jpg'
                file_counter += 1
                safe_name = f"{file_counter}_{name_part}{ext_part}"
                filepath = os.path.join(upload_dir, safe_name)
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                f.save(filepath)
                saved_files.append(filepath)

    if len(saved_files) < 2:
        shutil.rmtree(upload_dir, ignore_errors=True)
        return jsonify({"error": "Need at least 2 photos to find duplicates"}), 400

    scan_id = str(uuid.uuid4())
    progress = {"total": len(saved_files), "current": 0, "pct": 0, "status": "scanning"}
    scan_results[scan_id] = {"progress": progress, "groups": None, "done": False, "upload_dir": upload_dir}

    def run_scan():
        groups = find_duplicates_from_files(saved_files, threshold, hash_type, progress)
        for group in groups:
            keeper = group["keeper"]
            kq = get_image_quality(keeper)
            group["keeper_info"] = {
                "path": keeper,
                "name": os.path.basename(keeper),
                "size": kq[0],
                "width": kq[1],
                "height": kq[2],
                "thumb": get_image_thumbnail(keeper),
            }
            group["duplicates_info"] = []
            for d in group["duplicates"]:
                dq = get_image_quality(d)
                group["duplicates_info"].append({
                    "path": d,
                    "name": os.path.basename(d),
                    "size": dq[0],
                    "width": dq[1],
                    "height": dq[2],
                    "thumb": get_image_thumbnail(d),
                })
        scan_results[scan_id]["groups"] = groups
        scan_results[scan_id]["done"] = True

    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({"scan_id": scan_id})


@app.route("/api/progress/<scan_id>")
def api_progress(scan_id):
    if scan_id not in scan_results:
        return jsonify({"error": "Scan not found"}), 404
    result = scan_results[scan_id]
    return jsonify({
        "done": result["done"],
        "progress": result["progress"],
    })


@app.route("/api/results/<scan_id>")
def api_results(scan_id):
    if scan_id not in scan_results:
        return jsonify({"error": "Scan not found"}), 404
    result = scan_results[scan_id]
    if not result["done"]:
        return jsonify({"error": "Scan still in progress"}), 400

    groups = result["groups"]
    total_dupes = sum(len(g["duplicates"]) for g in groups)
    total_space = sum(d["size"] for g in groups for d in g["duplicates_info"])

    return jsonify({
        "groups": groups,
        "total_groups": len(groups),
        "total_duplicates": total_dupes,
        "total_space": total_space,
    })


@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.json
    scan_id = data.get("scan_id", "")
    action = data.get("action", "")
    move_dir = data.get("move_dir", "./duplicates")

    print(f"API Action: scan_id={scan_id}, action={action}")

    if scan_id not in scan_results:
        print(f"Scan not found: {scan_id}")
        print(f"Available scans: {list(scan_results.keys())}")
        return jsonify({
            "error": "Scan expired. Please scan again.", 
            "scan_ids": list(scan_results.keys())
        }), 404

    groups = scan_results[scan_id].get("groups", [])
    if not groups:
        print("No groups found")
        return jsonify({"error": "No results to act on"}), 400

    results = {"deleted": [], "moved": [], "errors": []}

    for group in groups:
        for dupe_info in group["duplicates_info"]:
            filepath = dupe_info["path"]
            # Use absolute path to be 100% sure
            abs_path = os.path.abspath(filepath)
            try:
                if not os.path.exists(abs_path):
                    print(f"File not found on disk: {abs_path}")
                    results["errors"].append({"file": dupe_info["name"], "error": "File not found on server"})
                    continue
                    
                if action == "delete":
                    os.remove(abs_path)
                    print(f"Successfully deleted: {abs_path}")
                    results["deleted"].append(dupe_info["name"])
                elif action == "move":
                    os.makedirs(move_dir, exist_ok=True)
                    dest = os.path.join(os.path.abspath(move_dir), os.path.basename(filepath))
                    base, ext = os.path.splitext(dest)
                    counter = 1
                    while os.path.exists(dest):
                        dest = f"{base}_{counter}{ext}"
                        counter += 1
                    shutil.move(abs_path, dest)
                    results["moved"].append({"from": dupe_info["name"], "to": dest})
            except Exception as e:
                print(f"Critical error deleting {abs_path}: {str(e)}")
                results["errors"].append({"file": dupe_info["name"], "error": str(e)})

    print(f"Results: {results}")
    return jsonify(results)


@app.route("/api/browse", methods=["POST"])
def api_browse():
    data = request.json
    path = data.get("path", "")
    if not path or not os.path.isdir(path):
        if os.name == "nt":
            dirs = [
                os.path.expanduser("~\\Pictures"),
                os.path.expanduser("~\\Desktop"),
                os.path.expanduser("~\\Downloads"),
                "C:\\",
            ]
        else:
            dirs = [os.path.expanduser("~"), "/"]
        return jsonify({"dirs": [d for d in dirs if os.path.isdir(d)]})

    entries = []
    try:
        for entry in sorted(os.listdir(path)):
            full = os.path.join(path, entry)
            if os.path.isdir(full):
                entries.append({"name": entry, "path": full})
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403
    return jsonify({"dirs": entries, "current": path})


def main():
    parser = argparse.ArgumentParser(description="Duplicate Photo Detector - Web UI")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)), help="Port to run on")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to (default: 0.0.0.0)")
    args = parser.parse_args()

    print(f"\n  Duplicate Photo Detector - Web UI")
    print(f"  Open http://localhost:{args.port} in your browser")
    print(f"  Or from phone on same WiFi: http://<YOUR_PC_IP>:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
