import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "AffinityScripts"
    / "AffinityClipboardBridge.py"
)
SPEC = importlib.util.spec_from_file_location("affinity_clipboard_bridge", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class ClipboardBridgeTests(unittest.TestCase):
    def test_read_bounded_preserves_binary_nul_bytes(self):
        expected = b"\x89PNG\r\n\x1a\n\x00binary\x00payload"
        code = f"import sys; sys.stdout.buffer.write({expected!r})"
        payload, status = bridge.read_bounded(
            [sys.executable, "-c", code], max_bytes=1024
        )
        self.assertEqual(status, "ok")
        self.assertEqual(payload, expected)

    def test_read_bounded_rejects_oversized_payload(self):
        code = "import sys; sys.stdout.buffer.write(b'x' * 1025)"
        payload, status = bridge.read_bounded(
            [sys.executable, "-c", code], max_bytes=1024
        )
        self.assertIsNone(payload)
        self.assertEqual(status, "too-large")

    def test_read_bounded_times_out_nonterminating_source(self):
        code = "import time; time.sleep(2)"
        payload, status = bridge.read_bounded(
            [sys.executable, "-c", code], max_bytes=1024, timeout=0.05
        )
        self.assertIsNone(payload)
        self.assertEqual(status, "timeout")

    def test_uri_list_has_one_canonical_terminator(self):
        payload = b"# comment\nfile:///tmp/a.png\r\n\nfile:///tmp/b.png\n\n"
        expected = b"file:///tmp/a.png\r\nfile:///tmp/b.png\r\n"
        self.assertEqual(
            bridge.normalize_payload("text/uri-list", payload), expected
        )

    def test_no_relevant_format_clears_cached_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            digest_path = Path(directory) / "digest"
            digest_path.write_text("00" * 32)
            with mock.patch.object(bridge, "get_types", return_value={"text/plain"}):
                status = bridge.process_current_selection(
                    "wl-paste", "xclip", 1024, digest_path
                )
            self.assertEqual(status, "no-relevant-format")
            self.assertFalse(digest_path.exists())

    def test_xclip_failure_is_not_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            digest_path = Path(directory) / "digest"
            with (
                mock.patch.object(bridge, "get_types", return_value={"image/png"}),
                mock.patch.object(
                    bridge, "read_bounded", return_value=(b"PNG\x00data", "ok")
                ),
                mock.patch.object(bridge, "set_x11_clipboard", return_value=False),
            ):
                status = bridge.process_current_selection(
                    "wl-paste", "xclip", 1024, digest_path
                )
            self.assertEqual(status, "xclip-failed")
            self.assertFalse(digest_path.exists())

    def test_event_helper_keeps_standard_input_descriptor_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "stdin-open"
            wl_paste = root / "wl-paste"
            wl_paste.write_text(
                "#!/usr/bin/env python3\n"
                "import os, pathlib, sys\n"
                "os.fstat(0)\n"
                f"pathlib.Path({str(marker)!r}).write_text('open')\n"
                "if '--list-types' in sys.argv:\n"
                "    print('text/plain')\n"
            )
            wl_paste.chmod(0o700)
            xclip = root / "xclip"
            xclip.write_text("#!/bin/sh\nexit 0\n")
            xclip.chmod(0o700)
            environment = os.environ.copy()
            environment.update(
                {
                    "PATH": f"{root}:{environment['PATH']}",
                    "DISPLAY": ":99",
                    "WAYLAND_DISPLAY": "wayland-test",
                    "XDG_RUNTIME_DIR": str(root),
                }
            )
            result = subprocess.run(
                [sys.executable, SCRIPT, "--event"],
                input=b"watch payload that must be detached",
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(), "open")

    def test_once_returns_failure_for_failed_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = (Path(directory) / "digest", Path(directory) / "lock")
            with (
                mock.patch.object(bridge, "runtime_paths", return_value=paths),
                mock.patch.object(
                    bridge,
                    "process_current_selection",
                    return_value="xclip-failed",
                ),
            ):
                self.assertEqual(bridge.once_main("wl-paste", "xclip", 1024), 1)

    def test_once_returns_success_only_after_fresh_transfer(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = (Path(directory) / "digest", Path(directory) / "lock")
            paths[0].write_text("00" * 32)

            def fresh_transfer(*_args):
                self.assertFalse(paths[0].exists())
                return "mirrored"

            with (
                mock.patch.object(bridge, "runtime_paths", return_value=paths),
                mock.patch.object(
                    bridge,
                    "process_current_selection",
                    side_effect=fresh_transfer,
                ),
            ):
                self.assertEqual(bridge.once_main("wl-paste", "xclip", 1024), 0)


if __name__ == "__main__":
    unittest.main()
