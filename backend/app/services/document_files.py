import hashlib
import re
import uuid
from dataclasses import dataclass

from app.config import get_settings

# Extensions the upload accepts, and the canonical type each one must match.
# jpeg is folded into jpg so the stored extension is consistent.
_CANONICAL_EXTENSION = {"pdf": "pdf", "png": "png", "jpg": "jpg", "jpeg": "jpg"}
_MIME_BY_CANONICAL = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg"}

# Active content that has no place in a document we review. This is a heuristic
# over the raw bytes: a name inside a compressed object stream can slip past it.
# Treat it as one layer, not the only one.
_PDF_ACTIVE_CONTENT = re.compile(rb"/(JavaScript|JS|Launch|EmbeddedFile)\b")


class DocumentValidationError(Exception):
    """The file was refused. The message is safe to show the user."""


@dataclass(frozen=True)
class ValidatedDocument:
    extension: str  # canonical: pdf | png | jpg
    mime_type: str
    size_bytes: int
    sha256: str


def _detect(content: bytes) -> str | None:
    """Sniff the real type from the first bytes. The filename and the browser's claim are not trusted."""
    if content.startswith(b"%PDF-"):
        return "pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpg"
    return None


def validate_document(filename: str | None, content: bytes) -> ValidatedDocument:
    """Accept a PDF, PNG or JPEG only when the bytes match the extension and the size limit.

    Checks, in order: non-empty, size limit, allowed extension, magic bytes match
    that extension, and (for PDFs) no active content.
    """
    if not content:
        raise DocumentValidationError("No file provided.")

    max_bytes = get_settings().document_max_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise DocumentValidationError(f"The file is larger than {get_settings().document_max_mb} MB.")

    extension = (filename or "").rsplit(".", 1)[-1].lower() if filename and "." in filename else ""
    if extension not in _CANONICAL_EXTENSION:
        raise DocumentValidationError("Upload a PDF, PNG or JPEG file.")
    canonical = _CANONICAL_EXTENSION[extension]

    detected = _detect(content)
    if detected is None:
        raise DocumentValidationError("The file is not a PDF, PNG or JPEG.")
    if detected != canonical:
        raise DocumentValidationError("The file contents don't match its extension.")

    if canonical == "pdf" and _PDF_ACTIVE_CONTENT.search(content):
        raise DocumentValidationError("PDFs with embedded scripts or launch actions are not accepted.")

    return ValidatedDocument(
        extension=canonical,
        mime_type=_MIME_BY_CANONICAL[canonical],
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def storage_path(user_id: str, requirement_id: str, extension: str) -> str:
    """A random name under the user and requirement. The user's own filename is never used, which removes path tricks."""
    return f"{user_id}/{requirement_id}/{uuid.uuid4().hex}.{extension}"
