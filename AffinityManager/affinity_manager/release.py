"""Which version of Affinity an installer holds -- without running it.

downloads.affinity.studio has one URL for whatever the current release is:
no version in the path, none in the headers (only a date and a size). So the
manager could say "the current release" and not which one, and a new prefix
was created without anyone knowing what it would get.

The version is in the installer itself, in the standard Windows version
resource. The installer is 670 MB, but the resource is small and its address
is in the first few kilobytes, and the server answers range requests -- so
reading it is three requests and well under a megabyte. The same parser reads
an installer kept on disk, which is what a pinned install uses.

Only the standard PE layout is read: the section table, the resource
directory, and VS_FIXEDFILEINFO. Anything that does not fit it is reported as
unknown rather than guessed.
"""

from __future__ import annotations

import struct
import urllib.request
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

CURRENT_URL = "https://downloads.affinity.studio/Affinity%20x64.exe"

RT_VERSION = 16
FIXED_SIGNATURE = b"\xbd\x04\xef\xfe"
HEADER_BYTES = 4096
DIRECTORY_BYTES = 64 * 1024     # the resource directory sits at the start of .rsrc


class Unknown(Exception):
    """The version could not be read; the message says why."""


@dataclass
class Release:
    version: str                # "3.3.0.4850"
    published: str = ""         # the server's Last-Modified, as YYYY-MM-DD
    size: int = 0

    def __str__(self):
        return f"Affinity {self.version}"


# ── reading ───────────────────────────────────────────────────────────────────


def version_from(read) -> str:
    """The file version, given read(offset, length) -> bytes over the installer."""
    head = read(0, HEADER_BYTES)
    try:
        if head[:2] != b"MZ":
            raise Unknown("not a Windows program")
        pe = struct.unpack_from("<I", head, 0x3C)[0]
        if head[pe:pe + 4] != b"PE\0\0":
            raise Unknown("not a Windows program")
        sections = struct.unpack_from("<H", head, pe + 6)[0]
        optional_size = struct.unpack_from("<H", head, pe + 20)[0]
        optional = pe + 24
        magic = struct.unpack_from("<H", head, optional)[0]
        directories = optional + (112 if magic == 0x20B else 96)
        rsrc_rva, rsrc_size = struct.unpack_from("<II", head, directories + 2 * 8)
        table = optional + optional_size
        found = None
        for i in range(sections):
            _, vsize, va, rawsize, raw = struct.unpack_from("<8sIIII", head, table + 40 * i)
            if va <= rsrc_rva < va + max(vsize, rawsize):
                found = (va, raw)
                break
    except struct.error as exc:
        raise Unknown("its header is cut short") from exc
    if not rsrc_rva or found is None:
        raise Unknown("it carries no resources")
    va, raw = found

    def offset(rva):
        return raw + (rva - va)

    base = offset(rsrc_rva)
    tree = read(base, min(rsrc_size, DIRECTORY_BYTES))

    def entries(at):
        named, ids = struct.unpack_from("<HH", tree, at + 12)
        return [struct.unpack_from("<II", tree, at + 16 + 8 * i)
                for i in range(named + ids)]

    try:
        version_dir = next((ptr for ident, ptr in entries(0)
                            if not ident & 0x80000000 and ident == RT_VERSION), None)
        if version_dir is None or not version_dir & 0x80000000:
            raise Unknown("it has no version resource")
        node = version_dir & 0x7FFFFFFF
        # type -> name -> language -> data entry
        for _ in range(2):
            node_entries = entries(node)
            if not node_entries:
                raise Unknown("its version resource is empty")
            node = node_entries[0][1]
            if node & 0x80000000:
                node &= 0x7FFFFFFF
            else:
                break
        data_rva, data_size = struct.unpack_from("<II", tree, node)
    except struct.error as exc:
        raise Unknown("its resource directory is cut short") from exc

    data = read(offset(data_rva), min(data_size, 64 * 1024))
    at = data.find(FIXED_SIGNATURE)
    if at < 0 or len(data) < at + 16:
        raise Unknown("its version resource has no version in it")
    ms, ls = struct.unpack_from("<II", data, at + 8)
    return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"


def of_file(path) -> Release:
    """The Affinity version in an installer on disk."""
    path = Path(path).expanduser()
    try:
        with open(path, "rb") as f:
            def read(at, length):
                f.seek(at)
                return f.read(length)
            version = version_from(read)
        size = path.stat().st_size
    except OSError as exc:
        raise Unknown(f"it could not be read: {exc.strerror or exc}") from exc
    return Release(version, size=size)


def current(url: str = CURRENT_URL, timeout: float = 15.0) -> Release:
    """The version downloads.affinity.studio is serving right now."""
    meta = {}

    def read(at, length):
        request = urllib.request.Request(
            url, headers={"Range": f"bytes={at}-{at + length - 1}"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if response.status != 206:
                    # Ignoring the range would mean downloading 670 MB to read
                    # a few kilobytes of it. Not done.
                    raise Unknown("the download server does not allow reading "
                                  "part of the file")
                meta.setdefault("modified", response.headers.get("Last-Modified", ""))
                total = response.headers.get("Content-Range", "").rpartition("/")[2]
                if total.isdigit():
                    meta.setdefault("size", int(total))
                return response.read()
        except OSError as exc:
            raise Unknown(f"the download server could not be reached: "
                          f"{getattr(exc, 'reason', exc)}") from exc

    version = version_from(read)
    published = ""
    try:
        published = parsedate_to_datetime(meta.get("modified", "")).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    return Release(version, published=published, size=meta.get("size", 0))
