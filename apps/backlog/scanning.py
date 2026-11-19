"""Virus scanning of uploaded files via a ClamAV daemon (clamd).

Implements the clamd INSTREAM protocol directly over TCP, so no additional
Python dependency is required. Configuration: ATTACHMENT_VIRUS_SCAN,
ATTACHMENT_SCAN_FAIL_CLOSED and CLAMAV_HOST/PORT/TIMEOUT.
"""

import logging
import socket
import struct

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024
MAX_REPLY_BYTES = 4096


class ScannerUnavailableError(Exception):
    """The scanner could not be reached or returned an error."""


class ClamAVScanner:
    def __init__(self, host: str, port: int, timeout: float):
        self.host = host
        self.port = port
        self.timeout = timeout

    def scan(self, uploaded_file) -> str | None:
        """Returns the signature name if malware was found, otherwise None."""
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout
            ) as connection:
                connection.sendall(b"zINSTREAM\0")
                for chunk in uploaded_file.chunks(CHUNK_SIZE):
                    connection.sendall(struct.pack("!L", len(chunk)) + chunk)
                connection.sendall(struct.pack("!L", 0))
                reply = self._read_reply(connection)
        except OSError as error:
            raise ScannerUnavailableError(str(error)) from error
        finally:
            uploaded_file.seek(0)
        return self._parse_reply(reply)

    @staticmethod
    def _read_reply(connection) -> str:
        data = b""
        while not data.endswith(b"\0") and len(data) < MAX_REPLY_BYTES:
            chunk = connection.recv(1024)
            if not chunk:
                break
            data += chunk
        return data.rstrip(b"\0").decode("utf-8", errors="replace").strip()

    @staticmethod
    def _parse_reply(reply: str) -> str | None:
        result = reply.split(":", 1)[-1].strip()
        if result == "OK":
            return None
        if result.endswith(" FOUND"):
            return result[: -len(" FOUND")].strip()
        raise ScannerUnavailableError(f"Unerwartete Antwort von clamd: {reply!r}")


def scan_upload(uploaded_file) -> None:
    """Raises ValidationError if the file is infected or cannot be checked."""
    mode = settings.ATTACHMENT_VIRUS_SCAN
    if mode == "disabled":
        return
    if mode != "clamav":
        raise ValidationError({"file": "Unbekannte Virenprüfung konfiguriert."})
    scanner = ClamAVScanner(
        settings.CLAMAV_HOST, settings.CLAMAV_PORT, settings.CLAMAV_TIMEOUT
    )
    try:
        signature = scanner.scan(uploaded_file)
    except ScannerUnavailableError:
        logger.exception("Virenprüfung nicht verfügbar.")
        if settings.ATTACHMENT_SCAN_FAIL_CLOSED:
            raise ValidationError(
                {"file": "Die Virenprüfung ist derzeit nicht verfügbar. "
                 "Der Upload wurde abgelehnt; bitte später erneut versuchen."}
            )
        return
    if signature:
        logger.warning(
            "Upload %r abgelehnt: Schadsoftware erkannt (%s).",
            uploaded_file.name, signature,
        )
        raise ValidationError(
            {"file": f"Die Datei wurde abgelehnt: Schadsoftware erkannt ({signature})."}
        )
