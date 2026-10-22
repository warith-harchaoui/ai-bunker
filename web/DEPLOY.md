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

## The check after uploading

```bash
python3 ../scripts/verify_deployment.py          # or --quiet for the drift only
```

Everything above this line checks the *tree*. This one checks the *server*, and
it is the only check here that can tell you the upload did not happen: it asks
production for each of the 38 files `publish.py` would send and compares the
bytes. Exit zero means production is the repository.

It takes its file list from `publish.py`'s own `shipped()` rather than globbing,
and that is load-bearing. The hand check this replaced filtered by extension
and was wrong both ways — it missed `js/theme.js`, `js/nav.js` and the six
fonts, and counted five `_shell/` partials that are never served.

Three things it deliberately does:

- **Never reports drift on one request.** `Cache-Control: no-cache` is only a
  hint and this host ignores it: `deraison.ai` is behind Varnish, which drops
  a client's cache-control by design. So a mismatch is re-fetched with a unique
  query string, which changes the cache key and reaches the origin. If the
  origin agrees with the repository the upload was fine and the edge is merely
  behind — reported as `edge-stale`, which exits **zero**, because re-uploading
  is exactly the wrong thing to do about it.
- **Separates `unreachable` from `missing`.** A timeout means the check did not
  happen; a 404 means the upload did not. Calling the first one "missing" would
  blame the deployment for the network.
- **Retries once**, because refusing the cache makes every page an origin hit —
  measured at 25s cold against 2–4s warm on this host, so the first version
  reported eight pages unreachable on a site that was serving them fine.

What it **cannot** do: find files on the server that the repository does not
list. The HyperText Transfer Protocol (HTTP) cannot enumerate a directory, so
a superseded image left behind by an earlier upload stays invisible — `img/dashboard.png` was found by
remembering it, which is not a check. Deleting those stays a manual job.

## Writing a page

One module per page and per language in `pages/<slug>.<lang>.py`, exposing
`TITLE`, `DESCRIPTION`, `BODY` and optionally `EXTRA_HEAD`. The shell —
meta tags, the JSON-LD wrapper (JavaScript Object Notation for Linked Data),
header, footer, theme script — is shared, so the
header is edited once rather than eight times.

The pages are **written by hand**, not generated from the Markdown. That is a
deliberate choice and it carries a risk: the figures quoted here
(27 rules, 218 assertions) can drift from the repository. `tests/test_site.py`
asserts they match.

The **test count is deliberately not on the site**. It changes on every commit
that adds a test, so quoting it made the deployment stale after every commit
and bought nothing: "a green continuous-integration (CI) gate" is the claim a
reader cares about, and it does not rot. `README.md` and `LISEZMOI.md` still
carry the number, where correcting it costs no upload.
