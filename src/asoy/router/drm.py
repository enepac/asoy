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

OpenDocument has no such ambiguity. ODF records encryption inside `META-INF/manifest.xml`, as an
`encryption-data` child of the entry it applies to, and it has no benign second use — an entry
carrying one needs a password to read. Note that this is the user's own password rather than a
vendor's DRM, so the finding says so and the remedy differs: the user can produce an unprotected
copy themselves, which is not true of a DRM-protected book. Every protected finding carries its
own remedy for exactly this reason.
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

# ODF's manifest. Shared by ODT, ODS, and ODP, and by nothing else Asoy reads.
_ODF_MANIFEST_PATH = "META-INF/manifest.xml"
_ODF_ENCRYPTION_ELEMENT = "encryption-data"
_ODF_ALGORITHM_ELEMENT = "algorithm"
_ODF_ALGORITHM_NAME_ATTRIBUTE = "algorithm-name"

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
    ODF_ENCRYPTED = "odf_encrypted"


# What a user can do about a protected file, which is not the same answer for every kind. A
# vendor-DRM book cannot be unlocked by its owner; a file the owner encrypted themselves can.
DRM_REMEDY = (
    "Asoy cannot convert DRM-protected books, by design, and this is not a bug. "
    "Use a copy you can already open without the vendor's reader application. "
    "See the DRM section in SUPPORT.md."
)

PASSWORD_REMEDY = (
    "Open the document in the application that made it, supply the password, and save an "
    "unprotected copy for conversion. Asoy never asks for a password and never decrypts a file."
)


@dataclass(frozen=True)
class DrmFinding:
    """The outcome of one DRM inspection, with what the user can do about it."""

    protected: bool
    kind: Protection
    detail: str
    remedy: str = ""


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


def _odf_encrypted_entries(manifest_xml: bytes) -> list[tuple[str, str]]:
    """Every (entry path, algorithm) in an ODF manifest that declares encryption-data.

    Reads the manifest the same way any ODF reader reads it. Nothing here derives a key, and the
    `key-derivation` and `start-key-generation` elements that sit alongside the algorithm are
    deliberately not read at all.
    """
    root = ElementTree.fromstring(manifest_xml)
    found: list[tuple[str, str]] = []

    for entry in root.iter():
        if entry.tag.rsplit("}", 1)[-1] != "file-entry":
            continue

        full_path = next(
            (value for key, value in entry.attrib.items() if key.endswith("full-path")),
            "an entry",
        )
        for child in entry.iter():
            if child.tag.rsplit("}", 1)[-1] != _ODF_ENCRYPTION_ELEMENT:
                continue
            algorithm = "unnamed"
            for element in child.iter():
                if element.tag.rsplit("}", 1)[-1] != _ODF_ALGORITHM_ELEMENT:
                    continue
                algorithm = next(
                    (
                        value
                        for key, value in element.attrib.items()
                        if key.endswith(_ODF_ALGORITHM_NAME_ATTRIBUTE)
                    ),
                    algorithm,
                )
            found.append((full_path, algorithm))
            break

    return found


def _inspect_odf(archive: zipfile.ZipFile) -> DrmFinding:
    """Check an OpenDocument manifest for encrypted entries. _CLEAR if there are none."""
    encrypted = _odf_encrypted_entries(archive.read(_ODF_MANIFEST_PATH))
    if not encrypted:
        return _CLEAR

    entry, algorithm = encrypted[0]
    return DrmFinding(
        protected=True,
        kind=Protection.ODF_ENCRYPTED,
        detail=(
            f"The document is password protected: {len(encrypted)} entries are encrypted, "
            f"including {entry} (algorithm: {algorithm}). Asoy does not decrypt files."
        ),
        remedy=PASSWORD_REMEDY,
    )


def _inspect_zip(path: Path) -> DrmFinding:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

        for info in archive.infolist():
            if info.flag_bits & 0x1:
                return DrmFinding(
                    protected=True,
                    kind=Protection.ZIP_PASSWORD,
                    detail=f"The archive entry {info.filename} is password protected.",
                    remedy=PASSWORD_REMEDY,
                )

        # ODF hides its encryption in the manifest rather than in a file of its own, so this has
        # to be read to know. EPUB has no META-INF/manifest.xml, so the two never collide.
        if _ODF_MANIFEST_PATH in names:
            finding = _inspect_odf(archive)
            if finding.protected:
                return finding

        if _RIGHTS_PATH in names:
            return DrmFinding(
                protected=True,
                kind=Protection.EPUB_ADOBE_RIGHTS,
                detail=(
                    f"The book carries {_RIGHTS_PATH}, which indicates Adobe DRM. "
                    "Asoy does not remove DRM."
                ),
                remedy=DRM_REMEDY,
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
            remedy=DRM_REMEDY,
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
        remedy=DRM_REMEDY,
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
