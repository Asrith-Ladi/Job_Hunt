import base64
import unittest

from job_hunt.integrations.gmail import _decode_body, alert_message_from_api


def _encoded(value):
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


class GmailPayloadTests(unittest.TestCase):
    def test_nested_mime_parts_are_decoded_without_attachments(self):
        raw = {
            "id": "message-1",
            "threadId": "thread-1",
            "internalDate": "1784419200000",
            "payload": {
                "mimeType": "multipart/alternative",
                "headers": [
                    {"name": "From", "value": "alerts@linkedin.com"},
                    {"name": "Subject", "value": "LinkedIn alert"},
                ],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": _encoded("Plain")}},
                    {"mimeType": "text/html", "body": {"data": _encoded("<b>HTML</b>")}},
                    {
                        "mimeType": "text/plain",
                        "filename": "ignored.txt",
                        "body": {"data": _encoded("Private attachment")},
                    },
                ],
            },
        }

        message = alert_message_from_api(raw)

        self.assertEqual(message.message_id, "message-1")
        self.assertEqual(message.sender, "alerts@linkedin.com")
        self.assertEqual(message.text_body, "Plain")
        self.assertEqual(message.html_body, "<b>HTML</b>")

    def test_invalid_base64_is_ignored(self):
        self.assertEqual(_decode_body("%%%not-base64%%%"), "")


if __name__ == "__main__":
    unittest.main()
