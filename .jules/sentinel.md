## 2025-05-18 - Path Boundary Validation for Uploaded Scan Actions
**Vulnerability:** `/api/action` endpoint performed file deletion/moving operations based on file paths without verifying that target files or `move_dir` remained within the scan's temporary `upload_dir`.
**Learning:** Upload-based temporary scans create isolated directories for uploaded photos, but action endpoints can be manipulated or misused if file paths are not restricted using boundary checks like `os.path.commonpath`.
**Prevention:** For any action performed on uploaded session data, always resolve canonical paths and enforce `os.path.commonpath([target, boundary_dir]) == boundary_dir` before performing file mutations.
