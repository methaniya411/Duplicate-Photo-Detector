import os
import shutil
import tempfile
import unittest
from app import app, scan_results

class AppSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_api_action_upload_scan_path_traversal_prevention(self):
        # Create a temp upload dir and an external sensitive file
        temp_dir = tempfile.mkdtemp()
        ext_dir = tempfile.mkdtemp()
        sensitive_file = os.path.join(ext_dir, "sensitive.txt")
        with open(sensitive_file, "w") as f:
            f.write("secret data")

        try:
            scan_id = "test-scan-123"
            scan_results[scan_id] = {
                "upload_dir": temp_dir,
                "groups": [
                    {
                        "keeper": os.path.join(temp_dir, "keep.jpg"),
                        "duplicates": [sensitive_file],
                        "duplicates_info": [
                            {
                                "path": sensitive_file,
                                "name": "sensitive.txt",
                                "size": 11,
                                "width": 0,
                                "height": 0
                            }
                        ]
                    }
                ],
                "done": True
            }

            response = self.app.post("/api/action", json={
                "scan_id": scan_id,
                "action": "delete"
            })

            # Sensitive file outside upload_dir must NOT be deleted
            self.assertTrue(os.path.exists(sensitive_file), "Sensitive file outside upload directory was deleted!")
            data = response.get_json()
            self.assertTrue(len(data.get("errors", [])) > 0 or response.status_code == 400)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            shutil.rmtree(ext_dir, ignore_errors=True)
            scan_results.pop("test-scan-123", None)

    def test_api_action_move_dir_path_traversal(self):
        temp_dir = tempfile.mkdtemp()
        target_file = os.path.join(temp_dir, "test.jpg")
        with open(target_file, "w") as f:
            f.write("image data")

        try:
            scan_id = "test-scan-move"
            scan_results[scan_id] = {
                "upload_dir": temp_dir,
                "groups": [
                    {
                        "keeper": os.path.join(temp_dir, "keep.jpg"),
                        "duplicates": [target_file],
                        "duplicates_info": [
                            {
                                "path": target_file,
                                "name": "test.jpg",
                                "size": 10,
                                "width": 0,
                                "height": 0
                            }
                        ]
                    }
                ],
                "done": True
            }

            # Attempt to move outside allowed location via relative traversal
            response = self.app.post("/api/action", json={
                "scan_id": scan_id,
                "action": "move",
                "move_dir": "../../../tmp/escaped"
            })

            data = response.get_json()
            self.assertTrue(len(data.get("errors", [])) > 0 or response.status_code == 400)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            scan_results.pop("test-scan-move", None)

if __name__ == "__main__":
    unittest.main()
