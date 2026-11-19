import socketserver
import struct
import threading

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.backlog.models import Attachment
from apps.backlog.scanning import ClamAVScanner, ScannerUnavailableError
from apps.backlog.services import add_attachment
from tests.factories import add_member, make_item, make_project, make_user

EICAR = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
)


class FakeClamdHandler(socketserver.BaseRequestHandler):
    """Implements the clamd INSTREAM protocol for tests."""

    def handle(self):
        command = b""
        while not command.endswith(b"\0"):
            command += self.request.recv(1)
        payload = b""
        while True:
            size = struct.unpack("!L", self._read(4))[0]
            if size == 0:
                break
            payload += self._read(size)
        self.server.received.append((command, payload))
        if EICAR in payload:
            reply = b"stream: Eicar-Test-Signature FOUND\0"
        else:
            reply = b"stream: OK\0"
        self.request.sendall(reply)

    def _read(self, size):
        data = b""
        while len(data) < size:
            data += self.request.recv(size - len(data))
        return data


class FakeClamd:
    def __enter__(self):
        self.server = socketserver.ThreadingTCPServer(
            ("127.0.0.1", 0), FakeClamdHandler
        )
        self.server.received = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.server

    def __exit__(self, *exc_info):
        self.server.shutdown()
        self.server.server_close()


def unused_port() -> int:
    with socketserver.TCPServer(("127.0.0.1", 0), None) as probe:
        return probe.server_address[1]


class ClamAVScannerTests(TestCase):
    def test_clean_stream_returns_no_signature(self):
        with FakeClamd() as server:
            scanner = ClamAVScanner("127.0.0.1", server.server_address[1], 5)
            upload = SimpleUploadedFile("a.txt", b"x" * 200_000)
            self.assertIsNone(scanner.scan(upload))
            command, payload = server.received[0]
        self.assertEqual(command, b"zINSTREAM\0")
        self.assertEqual(len(payload), 200_000)
        self.assertEqual(upload.read(1), b"x")

    def test_infected_stream_returns_signature(self):
        with FakeClamd() as server:
            scanner = ClamAVScanner("127.0.0.1", server.server_address[1], 5)
            result = scanner.scan(SimpleUploadedFile("e.txt", EICAR))
        self.assertEqual(result, "Eicar-Test-Signature")

    def test_unreachable_scanner_raises(self):
        scanner = ClamAVScanner("127.0.0.1", unused_port(), 1)
        with self.assertRaises(ScannerUnavailableError):
            scanner.scan(SimpleUploadedFile("a.txt", b"abc"))


class AttachmentScanTests(TestCase):
    def setUp(self):
        project = make_project("HELP")
        self.user = make_user()
        add_member(project, self.user)
        self.item = make_item(project)

    def upload(self, content=b"Hallo"):
        return add_attachment(
            self.item, uploaded_by=self.user,
            uploaded_file=SimpleUploadedFile("notiz.txt", content, "text/plain"),
        )

    def test_infected_upload_is_rejected(self):
        with FakeClamd() as server:
            with override_settings(
                ATTACHMENT_VIRUS_SCAN="clamav", CLAMAV_PORT=server.server_address[1]
            ):
                with self.assertRaises(ValidationError):
                    self.upload(EICAR)
                self.upload()
        self.assertEqual(Attachment.objects.count(), 1)

    @override_settings(ATTACHMENT_VIRUS_SCAN="clamav", ATTACHMENT_SCAN_FAIL_CLOSED=True)
    def test_unavailable_scanner_rejects_upload_when_fail_closed(self):
        with override_settings(CLAMAV_PORT=unused_port()):
            with self.assertRaises(ValidationError):
                self.upload()
        self.assertFalse(Attachment.objects.exists())

    @override_settings(
        ATTACHMENT_VIRUS_SCAN="clamav", ATTACHMENT_SCAN_FAIL_CLOSED=False
    )
    def test_unavailable_scanner_allows_upload_when_fail_open(self):
        with override_settings(CLAMAV_PORT=unused_port()):
            self.upload()
        self.assertTrue(Attachment.objects.exists())
