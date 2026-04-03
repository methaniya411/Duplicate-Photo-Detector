#!/usr/bin/env python3
"""
Duplicate Photo Detector & Auto-Delete Tool
=============================================

Detects duplicate and near-duplicate images using perceptual hashing (pHash).
Keeps the highest-quality version from each duplicate group and removes the rest.

Usage:
    # Dry-run mode (default) - shows what would be deleted without touching files
    python duplicate_photo_detector.py /path/to/photos

    # Actually delete duplicates (use with caution!)
    python duplicate_photo_detector.py /path/to/photos --delete

    # Move duplicates to a separate folder instead of deleting
    python duplicate_photo_detector.py /path/to/photos --move --move-dir /path/to/duplicates

    # Custom similarity threshold (lower = stricter, higher = more lenient)
    python duplicate_photo_detector.py /path/to/photos --threshold 5

    # Combine options
    python duplicate_photo_detector.py /path/to/photos --delete --threshold 15

Options:
    --threshold N    Max hash distance to consider images as duplicates (default: 10)
    --delete         Actually delete duplicate files (default is dry-run)
    --move           Move duplicates to a folder instead of deleting
    --move-dir PATH  Destination folder for moved duplicates (default: ./duplicates)
    --hash-type TYPE Hash algorithm: phash, dhash, ahash, whash (default: phash)
"""

import argparse
import hashlib
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

from PIL import Image
import imagehash

# Supported image extensions
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def compute_perceptual_hash(filepath: str, hash_type: str = "phash") -> Optional[imagehash.ImageHash]:
    """
    Compute a perceptual hash for an image file.

    Returns None if the file cannot be opened or is not a valid image.
    Supports multiple hash algorithms for different sensitivity levels:
      - phash:  perceptual hash (good general-purpose choice)
      - dhash:  difference hash (fast, catches structural similarity)
      - ahash:  average hash (fastest, less accurate)
      - whash:  wavelet hash (good for photos with minor edits)
    """
    try:
        with Image.open(filepath) as img:
            # Convert to grayscale for consistent hashing
            img = img.convert("L")

            if hash_type == "dhash":
                return imagehash.dhash(img)
            elif hash_type == "ahash":
                return imagehash.average_hash(img)
            elif hash_type == "whash":
                return imagehash.whash(img)
            else:
                # Default: phash
                return imagehash.phash(img)
    except Exception as e:
        # Gracefully handle corrupted files, permission errors, etc.
        print(f"  [WARN] Could not hash {filepath}: {e}")
        return None


def get_image_quality(filepath: str) -> tuple[int, int, int]:
    """
    Get a quality score tuple for an image used to decide which copy to keep.

    Returns (file_size_bytes, width, height) so we can sort and pick the
    "best" version — preferring larger file size, then higher resolution.
    """
    try:
        size = os.path.getsize(filepath)
        with Image.open(filepath) as img:
            width, height = img.size
        return (size, width, height)
    except Exception:
        return (0, 0, 0)


def collect_image_files(root_dir: str) -> list[str]:
    """
    Walk the directory tree and collect all image file paths.
    """
    image_files = []
    root = Path(root_dir).resolve()

    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            ext = Path(filename).suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                image_files.append(os.path.join(dirpath, filename))

    return sorted(image_files)


def group_by_exact_hash(image_files: list[str]) -> dict[str, list[str]]:
    """
    Pre-group files by their exact byte-level MD5 hash as a fast first pass.
    Files with unique byte hashes still need perceptual hashing, but this
    quickly identifies byte-for-byte duplicates without loading images.
    """
    groups: dict[str, list[str]] = defaultdict(list)

    for filepath in image_files:
        try:
            file_hash = hashlib.md5(Path(filepath).read_bytes()).hexdigest()
            groups[file_hash].append(filepath)
        except Exception as e:
            print(f"  [WARN] Could not read {filepath}: {e}")

    return groups


