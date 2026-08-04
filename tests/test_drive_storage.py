import tempfile
import unittest
from pathlib import Path

from job_hunt.integrations.drive_storage import (
    EXCEL_MIME_TYPE,
    FOLDER_MIME_TYPE,
    ensure_job_hunt_folders,
    upload_or_update_file,
)


class _Request:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class _Files:
    def __init__(self):
        self.items = []
        self.creates = []
        self.updates = []

    def list(self, **kwargs):
        query = kwargs["q"]
        matches = []
        for item in self.items:
            if "name = '{0}'".format(item["name"]) not in query:
                continue
            if "mimeType = '{0}'".format(item["mimeType"]) not in query:
                continue
            parent = (item.get("parents") or [None])[0]
            if " in parents" in query and "'{0}' in parents".format(parent) not in query:
                continue
            matches.append(dict(item))
        return _Request({"files": matches})

    def create(self, **kwargs):
        body = dict(kwargs["body"])
        item = {
            "id": "id-{0}".format(len(self.items) + 1),
            "name": body["name"],
            "mimeType": body["mimeType"],
            "parents": body.get("parents", []),
            "webViewLink": "https://drive.example/{0}".format(len(self.items) + 1),
        }
        self.items.append(item)
        self.creates.append(kwargs)
        return _Request(dict(item))

    def update(self, **kwargs):
        self.updates.append(kwargs)
        item = next(item for item in self.items if item["id"] == kwargs["fileId"])
        return _Request(dict(item))


class _Drive:
    def __init__(self):
        self.resource = _Files()

    def files(self):
        return self.resource


class _Uploader:
    def __init__(self, path, mimetype, resumable):
        self.path = path
        self.mimetype = mimetype
        self.resumable = resumable


class DriveStorageTests(unittest.TestCase):
    def test_folder_tree_is_idempotent_and_run_date_is_nested(self):
        drive = _Drive()
        first = ensure_job_hunt_folders(drive, run_date="2026-08-01")
        second = ensure_job_hunt_folders(drive, run_date="2026-08-01")

        self.assertEqual(first["root"]["id"], second["root"]["id"])
        self.assertEqual(first["source"]["id"], second["source"]["id"])
        self.assertEqual(first["date"]["id"], second["date"]["id"])
        self.assertEqual(len(drive.resource.items), 3)
        self.assertEqual(first["source"]["parents"], [first["root"]["id"]])
        self.assertEqual(first["date"]["parents"], [first["root"]["id"]])
        self.assertTrue(all(item["mimeType"] == FOLDER_MIME_TYPE for item in drive.resource.items))

    def test_run_file_is_created_then_updated_in_place(self):
        drive = _Drive()
        folders = ensure_job_hunt_folders(drive, run_date="2026-08-01")
        with tempfile.TemporaryDirectory() as directory:
            local_path = Path(directory) / "gmail_alerts_2026-08-01_140000.xlsx"
            local_path.write_bytes(b"first")
            created = upload_or_update_file(
                drive,
                local_path,
                parent_id=folders["date"]["id"],
                uploader_factory=_Uploader,
            )
            local_path.write_bytes(b"second")
            updated = upload_or_update_file(
                drive,
                local_path,
                parent_id=folders["date"]["id"],
                existing_file_id=created["id"],
                uploader_factory=_Uploader,
            )

        self.assertEqual(created["id"], updated["id"])
        self.assertEqual(created["mimeType"], EXCEL_MIME_TYPE)
        self.assertEqual(len(drive.resource.updates), 1)


if __name__ == "__main__":
    unittest.main()
