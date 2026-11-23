import pytest

from app.config import get_settings
from app.services.document_files import DocumentValidationError, storage_path, validate_document

PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def test_a_real_pdf_is_accepted_and_described():
    result = validate_document("licence.pdf", PDF)
    assert result.extension == "pdf"
    assert result.mime_type == "application/pdf"
    assert result.size_bytes == len(PDF)
    assert len(result.sha256) == 64


def test_a_real_png_is_accepted():
    assert validate_document("scan.png", PNG).mime_type == "image/png"


@pytest.mark.parametrize("name", ["id.jpg", "id.jpeg", "ID.JPG"])
def test_jpeg_is_accepted_under_either_extension_and_stored_as_jpg(name):
    result = validate_document(name, JPEG)
    assert result.extension == "jpg"
    assert result.mime_type == "image/jpeg"


def test_an_empty_file_is_refused():
    with pytest.raises(DocumentValidationError, match="No file provided"):
        validate_document("licence.pdf", b"")


def test_a_file_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "document_max_mb", 1)
    with pytest.raises(DocumentValidationError, match="larger than 1 MB"):
        validate_document("big.pdf", PDF + b"0" * (1024 * 1024))


def test_a_file_exactly_at_the_limit_is_accepted(monkeypatch):
    monkeypatch.setattr(get_settings(), "document_max_mb", 1)
    validate_document("edge.pdf", PDF + b"0" * (1024 * 1024 - len(PDF)))


@pytest.mark.parametrize("name", ["notes.txt", "archive.zip", "page.html", "noextension", ""])
def test_an_extension_outside_the_allowlist_is_refused(name):
    with pytest.raises(DocumentValidationError, match="Upload a PDF, PNG or JPEG"):
        validate_document(name, PDF)


def test_bytes_that_are_not_any_allowed_type_are_refused():
    with pytest.raises(DocumentValidationError, match="not a PDF, PNG or JPEG"):
        validate_document("licence.pdf", b"MZ\x90\x00 this is an executable")


def test_a_pdf_renamed_to_png_is_refused_because_the_contents_do_not_match():
    with pytest.raises(DocumentValidationError, match="don't match its extension"):
        validate_document("licence.png", PDF)


def test_a_png_renamed_to_pdf_is_refused():
    with pytest.raises(DocumentValidationError, match="don't match its extension"):
        validate_document("licence.pdf", PNG)


def test_the_browser_claimed_type_is_never_trusted():
    # The validator takes no content type at all, so nothing the client claims can influence it.
    import inspect

    assert list(inspect.signature(validate_document).parameters) == ["filename", "content"]


@pytest.mark.parametrize(
    "fragment",
    [b"/JavaScript", b"/JS ", b"/Launch", b"/EmbeddedFile"],
)
def test_a_pdf_with_active_content_is_refused(fragment):
    hostile = PDF + b"\n2 0 obj << /S " + fragment + b" >> endobj\n"
    with pytest.raises(DocumentValidationError, match="embedded scripts"):
        validate_document("licence.pdf", hostile)


def test_a_pdf_that_merely_mentions_javascript_in_text_is_still_checked_by_name():
    # Known limit: this is a byte heuristic. It catches the common forms, not every encoding.
    with pytest.raises(DocumentValidationError):
        validate_document("licence.pdf", PDF + b"/JavaScript")


def test_stored_paths_never_contain_the_users_filename():
    path = storage_path("user-1", "req-1", "pdf")
    assert path.startswith("user-1/req-1/")
    assert path.endswith(".pdf")
    assert "licence" not in path
    assert ".." not in path


def test_two_stored_paths_for_the_same_requirement_differ():
    assert storage_path("u", "r", "pdf") != storage_path("u", "r", "pdf")