def find_duplicates(
    root_dir: str,
    threshold: int = 10,
    hash_type: str = "phash",
) -> list[tuple[str, list[str]]]:
    """
    Find groups of duplicate images.

    Strategy:
    1. First group by exact MD5 hash (fast, catches identical files).
    2. For files with unique MD5 hashes, compute perceptual hashes and
       group those that are within the similarity threshold.

    Returns a list of (keeper, duplicates) tuples where:
      - keeper: the file path to keep (highest quality)
      - duplicates: list of file paths that are duplicates of the keeper
    """
    print(f"\n[1/4] Scanning for image files in: {root_dir}")
    image_files = collect_image_files(root_dir)
    print(f"  Found {len(image_files)} image files")

    if not image_files:
        return []

    # Step 1: Group by exact byte hash (instant duplicates)
    print("\n[2/4] Grouping by exact file hash...")
    exact_groups = group_by_exact_hash(image_files)

    # Files that are already in duplicate groups (byte-identical)
    exact_duplicate_files = set()
    duplicate_groups: list[tuple[str, list[str]]] = []

    for md5_hash, files in exact_groups.items():
        if len(files) > 1:
            # Pick the keeper based on quality score
            keeper = max(files, key=get_image_quality)
            dupes = [f for f in files if f != keeper]
            duplicate_groups.append((keeper, dupes))
            exact_duplicate_files.update(files)
            print(f"  Exact duplicate group: {len(files)} files (keeping {Path(keeper).name})")

    # Step 2: For remaining unique files, compute perceptual hashes
    unique_files = [f for f in image_files if f not in exact_duplicate_files]
    print(f"\n[3/4] Computing perceptual hashes for {len(unique_files)} unique files...")

    perceptual_hashes: list[tuple[str, imagehash.ImageHash]] = []
    for filepath in unique_files:
        phash = compute_perceptual_hash(filepath, hash_type)
        if phash is not None:
            perceptual_hashes.append((filepath, phash))

    # Compare all pairs of perceptual hashes and group near-duplicates
    # Use a union-find approach to merge overlapping groups
    parent = {filepath: filepath for filepath, _ in perceptual_hashes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # Path compression
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Compare all pairs (O(n^2) but practical for typical photo collections)
    print(f"  Comparing {len(perceptual_hashes)} hashes (threshold={threshold})...")
    near_dupes_found = 0

    for i in range(len(perceptual_hashes)):
        for j in range(i + 1, len(perceptual_hashes)):
            filepath_a, hash_a = perceptual_hashes[i]
            filepath_b, hash_b = perceptual_hashes[j]

            # Skip if already in the same group
            if find(filepath_a) == find(filepath_b):
                continue

            distance = hash_a - hash_b
            if distance <= threshold:
                union(filepath_a, filepath_b)
                near_dupes_found += 1

    print(f"  Found {near_dupes_found} near-duplicate pairs")

    # Build groups from union-find structure
    groups: dict[str, list[str]] = defaultdict(list)
    for filepath, _ in perceptual_hashes:
        groups[find(filepath)].append(filepath)

    # Convert groups to (keeper, duplicates) tuples
    for group_files in groups.values():
        if len(group_files) > 1:
            keeper = max(group_files, key=get_image_quality)
            dupes = [f for f in group_files if f != keeper]
            duplicate_groups.append((keeper, dupes))

    return duplicate_groups


def process_duplicates(
    duplicate_groups: list[tuple[str, list[str]]],
    mode: str = "dry-run",
    move_dir: str = "./duplicates",
) -> dict:
    """
    Process duplicate groups according to the chosen mode.

    Modes:
      - dry-run:  Print what would happen without modifying files
      - delete:   Permanently delete duplicate files
      - move:     Move duplicates to a separate folder

    Returns a summary dict with counts and details.
    """
    stats = {
        "total_groups": len(duplicate_groups),
        "total_duplicates": 0,
        "kept": [],
        "processed": [],
        "errors": [],
    }

    if mode == "move":
        os.makedirs(move_dir, exist_ok=True)

    for keeper, dupes in duplicate_groups:
        stats["total_duplicates"] += len(dupes)
        keeper_quality = get_image_quality(keeper)
        stats["kept"].append((keeper, keeper_quality))

        for dupe in dupes:
            dupe_quality = get_image_quality(dupe)
            dupe_size = dupe_quality[0] / (1024 * 1024)  # Convert to MB

            if mode == "dry-run":
                print(f"  [DRY-RUN] Would delete: {dupe} ({dupe_size:.2f} MB)")
                stats["processed"].append(("dry-run", dupe, None))

            elif mode == "delete":
                try:
                    os.remove(dupe)
                    print(f"  [DELETED] {dupe} ({dupe_size:.2f} MB)")
                    stats["processed"].append(("deleted", dupe, None))
                except Exception as e:
                    print(f"  [ERROR]  Failed to delete {dupe}: {e}")
                    stats["errors"].append((dupe, str(e)))

            elif mode == "move":
                try:
                    # Preserve relative directory structure in the move destination
                    rel_path = os.path.relpath(dupe)
                    dest = os.path.join(move_dir, rel_path)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.move(dupe, dest)
                    print(f"  [MOVED]   {dupe} -> {dest} ({dupe_size:.2f} MB)")
                    stats["processed"].append(("moved", dupe, dest))
                except Exception as e:
                    print(f"  [ERROR]  Failed to move {dupe}: {e}")
                    stats["errors"].append((dupe, str(e)))

    return stats


def print_summary(stats: dict, mode: str, threshold: int, hash_type: str) -> None:
    """Print a clear summary of the duplicate detection and processing results."""
    print("\n" + "=" * 70)
    print("DUPLICATE PHOTO DETECTOR - SUMMARY")
    print("=" * 70)
    print(f"  Hash algorithm:     {hash_type}")
    print(f"  Similarity threshold: {threshold}")
    print(f"  Mode:               {mode}")
    print(f"  Duplicate groups:   {stats['total_groups']}")
    print(f"  Total duplicates:   {stats['total_duplicates']}")

    # Calculate space that would be / was freed
    total_freed = 0
    for action, filepath, _ in stats["processed"]:
        try:
            total_freed += os.path.getsize(filepath)
        except Exception:
            pass

    print(f"  Space {'freed' if mode != 'dry-run' else 'recoverable'}: {total_freed / (1024 * 1024):.2f} MB")

    if stats["errors"]:
        print(f"  Errors:             {len(stats['errors'])}")

    print("-" * 70)

    # Show what was kept
    if stats["kept"]:
        print("\nFILES KEPT (highest quality from each group):")
        for filepath, (size, width, height) in stats["kept"]:
            print(f"  [KEEP] {filepath}")
            print(f"         Size: {size / (1024 * 1024):.2f} MB | Resolution: {width}x{height}")

    # Show errors
    if stats["errors"]:
        print("\nERRORS:")
        for filepath, error in stats["errors"]:
            print(f"  [ERROR] {filepath}: {error}")

    print("\n" + "=" * 70)

    if mode == "dry-run":
        print("This was a DRY RUN. No files were modified.")
        print("Add --delete to actually remove duplicates, or --move to relocate them.")
    print("=" * 70)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Detect and remove duplicate photos using perceptual hashing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "directory",
        help="Directory to scan for duplicate images",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=10,
        help="Max hash distance to consider images as duplicates (default: 10). "
             "Lower = stricter match, higher = catches more subtle duplicates.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Actually delete duplicate files (default is dry-run mode)",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move duplicates to a separate folder instead of deleting",
    )
    parser.add_argument(
        "--move-dir",
        default="./duplicates",
        help="Destination folder for moved duplicates (default: ./duplicates)",
    )
    parser.add_argument(
        "--hash-type",
        choices=["phash", "dhash", "ahash", "whash"],
        default="phash",
        help="Perceptual hash algorithm to use (default: phash)",
    )

    return parser.parse_args()


