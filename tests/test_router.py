"""Router and DRM tests (ARCHITECTURE section 4.3, invariant 2, ADR-014, ADR-010).

No real books are used. Every fixture is generated, and the DRM fixtures fake only the markers
that indicate protection.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from asoy.router import (
    CALIBRE_FORMATS,
    DIRECT_FORMATS,
    RejectionReason,
    Route,
    route,
)
from asoy.router.drm import Protection, inspect
from tests.epub_fixtures import (
    CHAPTER_ONE,
    CONTENT_ENCRYPTION_ALGORITHM,
    FONT_OBFUSCATION_ALGORITHM,
    add_adobe_rights,
    add_encryption_xml,
    build_epub,
    build_mobi,
)


@pytest.fixture
def plain_epub(tmp_path: Path) -> Path:
    return build_epub(tmp_path / "plain.epub", [("ch1", CHAPTER_ONE)])


def test_plain_epub_routes_direct(plain_epub: Path) -> None:
    decision = route(plain_epub)
    assert decision.route is Route.DIRECT
    assert decision.accepted is True
    assert decision.reason is RejectionReason.NONE


def test_kindle_format_routes_to_calibre(tmp_path: Path) -> None:
    book = build_mobi(tmp_path / "book.azw3", encryption=0)
    decision = route(book)
    assert decision.route is Route.CALIBRE
    assert decision.accepted is True


def test_unsupported_format_is_rejected(tmp_path: Path) -> None:
    odd = tmp_path / "book.xyz"
    odd.write_text("not a book", encoding="utf-8")
    decision = route(odd)
    assert decision.route is Route.REJECTED
    assert decision.reason is RejectionReason.UNSUPPORTED_FORMAT
    assert decision.remedy


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    decision = route(tmp_path / "absent.epub")
    assert decision.route is Route.REJECTED
    assert decision.reason is RejectionReason.MISSING


def test_directory_is_rejected(tmp_path: Path) -> None:
    folder = tmp_path / "a.epub"
    folder.mkdir()
    decision = route(folder)
    assert decision.route is Route.REJECTED
    assert decision.reason is RejectionReason.MISSING


# --- Invariant 2: DRM is rejected at ingestion -------------------------------------------------


def test_encrypted_epub_content_is_rejected(tmp_path: Path) -> None:
    """Invariant 2 and ADR-014: rejected at ingestion, with an explanation."""
    book = build_epub(tmp_path / "drm.epub", [("ch1", CHAPTER_ONE)])
    add_encryption_xml(book, CONTENT_ENCRYPTION_ALGORITHM)

    decision = route(book)
    assert decision.route is Route.REJECTED
    assert decision.reason is RejectionReason.DRM_PROTECTED
    assert "DRM" in decision.remedy
    assert decision.remedy.strip(), "a rejection must explain itself, not just refuse"


def test_adobe_rights_marker_is_rejected(tmp_path: Path) -> None:
    book = build_epub(tmp_path / "adept.epub", [("ch1", CHAPTER_ONE)])
    add_adobe_rights(book)

    decision = route(book)
    assert decision.route is Route.REJECTED
    assert decision.reason is RejectionReason.DRM_PROTECTED
    assert inspect(book).kind is Protection.EPUB_ADOBE_RIGHTS


def test_font_obfuscation_is_not_treated_as_drm(tmp_path: Path) -> None:
    """encryption.xml has two unrelated uses. Obfuscated fonts are not protection.

    Rejecting on the file's mere presence would refuse a large number of perfectly convertible
    books, which is a false positive users would experience as Asoy being broken.
    """
    book = build_epub(tmp_path / "fonts.epub", [("ch1", CHAPTER_ONE)])
    add_encryption_xml(book, FONT_OBFUSCATION_ALGORITHM, target="fonts/Body.otf")

    finding = inspect(book)
    assert finding.protected is False
    assert route(book).route is Route.DIRECT


def test_mixed_encryption_with_any_content_algorithm_is_rejected(tmp_path: Path) -> None:
    """A book that obfuscates fonts and also encrypts content is still protected."""
    book = build_epub(tmp_path / "mixed.epub", [("ch1", CHAPTER_ONE)])
    with zipfile.ZipFile(book, "a") as archive:
        archive.writestr(
            "META-INF/encryption.xml",
            '<?xml version="1.0"?><encryption xmlns:enc="http://www.w3.org/2001/04/xmlenc#">'
            f'<enc:EncryptedData><enc:EncryptionMethod Algorithm="{FONT_OBFUSCATION_ALGORITHM}"/>'
            "</enc:EncryptedData>"
            f'<enc:EncryptedData><enc:EncryptionMethod Algorithm="{CONTENT_ENCRYPTION_ALGORITHM}"/>'
            "</enc:EncryptedData></encryption>",
        )
    assert inspect(book).protected is True


@pytest.mark.parametrize("encryption", [1, 2])
def test_mobi_encryption_flag_is_rejected(tmp_path: Path, encryption: int) -> None:
    """Invariant 2 applies to every format, not only the ones Docling reads."""
    book = build_mobi(tmp_path / f"drm{encryption}.mobi", encryption=encryption)
    decision = route(book)
    assert decision.route is Route.REJECTED
    assert decision.reason is RejectionReason.DRM_PROTECTED
    assert inspect(book).kind is Protection.MOBI_ENCRYPTED


def test_unencrypted_mobi_is_not_rejected(tmp_path: Path) -> None:
    book = build_mobi(tmp_path / "clear.mobi", encryption=0)
    assert inspect(book).protected is False
    assert route(book).route is Route.CALIBRE


def test_drm_check_runs_before_the_calibre_decision(tmp_path: Path) -> None:
    """A protected Kindle book must be refused at ingestion, not handed to Calibre."""
    book = build_mobi(tmp_path / "drm.azw3", encryption=2)
    decision = route(book)
    assert decision.route is Route.REJECTED, "DRM must be caught before routing to Calibre"


def test_corrupt_zip_is_not_reported_as_drm(tmp_path: Path) -> None:
    book = tmp_path / "broken.epub"
    book.write_bytes(b"PK\x03\x04 not really a zip")
    finding = inspect(book)
    assert finding.protected is False


def test_route_never_raises_on_odd_input(tmp_path: Path) -> None:
    empty = tmp_path / "empty.epub"
    empty.write_bytes(b"")
    assert route(empty).route in {Route.DIRECT, Route.REJECTED}


# --- Invariant 5: the Calibre boundary ---------------------------------------------------------


def test_router_does_not_import_calibre() -> None:
    """Invariant 5 and ADR-010: Calibre is a subprocess, never a library.

    Importing it would relicense Asoy from Apache 2.0 to GPLv3. This asserts the module has no
    import-time dependency on any Calibre package.
    """
    import asoy.router

    source = Path(asoy.router.__file__).read_text(encoding="utf-8")
    for forbidden in ("import calibre", "from calibre"):
        assert forbidden not in source


def test_format_tables_do_not_overlap() -> None:
    """A format in both tables would make routing depend on dictionary order."""
    assert not (DIRECT_FORMATS & CALIBRE_FORMATS)
