"""Attach the files an owner uploads in a WhatsApp Flow to their tender, as drawings.

Each file is decrypted and checked (see flow_media) before it is stored. The same
file types and revision rules as the website apply. One bad file doesn't stop the rest.
"""

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models.project import Project
from app.services.drawings import add_drawing_file
from app.services.file_security import ALLOWED_DRAWING_EXTENSIONS
from app.services.flow_media import MAX_FILE_BYTES, FileFetcher, FlowMediaError, decrypt_flow_media, download_cdn_file
from app.services.storage import get_storage

# One review screen sends at most this many files.
MAX_DOCUMENTS = 10

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "zip": "application/zip",
}


@dataclass
class AttachResult:
    attached: int = 0
    failed: list[str] = field(default_factory=list)


def _extension(file_name: str) -> str:
    return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""


def attach_flow_documents(db: Session, project: Project, documents: list[Any], *, fetch: FileFetcher = download_cdn_file) -> AttachResult:
    """Store each valid uploaded file as a drawing of the project. Commits once at the end."""
    result = AttachResult()
    for document in documents[:MAX_DOCUMENTS]:
        name = str(document.get("file_name") or "document") if isinstance(document, dict) else "document"
        try:
            if not isinstance(document, dict):
                raise FlowMediaError("The upload is not a file.")
            extension = _extension(name)
            if extension not in ALLOWED_DRAWING_EXTENSIONS or extension not in CONTENT_TYPES:
                raise FlowMediaError("This file type is not accepted.")
            content = decrypt_flow_media(fetch(str(document.get("cdn_url", ""))), document.get("encryption_metadata") or {})
            if len(content) > MAX_FILE_BYTES:
                raise FlowMediaError("This file is larger than 25 MB.")
            add_drawing_file(db, get_storage(), project.id, name, content, CONTENT_TYPES[extension])
            result.attached += 1
        except (FlowMediaError, OSError):
            result.failed.append(name)
    db.commit()
    return result