def main() -> None:
    """Main entry point for the duplicate photo detector."""
    args = parse_args()

    # Validate the target directory
    target_dir = os.path.abspath(args.directory)
    if not os.path.isdir(target_dir):
        print(f"Error: '{target_dir}' is not a valid directory.")
        sys.exit(1)

    # Determine the processing mode
    if args.delete:
        mode = "delete"
    elif args.move:
        mode = "move"
    else:
        mode = "dry-run"

    # Safety confirmation for destructive operations
    if mode in ("delete", "move"):
        action = "DELETE" if mode == "delete" else "MOVE"
        print(f"\nWARNING: You are about to {action} duplicate files!")
        print(f"Target directory: {target_dir}")
        response = input(f"Type 'YES' to confirm {action}: ")
        if response != "YES":
            print("Operation cancelled.")
            sys.exit(0)

    print(f"\nDuplicate Photo Detector")
    print(f"  Directory:  {target_dir}")
    print(f"  Hash type:  {args.hash_type}")
    print(f"  Threshold:  {args.threshold}")
    print(f"  Mode:       {mode}")

    # Find all duplicate groups
    duplicate_groups = find_duplicates(
        root_dir=target_dir,
        threshold=args.threshold,
        hash_type=args.hash_type,
    )

    if not duplicate_groups:
        print("\nNo duplicates found! Your photo collection is clean.")
        return

    # Process duplicates according to the chosen mode
    print(f"\n[4/4] Processing duplicates ({mode} mode)...")
    print("-" * 70)

    stats = process_duplicates(
        duplicate_groups=duplicate_groups,
        mode=mode,
        move_dir=os.path.abspath(args.move_dir),
    )

    # Print the final summary
    print_summary(stats, mode, args.threshold, args.hash_type)


if __name__ == "__main__":
    main()
