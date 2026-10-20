# Deploying the site

The site lives at **https://deraison.ai/ai-bunker** — a path on an existing
host, not its own root. Two consequences are already baked in: every asset
reference is relative, and `robots.txt` says explicitly that it is not the
authoritative one (the host's is).

## What to upload

Everything **except** the four build-time directories:

```
_shell/          the shared header and footer, assembled into each page
pages/           the page sources
build.py         the assembler
tailwind.config.js
css/tailwind-input.css
DEPLOY.md        this file
```

`make publish` below writes a clean tree so you do not have to remember.

## Rebuilding

```bash
cd web
python3 build.py                                     # pages from pages/*.py
npx tailwindcss@3 -i css/tailwind-input.css \
                  -o css/app.css --minify            # the stylesheet
python3 ../scripts/lint_a11y.py index.html           # per page
```

`css/app.css` is **committed** on purpose: deployment is a file upload, and
requiring a Node toolchain on the far end would make the site undeployable by
the person who owns it.

## Checks before uploading

```bash
python3 publish.py --check        # links, hreflang, canonicals, asset depth
```

It refuses to assemble a tree when a local link does not resolve, because a
404 discovered after upload costs a round trip through someone else's SFTP —
the SSH File Transfer Protocol, SSH being Secure Shell.

## Writing a page

One module per page and per language in `pages/<slug>.<lang>.py`, exposing
`TITLE`, `DESCRIPTION`, `BODY` and optionally `EXTRA_HEAD`. The shell —
meta tags, the JSON-LD wrapper (JavaScript Object Notation for Linked Data),
header, footer, theme script — is shared, so the
header is edited once rather than eight times.

The pages are **written by hand**, not generated from the Markdown. That is a
deliberate choice and it carries a risk: the figures quoted here (881 tests,
25 rules, 198 assertions) can drift from the repository. `tests/test_site.py`
asserts they match.
