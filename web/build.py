#!/usr/bin/env python3
"""
Assemble the site's pages from one shared shell.

Not a Markdown-to-HTML generator: the pages are written by hand, as asked, and
this only stops the header, the footer and the meta block from drifting apart
across eight files. Change `_nav.html` once rather than eight times.

Each page is a `pages/<name>.<lang>.py` module exposing `TITLE`,
`DESCRIPTION`, `BODY` and optionally `EXTRA_HEAD`. Run from `web/`:

    python3 build.py && npx tailwindcss@3 -i css/tailwind-input.css -o css/app.css --minify
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

BASE = "https://deraison.ai/ai-bunker"
HERE = pathlib.Path(__file__).parent
PAGES = HERE / "pages"

# The shared header and footer live outside the document root so they are not
# mistaken for pages and not uploaded with the site: `../index.html` resolves
# correctly from fr/ and would 404 from the root.
_SHELL_DIR = HERE / "_shell"
SHELL = {
    "en": (
        (_SHELL_DIR / "_nav.html").read_text(encoding="utf-8"),
        (_SHELL_DIR / "_foot.html").read_text(encoding="utf-8"),
    ),
    "fr": (
        (_SHELL_DIR / "_nav.fr.html").read_text(encoding="utf-8"),
        (_SHELL_DIR / "_foot.fr.html").read_text(encoding="utf-8"),
    ),
}


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shell(page, *, slug: str, lang: str) -> str:
    """One page, wrapped in the shared shell."""
    prefix = "../" if lang == "fr" else ""
    here = f"{BASE}/" if slug == "index" else f"{BASE}/{slug}.html"
    if lang == "fr":
        here = f"{BASE}/fr/" if slug == "index" else f"{BASE}/fr/{slug}.html"
    en = f"{BASE}/" if slug == "index" else f"{BASE}/{slug}.html"
    fr = f"{BASE}/fr/" if slug == "index" else f"{BASE}/fr/{slug}.html"

    nav, foot = SHELL[lang]
    for asset in ("fonts/", "css/", "js/", "img/", "favicon", "site.webmanifest"):
        nav = nav.replace(f'"{asset}', f'"{prefix}{asset}')
        foot = foot.replace(f'"{asset}', f'"{prefix}{asset}')

    # The language toggle goes to *this* page in the other language. It used to
    # be written into the shared shell as the other language's homepage, which
    # is right on two pages out of eight and loses the reader's place on the
    # six others -- while the `hreflang` links a dozen lines above have always
    # named the correct counterpart. Telling a crawler more than a reader is
    # backwards, and `fr/sizing.html` has existed the whole time.
    counterpart = "index.html" if slug == "index" else f"{slug}.html"
    nav = nav.replace("{{OTHER_LANG}}", f"{prefix or 'fr/'}{counterpart}")

    return f"""<!doctype html>
<html lang="{lang}" data-color-scheme="light">

<head>
  <script>(function () {{
      var s; try {{ s = localStorage.getItem('ai-bunker-theme'); }} catch (e) {{ }}
      if (!s) s = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      document.documentElement.setAttribute('data-color-scheme', s);
    }})();</script>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">

  <title>{page.TITLE}</title>
  <meta name="description" content="{page.DESCRIPTION}">
  <link rel="canonical" href="{here}">
  <link rel="alternate" hreflang="en" href="{en}">
  <link rel="alternate" hreflang="fr" href="{fr}">
  <link rel="alternate" hreflang="x-default" href="{en}">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <meta name="theme-color" content="#FFFFFF" media="(prefers-color-scheme: light)">
  <meta name="theme-color" content="#0B0B0C" media="(prefers-color-scheme: dark)">

  <meta property="og:type" content="website">
  <meta property="og:site_name" content="ai-bunker">
  <meta property="og:title" content="{page.TITLE}">
  <meta property="og:description" content="{page.DESCRIPTION}">
  <meta property="og:url" content="{here}">
  <meta property="og:image" content="{BASE}/img/og.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="ai-bunker — one GPU, one charter, every coding agent">
  <meta property="og:locale" content="{"fr_FR" if lang == "fr" else "en_US"}">
  <meta property="og:locale:alternate" content="{"en_US" if lang == "fr" else "fr_FR"}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{page.TITLE}">
  <meta name="twitter:description" content="{page.DESCRIPTION}">
  <meta name="twitter:image" content="{BASE}/img/og.png">
{getattr(page, "EXTRA_HEAD", "")}
  <link rel="icon" href="{prefix}favicon.ico" sizes="any">
  <link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png">
  <link rel="manifest" href="{prefix}site.webmanifest">
  <meta name="apple-mobile-web-app-title" content="ai-bunker">
  <link rel="stylesheet" href="{prefix}fonts/roboto/fonts.css">
  <link rel="stylesheet" href="{prefix}fonts/roboto-serif/fonts.css">
  <link rel="stylesheet" href="{prefix}fonts/roboto-mono/fonts.css">
  <link rel="stylesheet" href="{prefix}css/app.css">
</head>

<body class="bg-white text-neutral-900 dark:bg-[#0B0B0C] dark:text-neutral-100 font-sans antialiased">
  <a href="#main"
    class="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-3 focus:left-3 focus:rounded-lg focus:bg-brand-blue focus:px-4 focus:py-2 focus:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-blue">{"Aller au contenu" if lang == "fr" else "Skip to content"}</a>

{nav}
  <main id="main">
{page.BODY}
  </main>

{foot}
  <script src="{prefix}js/theme.js" defer></script>
  <script src="{prefix}js/nav.js" defer></script>
</body>

</html>
"""


def main() -> int:
    if not PAGES.is_dir():
        print("no pages/ directory", file=sys.stderr)
        return 1
    written = 0
    for source in sorted(PAGES.glob("*.py")):
        slug, _, lang = source.stem.rpartition(".")
        if not slug:
            continue
        page = load(source)
        out = HERE / ("fr" if lang == "fr" else ".") / f"{slug}.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(shell(page, slug=slug, lang=lang), encoding="utf-8")
        print(f"  {out.relative_to(HERE)}")
        written += 1
    print(f"{written} page(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
