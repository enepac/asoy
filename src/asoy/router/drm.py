"""DRM detection at ingestion (CLAUDE.md invariant 2, ADR-014).

This module detects protection and refuses the file. It contains no circumvention of any kind,
and nothing here may be extended into any: no key handling, no decryption, no plugin hook that
could supply one. ADR-014 records that this is not negotiable and names no reversal condition.

Detection reads flags and manifests that any file-format reader reads. Refusing to convert a file
is the opposite of stripping its protection.

One nuance worth keeping. EPUB's `META-INF/encryption.xml` is used for two unrelated purposes:
real content encryption, and the font obfuscation scheme that many unprotected books use for
embedded typefaces. Treating every encryption.xml as DRM would reject a large number of perfectly
convertible books, so the algorithm is inspected rather than the file's mere presence.
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from xml.etree import ElementTree

# Obfuscated fonts are not DRM. These two algorithms mangle an embedded typeface so it cannot be
# lifted out and reused; the book's text is untouched and converts normally.
FONT_OBFUSCATION_ALGORITHMS = frozenset(
    {
        "http://www.idpf.org/2008/embedding",
        "http://ns.adobe.com/pdf/enc#RC",
    }
)

_ENCRYPTION_PATH = "META-INF/encryption.xml"
_RIGHTS_PATH = "META-INF/rights.xml"

# PalmDB layout, used by MOBI, AZW, and PRC. The encryption flag sits at offset 12 of record 0.
_PALMDB_NUM_RECORDS_OFFSET = 76
_PALMDB_RECORD_INFO_OFFSET = 78
_PALMDOC_ENCRYPTION_OFFSET = 12
_MOBI_CREATORS = frozenset({b"MOBI", b"TEXt", b"BOOK"})


class Protection(StrEnum):
    """What kind of protection was found. NONE means the file may be converted."""

    NONE = "none"
    EPUB_ENCRYPTED_CONTENT = "epub_encrypted_content"
    EPUB_ADOBE_RIGHTS = "epub_adobe_rights"
    ZIP_PASSWORD = "zip_password"
    MOBI_ENCRYPTED = "mobi_encrypted"


@dataclass(frozen=True)
class DrmFinding:
    """The outcome of one DRM inspection."""

    protected: bool
    kind: Protection
    detail: str


_CLEAR = DrmFinding(protected=False, kind=Protection.NONE, detail="No protection detected.")


def _algorithms(encryption_xml: bytes) -> list[str]:
    """Every EncryptionMethod/@Algorithm in an EPUB encryption.xml, in document order."""
    root = ElementTree.fromstring(encryption_xml)
    found: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "EncryptionMethod":
            algorithm = element.get("Algorithm")
            if algorithm:
                found.append(algorithm)
    return found


def _inspect_zip(path: Path) -> DrmFinding:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

        for info in archive.infolist():
            if info.flag_bits & 0x1:
                return DrmFinding(
                    protected=True,
                    kind=Protection.ZIP_PASSWORD,
                    detail=f"The archive entry {info.filename} is password protected.",
                )

        if _RIGHTS_PATH in names:
            return DrmFinding(
                protected=True,
                kind=Protection.EPUB_ADOBE_RIGHTS,
                detail=(
                    f"The book carries {_RIGHTS_PATH}, which indicates Adobe DRM. "
                    "Asoy does not remove DRM."
                ),
            )

        if _ENCRYPTION_PATH not in names:
            return _CLEAR

        algorithms = _algorithms(archive.read(_ENCRYPTION_PATH))
        content_encryption = [a for a in algorithms if a not in FONT_OBFUSCATION_ALGORITHMS]
        if not content_encryption:
            # Font obfuscation only. The text is not encrypted, so the book converts normally.
            return _CLEAR

        return DrmFinding(
            protected=True,
            kind=Protection.EPUB_ENCRYPTED_CONTENT,
            detail=(
                "The book's content is encrypted "
                f"(algorithm: {content_encryption[0]}). Asoy does not remove DRM."
            ),
        )


def _inspect_palmdb(path: Path) -> DrmFinding:
    """Read the PalmDOC encryption flag. This reads a number; it does not decrypt anything."""
    with path.open("rb") as handle:
        header = handle.read(_PALMDB_RECORD_INFO_OFFSET + 8)
        if len(header) < _PALMDB_RECORD_INFO_OFFSET + 8:
            return _CLEAR
        if header[60:64] not in _MOBI_CREATORS and header[64:68] not in _MOBI_CREATORS:
            return _CLEAR

        (record_count,) = struct.unpack(">H", header[_PALMDB_NUM_RECORDS_OFFSET:][:2])
        if record_count < 1:
            return _CLEAR

        (record0_offset,) = struct.unpack(">I", header[_PALMDB_RECORD_INFO_OFFSET:][:4])
        handle.seek(record0_offset + _PALMDOC_ENCRYPTION_OFFSET)
        raw = handle.read(2)
        if len(raw) < 2:
            return _CLEAR

        (encryption,) = struct.unpack(">H", raw)

    if encryption == 0:
        return _CLEAR
    return DrmFinding(
        protected=True,
        kind=Protection.MOBI_ENCRYPTED,
        detail=(
            f"The file reports Mobipocket encryption type {encryption}. Asoy does not remove DRM."
        ),
    )


def inspect(path: Path) -> DrmFinding:
    """Inspect a file for DRM. Returns a finding; raises only if the file cannot be read."""
    if zipfile.is_zipfile(path):
        try:
            return _inspect_zip(path)
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as exc:
            # A container we cannot read is not evidence of DRM. Say so rather than guessing,
            # and let the caller decide; a malformed book fails later with a clearer message.
            return DrmFinding(
                protected=False,
                kind=Protection.NONE,
                detail=f"Could not inspect the container for DRM ({type(exc).__name__}: {exc}).",
            )

    try:
        return _inspect_palmdb(path)
    except OSError:
        raise
    except Exception as exc:
        return DrmFinding(
            protected=False,
            kind=Protection.NONE,
            detail=f"Could not inspect the file for DRM ({type(exc).__name__}: {exc}).",
        )
