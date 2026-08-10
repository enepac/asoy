"""Builders for EPUB fixtures, so the suite carries no third-party book files.

Everything here is generated at test time. That matters for licensing as much as for repository
size: a real book checked into a public Apache 2.0 repository would be someone else's copyrighted
work, and a DRM-protected sample could not be included at all.

The DRM fixtures below fake the *markers* that indicate protection. They contain no encrypted
content and no keys, and nothing here decrypts anything.
"""

from __future__ import annotations

import struct
import zipfile
from pathlib import Path

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">urn:uuid:asoy-test-0001</dc:identifier>
    <dc:title>{title}</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
{manifest}
  </manifest>
  <spine>
{spine}
  </spine>
</package>
"""

_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title}</title></head>
<body>
{body}
</body></html>
"""

# The IDPF font obfuscation algorithm. Present in many unprotected books; not DRM.
FONT_OBFUSCATION_ALGORITHM = "http://www.idpf.org/2008/embedding"

# A real content-encryption algorithm. Its presence means the text itself is encrypted.
CONTENT_ENCRYPTION_ALGORITHM = "http://www.w3.org/2001/04/xmlenc#aes128-cbc"

_ENCRYPTION_XML = """<?xml version="1.0" encoding="UTF-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
            xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="{algorithm}"/>
    <enc:CipherData><enc:CipherReference URI="OEBPS/{target}"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>
"""


def build_epub(path: Path, chapters: list[tuple[str, str]], *, title: str = "A Test Book") -> Path:
    """Build a text-only EPUB. Each chapter is (filename_stem, body_html)."""
    manifest = ['    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
                'properties="nav"/>']
    spine = []
    documents: dict[str, str] = {}

    for index, (stem, body) in enumerate(chapters):
        href = f"{stem}.xhtml"
        manifest.append(
            f'    <item id="c{index}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'    <itemref idref="c{index}"/>')
        documents[href] = _XHTML.format(title=stem, body=body)

    nav_items = "\n".join(
        f'<li><a href="{stem}.xhtml">{stem}</a></li>' for stem, _ in chapters
    )
    nav = _XHTML.format(
        title="Contents",
        body=f'<nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops">'
        f"<ol>{nav_items}</ol></nav>",
    )

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr("META-INF/container.xml", CONTAINER_XML)
        archive.writestr(
            "OEBPS/content.opf",
            _OPF.format(title=title, manifest="\n".join(manifest), spine="\n".join(spine)),
        )
        archive.writestr("OEBPS/nav.xhtml", nav)
        for href, content in documents.items():
            archive.writestr(f"OEBPS/{href}", content)

    return path


def add_encryption_xml(path: Path, algorithm: str, target: str = "ch1.xhtml") -> Path:
    """Append a META-INF/encryption.xml declaring the given algorithm."""
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(
            "META-INF/encryption.xml",
            _ENCRYPTION_XML.format(algorithm=algorithm, target=target),
        )
    return path


def add_adobe_rights(path: Path) -> Path:
    """Append the META-INF/rights.xml marker that indicates Adobe DRM."""
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("META-INF/rights.xml", "<rights/>")
    return path


def build_mobi(path: Path, *, encryption: int) -> Path:
    """Build a stub PalmDB file carrying a MOBI creator and the given encryption flag.

    This is a header only. There is no book content and nothing encrypted; the point is purely to
    exercise the flag read in the DRM inspector.
    """
    record0_offset = 100
    header = bytearray(b"\x00" * record0_offset)
    header[0:9] = b"TestBook\x00"
    header[60:64] = b"BOOK"
    header[64:68] = b"MOBI"
    struct.pack_into(">H", header, 76, 1)
    struct.pack_into(">I", header, 78, record0_offset)

    record0 = bytearray(b"\x00" * 32)
    struct.pack_into(">H", record0, 12, encryption)

    path.write_bytes(bytes(header) + bytes(record0))
    return path


# Convenience bodies used by several tests.
CHAPTER_ONE = """
<h1>The First Chapter</h1>
<p>It was a bright cold day in April, and the clocks were striking thirteen.</p>
<p>This sentance keeps its own misspelling, and its _underscores_ and *asterisks*.</p>
<h2>A Subsection</h2>
<p>Nested content lives here.</p>
"""

CHAPTER_TWO = """
<h1>The Second Chapter</h1>
<p>The second chapter says something else entirely.</p>
"""

FRONT_MATTER_THEN_CHAPTER = """
<p>Front matter before any heading. It must not be dropped.</p>
<h1>The Only Chapter</h1>
<p>Body of the only chapter.</p>
"""
