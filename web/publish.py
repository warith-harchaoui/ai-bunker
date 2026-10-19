#!/usr/bin/env python3
"""
Assemble the uploadable tree, after checking it.

The site is deployed by hand over SFTP, so the expensive mistake is a broken
link discovered after the upload. This refuses to produce a tree when one
exists, rather than producing a tree that looks fine.

    python3 publish.py --check          # verify only
    python3 publish.py --out ../dist    # verify, then copy what should ship
"""

from __future__ import annotations

import argparse
import contextlib
import pathlib
import re
import shutil
import sys

HERE = pathlib.Path(__file__).parent
BASE = "https://deraison.ai/ai-bunker"

#: Build-time only. Everything else in web/ is served.
EXCLUDE = {
    "_shell",
    "pages",
    "build.py",
    "publish.py",
    "DEPLOY.md",
    "tailwind.config.js",
    "tailwind-input.css",
    "__pycache__",
    ".DS_Store",
    # The source sizes the multi-resolution favicon.ico was built from. Kept
    # so it can be rebuilt; not served, because nothing links them.
    "favicon-16.png",
    "favicon-32.png",
    "favicon-48.png",
}


def pages() -> list[pathlib.Path]:
    return sorted(HERE.glob("*.html")) + sorted((HERE / "fr").glob("*.html"))


def check() -> list[str]:
    """Everything decidable without a browser."""
    problems: list[str] = []

    for page in pages():
        text = page.read_text(encoding="utf-8")
        where = page.relative_to(HERE)
        lang = "fr" if page.parent.name == "fr" else "en"

        if f'<html lang="{lang}"' not in text:
            problems.append(f"{where}: <html lang> is not {lang!r}")
        for tag in (
            'hreflang="en"',
            'hreflang="fr"',
            'property="og:image"',
            'name="description"',
            'rel="canonical"',
        ):
            if tag not in text:
                problems.append(f"{where}: missing {tag}")

        canonical = re.search(r'rel="canonical" href="([^"]+)"', text)
        if canonical:
            url = canonical.group(1)
            if not url.startswith(BASE):
                problems.append(f"{where}: canonical is not under {BASE}")
            elif lang == "fr" and "/fr/" not in url:
                problems.append(f"{where}: French canonical does not point at /fr/")

        title = re.search(r"<title>(.*?)</title>", text, re.S)
        if not title or not title.group(1).strip():
            problems.append(f"{where}: empty <title>")

        for href in re.findall(r'(?:href|src)="(?!https?:|#|mailto:|data:)([^"#?]+)', text):
            if not (page.parent / href).resolve().exists():
                problems.append(f"{where}: dead link {href}")

    listed = {
        u.split("/")[-1] or "index.html"
        for u in re.findall(
            r"<loc>([^<]+)</loc>", (HERE / "sitemap.xml").read_text(encoding="utf-8")
        )
    }
    actual = {p.name for p in pages()}
    for name in sorted(actual - listed):
        problems.append(f"sitemap.xml: {name} is not listed")

    if not (HERE / "css" / "app.css").stat().st_size:
        problems.append("css/app.css is empty — run the Tailwind build")

    problems += orphans()

    return problems


#: Served because a browser or a crawler asks for them by name, not because a
#: page links to them. Anything else has to be reachable from somewhere.
ENTRY_POINTS = {
    "sitemap.xml",
    "robots.txt",
    "humans.txt",
    "llms.txt",
    "site.webmanifest",
    "favicon.ico",
    "favicon.svg",
    # A font licence ships because the licence says so, not because a page
    # links it.
    "OFL.txt",
}


def shipped() -> list[pathlib.Path]:
    """Every file `--out` would copy."""
    out = []
    for path in sorted(HERE.rglob("*")):
        if path.is_dir() or any(part in EXCLUDE for part in path.relative_to(HERE).parts):
            continue
        out.append(path)
    return out


def orphans() -> list[str]:
    """Files that would be uploaded and that nothing asks for.

    The dead-link check above runs one way: every reference resolves to a file.
    This runs the other way. Both matter, and only one of them is obvious --
    an unreferenced file costs an SFTP upload and never shows a symptom, so it
    accumulates. Three superseded logo exports and a replaced chart were
    sitting in `img/` when this was written.
    """
    referenced: set[pathlib.Path] = set()

    def resolve(base: pathlib.Path, href: str) -> None:
        with contextlib.suppress(OSError, ValueError):
            referenced.add((base / href).resolve())

    for page in pages():
        text = page.read_text(encoding="utf-8")
        for href in re.findall(r'(?:href|src)="(?!https?:|#|mailto:|data:)([^"#?]+)', text):
            resolve(page.parent, href)
        # Social and canonical tags carry absolute URLs; og:image is the one
        # asset on the site that no relative reference ever points at.
        for url in re.findall(rf'"({re.escape(BASE)}/[^"]+)"', text):
            resolve(HERE, url[len(BASE) + 1 :])

    for sheet in HERE.rglob("*.css"):
        if any(part in EXCLUDE for part in sheet.relative_to(HERE).parts):
            continue
        for href in re.findall(
            r"url\(\s*['\"]?(?!https?:|data:)([^)'\"]+)", sheet.read_text(encoding="utf-8")
        ):
            resolve(sheet.parent, href)

    manifest = HERE / "site.webmanifest"
    if manifest.exists():
        for href in re.findall(r'"src"\s*:\s*"([^"]+)"', manifest.read_text(encoding="utf-8")):
            resolve(HERE, href)

    problems = []
    for path in shipped():
        if path.resolve() in referenced or path.name in ENTRY_POINTS or path.suffix == ".html":
            continue
        size = path.stat().st_size
        problems.append(
            f"{path.relative_to(HERE)}: nothing references it "
            f"({size / 1024:.0f} KB that would ship anyway)"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify and stop.")
    parser.add_argument("--out", help="Directory to assemble the uploadable tree into.")
    args = parser.parse_args(argv)

    problems = check()
    if problems:
        print(f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print(
        f"{len(pages())} pages, {len(shipped())} files: links, hreflang, canonicals, "
        "sitemap and orphans all check out"
    )

    if args.check or not args.out:
        return 0

    out = pathlib.Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(
        HERE,
        out,
        ignore=lambda _d, names: [n for n in names if n in EXCLUDE],
    )
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"assembled {out} — {len(list(out.rglob('*.html')))} pages, {total / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
