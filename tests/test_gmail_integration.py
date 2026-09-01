import base64
import unittest

from job_hunt.integrations.gmail import GoogleGmailReader


def _raw_message(message_id: str, subject: str) -> dict:
    body = base64.urlsafe_b64encode(f"Body for {subject}".encode()).decode().rstrip("=")
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "internalDate": "0",
        "payload": {
            "headers": [
                {"name": "From", "value": "alerts@example.com"},
                {"name": "Subject", "value": subject},
            ],
            "mimeType": "text/plain",
            "body": {"data": body},
        },
    }


class _Request:
    def __init__(self, owner, payload, *, is_message=False):
        self.owner = owner
        self.payload = payload
        self.is_message = is_message

    def execute(self):
        if self.is_message:
            self.owner.direct_message_requests += 1
        else:
            self.owner.list_requests += 1
        return self.payload


class _Messages:
    def __init__(self, owner):
        self.owner = owner

    def list(self, **_kwargs):
        references = [{"id": message_id} for message_id in self.owner.messages]
        return _Request(
            self.owner,
            {
                "messages": references,
                "resultSizeEstimate": len(references),
            },
        )

    def get(self, *, id, **_kwargs):
        return _Request(self.owner, self.owner.messages[id], is_message=True)


class _Users:
    def __init__(self, owner):
        self.owner = owner

    def messages(self):
        return _Messages(self.owner)


class _Batch:
    def __init__(self, owner):
        self.owner = owner
        self.requests = []

    def add(self, request, *, callback, request_id):
        self.requests.append((request_id, request, callback))

    def execute(self):
        self.owner.batch_requests += 1
        for request_id, request, callback in self.requests:
            if request_id in self.owner.failed_batch_request_ids:
                callback(request_id, None, RuntimeError("simulated partial batch failure"))
            else:
                callback(request_id, request.payload, None)


class _GmailService:
    def __init__(self, *, failed_batch_request_ids=()):
        self.messages = {
            "message-private-1": _raw_message("message-private-1", "First alert"),
            "message-private-2": _raw_message("message-private-2", "Second alert"),
        }
        self.failed_batch_request_ids = set(failed_batch_request_ids)
        self.list_requests = 0
        self.batch_requests = 0
        self.direct_message_requests = 0

    def users(self):
        return _Users(self)

    def new_batch_http_request(self):
        return _Batch(self)


class GmailIntegrationTests(unittest.TestCase):
    def test_reader_batches_full_message_downloads_and_emits_safe_progress(self):
        service = _GmailService()
        progress = []

        messages = GoogleGmailReader(service).list_alerts(
            "label:approved newer_than:1d",
            progress_callback=progress.append,
        )

        self.assertEqual([message.subject for message in messages], ["First alert", "Second alert"])
        self.assertEqual(service.list_requests, 1)
        self.assertEqual(service.batch_requests, 1)
        self.assertEqual(service.direct_message_requests, 0)
        self.assertEqual(progress[-1]["stage"], "gmail_fetch")
        self.assertEqual(progress[-1]["completed_items"], 2)
        self.assertEqual(progress[-1]["total_items"], 2)
        serialized_progress = str(progress)
        self.assertNotIn("message-private", serialized_progress)
        self.assertNotIn("Body for", serialized_progress)

    def test_reader_retries_a_partial_batch_failure_once(self):
        service = _GmailService(failed_batch_request_ids={"1"})

        messages = GoogleGmailReader(service).list_alerts(
            "label:approved newer_than:1d",
        )

        self.assertEqual(len(messages), 2)
        self.assertEqual(service.batch_requests, 1)
        self.assertEqual(service.direct_message_requests, 1)


if __name__ == "__main__":
    unittest.main()
