"""Measure what a weight read costs when it comes off storage, on this machine.

Why
---
Every speed figure this repository publishes is a memory roofline: decoding a
token means reading the active weights out of memory once, so throughput is
bounded by memory bandwidth. Layer-by-layer inference -- what `airllm` does,
and what `ai_bunker/fallback.py` sizes -- moves that read to **storage**. The
roofline is the same arithmetic over a different device, and the device is
between one and three orders of magnitude slower.

So the one number that decides whether a model too large for a machine is
worth running at all is the machine's **uncached sequential read bandwidth**,
and it is not a number to assume. Vendor figures are peak, queue-depth-32,
compression-friendly marketing; a laptop with a full disk, a thermally
throttled controller or an external enclosure can be five times slower. This
measures it.

How it avoids measuring the wrong thing
---------------------------------------
Reading a file you just wrote measures the page cache -- gigabytes per second
of memory copy, which is precisely the device that was too small. So the read
bypasses the cache: ``F_NOCACHE`` on macOS, ``O_DIRECT`` on Linux. When
neither is available the script says so and refuses to print a figure, rather
than printing the page cache's bandwidth under a storage label.

It also reports the **cached** rate, because that one matters too: if free
memory can hold part of the model, those layers are read at memory speed and
only the rest pays the storage price. `fallback.py` mixes the two.

Usage
-----
    python scripts/bench_disk.py                     # ~20 s, 2 GiB of scratch
    python scripts/bench_disk.py --size-gib 8        # longer, steadier
    python scripts/bench_disk.py --path /Volumes/ext # measure another device
    python scripts/bench_disk.py --json

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

GIB = 1024**3

#: Read size per call. Layer shards are read whole and sequentially, so a large
#: block is the honest analogue; it is also what keeps the syscall count from
#: becoming the thing being measured. O_DIRECT needs it aligned, which it is.
BLOCK = 8 * 1024 * 1024

#: Spread above this fraction of the median means the machine was busy. Same
#: threshold and same reason as `bench_context.py`: a figure from a machine
#: that was also doing something else should be reported as uncertain rather
#: than printed as fact.
NOISE_FRACTION = 0.15


def _open_uncached(path: Path) -> tuple[int, str]:
    """Open ``path`` for reading with the page cache out of the way.

    Returns
    -------
    (fd, how)
        ``how`` is ``"F_NOCACHE"``, ``"O_DIRECT"`` or ``"cached"`` -- and a
        caller that gets ``"cached"`` must not report its figure as storage
        bandwidth.
    """
    direct = getattr(os, "O_DIRECT", 0)
    if direct:
        try:
            return os.open(str(path), os.O_RDONLY | direct), "O_DIRECT"
        except OSError:
            pass  # some filesystems refuse it; fall through to the generic path

    fd = os.open(str(path), os.O_RDONLY)
    return (fd, "F_NOCACHE") if _set_nocache(fd) else (fd, "cached")


def _open_uncached_for_write(path: Path) -> tuple[int, str]:
    """Create ``path`` for writing without populating the page cache."""
    direct = getattr(os, "O_DIRECT", 0)
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if direct:
        try:
            return os.open(str(path), flags | direct), "O_DIRECT"
        except OSError:
            pass
    fd = os.open(str(path), flags)
    _set_nocache(fd)
    return fd, "F_NOCACHE"


def _set_nocache(fd: int) -> bool:
    """Ask the kernel to keep this descriptor's pages out of the cache."""
    if os.name != "posix":
        return False
    try:
        import fcntl
    except ImportError:
        return False
    nocache = getattr(fcntl, "F_NOCACHE", None)
    if nocache is None:
        return False
    try:
        fcntl.fcntl(fd, nocache, 1)
    except OSError:
        return False
    return True


def _fullsync(fd: int) -> None:
    """Flush to the medium, not merely to the drive's own write cache."""
    try:
        import fcntl

        full = getattr(fcntl, "F_FULLFSYNC", None)
        if full is not None:
            fcntl.fcntl(fd, full)
            return
    except (ImportError, OSError):
        pass
    os.fsync(fd)


