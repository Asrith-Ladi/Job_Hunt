import tempfile
import unittest
from pathlib import Path

from job_hunt.integrations.drive_export import (
    EXCEL_MIME_TYPE,
    export_google_sheet_as_xlsx,
)


class _FakeFiles:
    def __init__(self):
        self.call = None

    def export_media(self, **kwargs):
        self.call = kwargs
        return object()


class _FakeDrive:
    def __init__(self):
        self.files_resource = _FakeFiles()

    def files(self):
        return self.files_resource


class _FakeDownloader:
    def __init__(self, buffer, request):
        self.buffer = buffer
        self.request = request

    def next_chunk(self):
        self.buffer.write(b"xlsx-content")
        return None, True


class DriveExportTests(unittest.TestCase):
    def test_export_writes_excel_atomically(self):
        drive = _FakeDrive()
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "job_hunt.xlsx"
            result = export_google_sheet_as_xlsx(
                credentials=object(),
                spreadsheet_id="sheet-123",
                output_path=output,
                drive_service=drive,
                downloader_factory=_FakeDownloader,
            )
            self.assertEqual(result, output)
            self.assertEqual(output.read_bytes(), b"xlsx-content")
            self.assertFalse(output.with_suffix(".xlsx.tmp").exists())
        self.assertEqual(
            drive.files_resource.call,
            {"fileId": "sheet-123", "mimeType": EXCEL_MIME_TYPE},
        )

    def test_export_requires_xlsx_suffix(self):
        with self.assertRaises(ValueError):
            export_google_sheet_as_xlsx(
                credentials=object(),
                spreadsheet_id="sheet-123",
                output_path=Path("tracker.csv"),
                drive_service=_FakeDrive(),
                downloader_factory=_FakeDownloader,
            )


if __name__ == "__main__":
    unittest.main()
