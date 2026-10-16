"""Reading the Affinity version out of an installer.

The installers are 670 MB, so the tests build the smallest Windows program
that has a version resource -- headers, one .rsrc section, the resource
directory three levels deep, VS_FIXEDFILEINFO -- and read that instead. The
network is never touched: current() is given a stand-in for urlopen.
"""
import io
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from affinity_manager import release  # noqa: E402

RSRC_RVA = 0x1000
RSRC_RAW = 0x400


def installer(version=(3, 3, 0, 4850), *, with_version=True, padding=0):
    """A minimal PE32+ whose version resource says `version`."""
    a, b, c, d = version
    fixed = (release.FIXED_SIGNATURE + struct.pack("<I", 0x10000)
             + struct.pack("<II", (a << 16) | b, (c << 16) | d) + b"\0" * 36)
    blob = b"VS_VERSION_INFO".ljust(40, b"\0") + fixed

    def directory(entries):
        out = struct.pack("<IIHHHH", 0, 0, 0, 0, 0, len(entries))
        for ident, ptr in entries:
            out += struct.pack("<II", ident, ptr)
        return out

    # root(16 -> name dir) -> name(1 -> lang dir) -> lang(0x409 -> data entry)
    root_type = 16 if with_version else 3
    root = directory([(root_type, 0x80000000 | 0x18)])
    name = directory([(1, 0x80000000 | 0x30)])
    lang = directory([(0x409, 0x48)])
    entry = struct.pack("<IIII", RSRC_RVA + 0x58 + padding, len(blob), 0, 0)
    rsrc = root + name + lang + entry
    rsrc = rsrc.ljust(0x58 + padding, b"\0") + blob

    pe = 0x80
    head = bytearray(RSRC_RAW)
    head[0:2] = b"MZ"
    struct.pack_into("<I", head, 0x3C, pe)
    head[pe:pe + 4] = b"PE\0\0"
    optional_size = 240
    struct.pack_into("<HH", head, pe + 4, 0x8664, 1)          # machine, 1 section
    struct.pack_into("<H", head, pe + 20, optional_size)
    optional = pe + 24
    struct.pack_into("<H", head, optional, 0x20B)
    struct.pack_into("<II", head, optional + 112 + 2 * 8, RSRC_RVA, len(rsrc))
    table = optional + optional_size
    struct.pack_into("<8sIIII", head, table, b".rsrc", len(rsrc), RSRC_RVA,
                     len(rsrc), RSRC_RAW)
    return bytes(head) + rsrc


def reader(data):
    return lambda at, length: data[at:at + length]


def test_it_reads_the_version():
    assert release.version_from(reader(installer())) == "3.3.0.4850"


def test_a_resource_far_into_the_section_is_still_found():
    """The real installer's .rsrc is 670 MB; the version need not be near
    its start, only the directory is."""
    assert release.version_from(reader(installer((3, 2, 3, 4646), padding=200_000))) \
        == "3.2.3.4646"


def test_a_file_on_disk(tmp_path):
    f = tmp_path / "Affinity-x64-3.3.0.4850.exe"
    f.write_bytes(installer())
    got = release.of_file(f)
    assert got.version == "3.3.0.4850" and str(got) == "Affinity 3.3.0.4850"


@pytest.mark.parametrize("data, why", [
    (b"not a program at all" * 300, "not a Windows program"),
    (installer(with_version=False), "no version resource"),
])
def test_what_is_not_an_installer_is_unknown_not_guessed(data, why):
    with pytest.raises(release.Unknown, match=why):
        release.version_from(reader(data))


def test_an_unreadable_file_says_so(tmp_path):
    with pytest.raises(release.Unknown, match="could not be read"):
        release.of_file(tmp_path / "missing.exe")


class FakeResponse(io.BytesIO):
    def __init__(self, data, status, headers):
        super().__init__(data)
        self.status = status
        self.headers = headers

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_current_reads_by_range_and_reports_the_date(monkeypatch):
    data = installer()
    asked = []

    def urlopen(request, timeout):
        start, _, end = request.headers["Range"].removeprefix("bytes=").partition("-")
        asked.append((int(start), int(end)))
        return FakeResponse(data[int(start):int(end) + 1], 206, {
            "Last-Modified": "Tue, 15 Sep 2026 10:00:39 GMT",
            "Content-Range": f"bytes {start}-{end}/673188936"})

    monkeypatch.setattr(release.urllib.request, "urlopen", urlopen)
    got = release.current()
    assert got.version == "3.3.0.4850"
    assert got.published == "2026-09-15" and got.size == 673188936
    assert len(asked) <= 3
    assert sum(e - s + 1 for s, e in asked) < 1024 * 1024


def test_a_server_ignoring_the_range_is_not_downloaded_whole(monkeypatch):
    monkeypatch.setattr(release.urllib.request, "urlopen",
                        lambda request, timeout: FakeResponse(b"", 200, {}))
    with pytest.raises(release.Unknown, match="part of the file"):
        release.current()


def test_offline_is_unknown(monkeypatch):
    def urlopen(request, timeout):
        raise OSError("Network is unreachable")

    monkeypatch.setattr(release.urllib.request, "urlopen", urlopen)
    with pytest.raises(release.Unknown, match="could not be reached"):
        release.current()