def _read_through(fd: int, size: int) -> float:
    """Read ``size`` bytes from the start of ``fd``; return seconds elapsed."""
    os.lseek(fd, 0, os.SEEK_SET)
    # Aligned buffer, so the same loop works under O_DIRECT.
    buffer = bytearray(BLOCK)
    view = memoryview(buffer)
    remaining = size
    start = time.perf_counter()
    while remaining > 0:
        got = os.preadv(fd, [view], size - remaining) if hasattr(os, "preadv") else None
        if got is None:
            got = len(os.read(fd, BLOCK))
        if got <= 0:
            break
        remaining -= got
    return time.perf_counter() - start


def measure(path: Path, size_gib: float, repeats: int) -> dict[str, object]:
    """Write a scratch file, read it uncached and cached, and report both."""
    size = int(size_gib * GIB)
    scratch = path / f"ai-bunker-bench-{os.getpid()}.bin"
    chunk = os.urandom(BLOCK)  # incompressible: a transparently compressing
    try:  # filesystem must not be able to cheat
        # The write has to miss the cache too. `F_NOCACHE` on the reading
        # descriptor stops *new* pages being cached; it does not evict the ones
        # the write just put there, and a 2 GiB file on a 96 GiB machine stays
        # resident. Measured on exactly that machine: cached writes gave a
        # 13.1 GB/s "uncached" read, above what the drive can physically do,
        # against 5.1 GB/s once the write bypassed the cache as well.
        fd, _how = _open_uncached_for_write(scratch)
        try:
            written = 0
            while written < size:
                written += os.write(fd, chunk)
            _fullsync(fd)
        finally:
            os.close(fd)

        fd, how = _open_uncached(scratch)
        try:
            cold = [size / _read_through(fd, size) for _ in range(repeats)]
        finally:
            os.close(fd)

        fd = os.open(str(scratch), os.O_RDONLY)
        try:
            _read_through(fd, size)  # prime the cache, then measure it
            warm = [size / _read_through(fd, size) for _ in range(repeats)]
        finally:
            os.close(fd)
    finally:
        scratch.unlink(missing_ok=True)

    return {
        "path": str(path),
        "size_gib": size_gib,
        "repeats": repeats,
        "how": how,
        "uncached_gbs": [round(r / 1e9, 2) for r in cold],
        "cached_gbs": [round(r / 1e9, 2) for r in warm],
        "uncached_median_gbs": round(statistics.median(cold) / 1e9, 2),
        "cached_median_gbs": round(statistics.median(warm) / 1e9, 2),
        "platform": platform.platform(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=None, help="Directory to write the scratch file in.")
    parser.add_argument("--size-gib", type=float, default=2.0)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    where = Path(args.path or tempfile.gettempdir())
    free = os.statvfs(where)
    need = args.size_gib * GIB * 1.2
    if free.f_bavail * free.f_frsize < need:
        print(f"Not enough free space in {where} for a {args.size_gib} GiB scratch file.")
        return 2

    result = measure(where, args.size_gib, args.repeats)
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    cold = result["uncached_gbs"]
    warm = result["cached_gbs"]
    spread = (max(cold) - min(cold)) / result["uncached_median_gbs"]

    print(f"  {result['platform']}")
    print(f"  {where}  ·  {args.size_gib} GiB  ·  {args.repeats} reads  ·  {result['how']}")
    print("")
    print(f"  uncached read   {result['uncached_median_gbs']:>7.2f} GB/s   {cold}")
    print(f"  cached read     {result['cached_median_gbs']:>7.2f} GB/s   {warm}")
    print("")

    if result["how"] == "cached":
        print("  ⚠  This platform offered neither F_NOCACHE nor O_DIRECT, so the")
        print("     'uncached' figure is the page cache and is NOT storage bandwidth.")
        print("     Do not pass it to `ai-bunker fallback --disk`.")
        return 1
    if spread > NOISE_FRACTION:
        print(f"  ⚠  Spread is {spread:.0%} of the median; the machine was busy.")
        print("     Re-run on an idle machine before quoting the figure.")

    print(f"  Use it:  ai-bunker fallback --disk {result['uncached_median_gbs']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
