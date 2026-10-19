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
    "__pycache__",
    ".DS_Store",
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
    print(f"{len(pages())} pages: links, hreflang, canonicals and sitemap all check out")

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
