#!/usr/bin/env python3
"""Bridge binary clipboard formats from Wayland to X11 for Wine applications.

The daemon is event-driven via ``wl-paste --watch``. It mirrors copied image
pixels (``image/png``) and copied file lists (``text/uri-list``), while keeping
all payload handling binary-safe and bounded.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time
from typing import Optional

DEFAULT_MAX_BYTES = 256 * 1024 * 1024
MAX_TYPES_BYTES = 64 * 1024
READ_TIMEOUT_SECONDS = 5.0
PRIORITY = ("text/uri-list", "image/png")


def command_path(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"Required command not found: {name}")
    return path


def runtime_paths() -> tuple[Path, Path]:
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return (
        runtime_dir / "affinity-clipboard-bridge.digest",
        runtime_dir / "affinity-clipboard-bridge.lock",
    )


def read_bounded(
    args: list[str],
    max_bytes: int,
    timeout: float = READ_TIMEOUT_SECONDS,
) -> tuple[Optional[bytes], str]:
    """Read command output without allowing unbounded memory growth."""
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    assert process.stdout is not None
    fd = process.stdout.fileno()
    os.set_blocking(fd, False)
    selector = selectors.DefaultSelector()
    selector.register(fd, selectors.EVENT_READ)
    payload = bytearray()
    deadline = time.monotonic() + timeout

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                return None, "timeout"

            events = selector.select(remaining)
            if not events:
                process.kill()
                process.wait()
                return None, "timeout"

            chunk = os.read(fd, min(64 * 1024, max_bytes + 1 - len(payload)))
            if not chunk:
                return_code = process.wait(timeout=max(0.1, remaining))
                if return_code != 0:
                    return None, "read-failed"
                return bytes(payload), "ok"

            payload.extend(chunk)
            if len(payload) > max_bytes:
                process.kill()
                process.wait()
                return None, "too-large"
    finally:
        selector.close()
        process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def get_types(wl_paste: str) -> set[str]:
    payload, status = read_bounded(
        [wl_paste, "--list-types"], MAX_TYPES_BYTES, timeout=2.0
    )
    if status != "ok" or payload is None:
        return set()
    return {
        line.decode("utf-8", "replace").strip()
        for line in payload.splitlines()
        if line.strip()
    }


def normalize_payload(mime: str, payload: bytes) -> Optional[bytes]:
    if mime != "text/uri-list":
        return payload or None

    # Xwayland/Klipper may append another newline whenever a selection crosses
    # the Wayland/X11 boundary. Canonical CRLF keeps the digest stable.
    normalized = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    lines = [
        line.strip()
        for line in normalized.split(b"\n")
        if line.strip() and not line.lstrip().startswith(b"#")
    ]
    if not lines:
        return None
    return b"\r\n".join(lines) + b"\r\n"


def set_x11_clipboard(xclip: str, mime: str, payload: bytes) -> bool:
    result = subprocess.run(
        [xclip, "-selection", "clipboard", "-t", mime, "-in"],
        input=payload,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5.0,
        check=False,
    )
    return result.returncode == 0


def read_cached_digest(path: Path) -> Optional[bytes]:
    try:
        value = bytes.fromhex(path.read_text(encoding="ascii").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None
    return value if len(value) == hashlib.sha256().digest_size else None


def write_cached_digest(path: Path, digest: bytes) -> None:
    temporary = path.with_suffix(f".tmp.{os.getpid()}")
    temporary.write_text(digest.hex(), encoding="ascii")
    os.replace(temporary, path)


def clear_cached_digest(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def process_current_selection(
    wl_paste: str,
    xclip: str,
    max_bytes: int,
    digest_path: Path,
) -> str:
    types = get_types(wl_paste)
    mime = next((candidate for candidate in PRIORITY if candidate in types), None)
    if mime is None:
        clear_cached_digest(digest_path)
        return "no-relevant-format"

    payload, status = read_bounded([wl_paste, "--type", mime], max_bytes)
    if status != "ok" or payload is None:
        return status

    payload = normalize_payload(mime, payload)
    if payload is None:
        return "empty"

    digest = hashlib.sha256(mime.encode() + b"\0" + payload).digest()
    if digest == read_cached_digest(digest_path):
        return "unchanged"

    if not set_x11_clipboard(xclip, mime, payload):
        return "xclip-failed"

    write_cached_digest(digest_path, digest)
    print(f"mirrored {mime}: {len(payload)} bytes", flush=True)
    return "mirrored"


def event_main(max_bytes: int) -> int:
    # wl-paste --watch offers the selected payload on stdin. Detach that pipe so
    # a large selection is not transferred twice, but keep file descriptor 0
    # open: wl-clipboard deliberately aborts when launched with a closed stdio
    # descriptor.
    devnull = os.open(os.devnull, os.O_RDONLY)
    try:
        os.dup2(devnull, sys.stdin.fileno())
    finally:
        if devnull != sys.stdin.fileno():
            os.close(devnull)

    digest_path, lock_path = runtime_paths()
    try:
        wl_paste = command_path("wl-paste")
        xclip = command_path("xclip")
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            status = process_current_selection(
                wl_paste, xclip, max_bytes, digest_path
            )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"clipboard bridge warning: {exc}", file=sys.stderr, flush=True)
        return 0  # Do not terminate the parent wl-paste watcher.

    if status not in {"mirrored", "unchanged", "no-relevant-format"}:
        print(f"clipboard bridge warning: {status}", file=sys.stderr, flush=True)
    return 0


def watch_main(wl_paste: str, max_bytes: int) -> int:
    digest_path, _ = runtime_paths()
    clear_cached_digest(digest_path)
    command = [
        wl_paste,
        "--watch",
        sys.executable,
        str(Path(__file__).resolve()),
        "--event",
        "--max-bytes",
        str(max_bytes),
    ]
    subprocess.run(command, check=False)
    # A watcher is expected to live until systemd stops the cgroup. Any normal
    # return here is unexpected and should trigger Restart=on-failure.
    return 1


def once_main(wl_paste: str, xclip: str, max_bytes: int) -> int:
    digest_path, lock_path = runtime_paths()
    try:
        with lock_path.open("a+b") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            # One-shot mode must verify a real X11 write rather than trusting a
            # digest left by a daemon or an earlier invocation.
            clear_cached_digest(digest_path)
            status = process_current_selection(
                wl_paste, xclip, max_bytes, digest_path
            )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"clipboard bridge error: {exc}", file=sys.stderr)
        return 1

    if status in {"mirrored", "unchanged"}:
        return 0
    print(f"clipboard bridge error: {status}", file=sys.stderr)
    return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="mirror once and exit")
    mode.add_argument("--event", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help=f"maximum payload size (default: {DEFAULT_MAX_BYTES} bytes)",
    )
    args = parser.parse_args()
    if args.max_bytes < 1:
        parser.error("--max-bytes must be positive")
    return args


def main() -> int:
    args = parse_args()
    if not os.environ.get("WAYLAND_DISPLAY"):
        print("WAYLAND_DISPLAY is not set; this bridge requires Wayland", file=sys.stderr)
        return 2
    if not os.environ.get("DISPLAY"):
        print("DISPLAY is not set; no Xwayland display is available", file=sys.stderr)
        return 2

    if args.event:
        return event_main(args.max_bytes)

    try:
        wl_paste = command_path("wl-paste")
        xclip = command_path("xclip")
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 2

    if args.once:
        return once_main(wl_paste, xclip, args.max_bytes)
    return watch_main(wl_paste, args.max_bytes)


if __name__ == "__main__":
    raise SystemExit(main())
