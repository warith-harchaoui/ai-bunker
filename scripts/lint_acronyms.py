"""Refuse any abbreviation the prose has not spelled out before using it.

Why
---
The project's documentation is read by people meeting it for the first time,
and it leans on fifty-odd abbreviations: AP2, JWKS, MoE, VRAM, ReDoS. A reader
who does not know what AP2 stands for cannot evaluate a claim about it, and
sending that reader to a glossary at the bottom of the page is no answer --
the glossary explains the term *after* every sentence that used it, which is
the wrong order, and it costs a round trip through a list nobody enjoys
reading.

So the rule is the stronger one: every abbreviation is spelled out **in place,
at or before its first use in that file**. This checks it, per file and per
language, because a term introduced properly in the English README is still
unexplained for whoever opens the French one.

    python scripts/lint_acronyms.py            # report, exit non-zero on a gap
    python scripts/lint_acronyms.py --list     # the catalogue, as a table

What it does not check
----------------------
Proper names. ``NVIDIA``, ``OpenAI``, ``LiteLLM``, ``NeMo``, ``DGX Spark`` and
``GB10`` are things people named, not initials standing for words, and forcing
an expansion on them would invent one. They are listed in ``NAMES`` so the
exemption is a decision on the record rather than a hole. The prose still
glosses them -- that is a writing job, and no linter can judge it.

Code is not prose either: fenced blocks, inline spans and link targets are
stripped before the check, so a flag like ``--fp8`` or a key like
``AI_BUNKER_HOME`` is not a claim about vocabulary.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import argparse
import html
import pathlib
import re

from ai_bunker.adopt import site_file

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Every prose file that is read by a human, with the language it is written
#: in. A term explained in `README.md` is not explained in `LISEZMOI.md`.
FILES: list[tuple[str, str]] = [
    ("README.md", "en"),
    ("LISEZMOI.md", "fr"),
    ("EXAMPLES.md", "en"),
    ("EXEMPLES.md", "fr"),
    ("LANDSCAPE.md", "en"),
    ("PAYSAGE.md", "fr"),
    ("CONTRIBUTING.md", "en"),
    ("CHANGELOG.md", "en"),
    ("docs/SIZING.md", "en"),
    ("docs/RULES.md", "en"),
    ("docs/REGLES.md", "fr"),
    ("clients/README.md", "en"),
    ("web/DEPLOY.md", "en"),
    ("web/llms.txt", "en"),
    ("web/humans.txt", "en"),
    # The website, checked on the assembled page because that is the thing a
    # reader meets -- a term introduced in the shared header counts. Fixes go
    # into the module named in the report, never into the built file.
    ("web/index.html", "en"),
    ("web/sizing.html", "en"),
    ("web/landscape.html", "en"),
    ("web/start.html", "en"),
    ("web/fr/index.html", "fr"),
    ("web/fr/sizing.html", "fr"),
    ("web/fr/landscape.html", "fr"),
    ("web/fr/start.html", "fr"),
]


def source_of(rel: str) -> str:
    """The editable module behind an assembled page."""
    if not rel.endswith(".html"):
        return rel
    slug = rel.rsplit("/", 1)[-1].removesuffix(".html")
    lang = "fr" if "/fr/" in rel else "en"
    return f"web/pages/{slug}.{lang}.py"


#: Abbreviation -> the spellings that count as having explained it, per
#: language. Several are accepted because prose should not have to match one
#: fixed phrasing: an en dash, a British `-isation`, a plural all read the same
#: to the person the rule is for.
TERMS: dict[str, dict[str, list[str]]] = {
    "A2A": {"en": ["Agent2Agent"], "fr": ["Agent2Agent"]},
    "A2UI": {"en": ["Agent-to-User Interface"], "fr": ["Agent-to-User Interface"]},
    "ACP": {"fr": ["analyse en composantes principales"]},
    "AI": {"en": ["artificial intelligence"], "fr": ["intelligence artificielle"]},
    "AP2": {"en": ["Agent Payments Protocol"], "fr": ["Agent Payments Protocol"]},
    "API": {
        "en": ["application programming interface"],
        "fr": ["interface de programmation"],
    },
    "AWQ4": {
        "en": ["activation-aware weight quantisation", "activation-aware weight quantization"],
        "fr": ["quantification des poids"],
    },
    "AWS": {"en": ["Amazon Web Services"], "fr": ["Amazon Web Services"]},
    "BSD": {"en": ["Berkeley Software Distribution"], "fr": ["Berkeley Software Distribution"]},
    "CDN": {
        "en": ["content delivery network"],
        "fr": ["réseau de diffusion de contenu"],
    },
    "CI": {"en": ["continuous integration"], "fr": ["intégration continue"]},
    "CLI": {
        "en": ["command-line interface"],
        "fr": ["interface en ligne de commande"],
    },
    "CPU": {"en": ["central processing unit"], "fr": ["processeur central"]},
    "CSS": {"en": ["Cascading Style Sheets"], "fr": ["Cascading Style Sheets"]},
    "CUDA": {
        "en": ["Compute Unified Device Architecture"],
        "fr": ["Compute Unified Device Architecture"],
    },
    "DSL": {"en": ["domain-specific language"], "fr": ["langage dédié"]},
    "ECC": {"en": ["error-correcting code"], "fr": ["code correcteur d'erreurs"]},
    "EdDSA": {
        "en": ["Edwards-curve Digital Signature Algorithm"],
        "fr": ["Edwards-curve Digital Signature Algorithm"],
    },
    "FP8": {
        "en": ["8-bit floating point", "floating point on 8 bits"],
        "fr": ["virgule flottante sur 8 bits"],
    },
    "GB": {"en": ["gigabyte"], "fr": ["gigaoctet"]},
    "GDDR7": {
        "en": ["graphics double data rate"],
        "fr": ["graphics double data rate"],
    },
    "GPU": {"en": ["graphics processing unit"], "fr": ["processeur graphique"]},
    "GiB": {"en": ["gibibyte"], "fr": ["gibioctet"]},
    "MiB": {"en": ["mebibyte"], "fr": ["m\u00e9bioctet"]},
    "HTML": {"en": ["HyperText Markup Language"], "fr": ["HyperText Markup Language"]},
    "HTTP": {
        "en": ["HyperText Transfer Protocol"],
        "fr": ["HyperText Transfer Protocol"],
    },
    "ISO": {
        "en": ["International Organization for Standardization"],
        "fr": ["Organisation internationale de normalisation"],
    },
    "JSON": {"en": ["JavaScript Object Notation"], "fr": ["JavaScript Object Notation"]},
    "JWKS": {"en": ["JSON Web Key Set"], "fr": ["JSON Web Key Set"]},
    "JWS": {"en": ["JSON Web Signature"], "fr": ["JSON Web Signature"]},
    "JWT": {"en": ["JSON Web Token"], "fr": ["JSON Web Token"]},
    "KV": {"en": ["key value"], "fr": ["clé valeur"]},
    "KiB": {"en": ["kibibyte"], "fr": ["kibioctet"]},
    "LD": {"en": ["Linked Data"], "fr": ["Linked Data"]},
    "LLM": {"en": ["large language model"], "fr": ["grand modèle de langue"]},
    "MCP": {"en": ["Model Context Protocol"], "fr": ["Model Context Protocol"]},
    "MIT": {
        "en": ["Massachusetts Institute of Technology"],
        "fr": ["Massachusetts Institute of Technology"],
    },
    "MoE": {"en": ["mixture of experts"], "fr": ["mélange d'experts"]},
    "NDA": {"en": ["non-disclosure agreement"], "fr": ["accord de confidentialité"]},
    "OFL": {"en": ["Open Font License"], "fr": ["Open Font License"]},
    "OPA": {"en": ["Open Policy Agent"], "fr": ["Open Policy Agent"]},
    "OTLP": {"en": ["OpenTelemetry Protocol"], "fr": ["OpenTelemetry Protocol"]},
    "OWASP": {
        "en": ["Open Worldwide Application Security Project"],
        "fr": ["Open Worldwide Application Security Project"],
    },
    "PCA": {"en": ["principal component analysis"]},
    "PII": {
        "en": ["personally identifiable information"],
        "fr": ["données personnelles identifiantes"],
    },
    "PNG": {"en": ["Portable Network Graphics"], "fr": ["Portable Network Graphics"]},
    "PS256": {"en": ["probabilistic signature scheme"], "fr": ["probabilistic signature scheme"]},
    "RAM": {"en": ["random-access memory"], "fr": ["mémoire vive"]},
    "ReDoS": {
        "en": ["regular expression denial of service"],
        "fr": ["déni de service par expression régulière"],
    },
    "RS256": {"en": ["Rivest-Shamir-Adleman"], "fr": ["Rivest-Shamir-Adleman"]},
    "ES": {
        "en": ["elliptic curve digital signature algorithm"],
        "fr": ["elliptic curve digital signature algorithm"],
    },
    "PS": {"en": ["probabilistic signature scheme"], "fr": ["probabilistic signature scheme"]},
    "RS": {"en": ["Rivest-Shamir-Adleman"], "fr": ["Rivest-Shamir-Adleman"]},
    "ES256": {
        "en": ["elliptic curve digital signature algorithm"],
        "fr": ["elliptic curve digital signature algorithm"],
    },
    "SaaS": {"en": ["software as a service"], "fr": ["logiciel en tant que service"]},
    "SDK": {"en": ["software development kit"], "fr": ["kit de développement"]},
    "SFTP": {"en": ["SSH File Transfer Protocol"], "fr": ["SSH File Transfer Protocol"]},
    "SSH": {"en": ["Secure Shell"], "fr": ["Secure Shell"]},
    "SSO": {"en": ["single sign-on"], "fr": ["authentification unique"]},
    "SVG": {"en": ["Scalable Vector Graphics"], "fr": ["Scalable Vector Graphics"]},
    "SWE": {"en": ["software engineering"], "fr": ["génie logiciel"]},
    "UCP": {
        "en": ["Universal Commerce Protocol"],
        "fr": ["Universal Commerce Protocol"],
    },
    "URL": {"en": ["uniform resource locator"], "fr": ["adresse web"]},
    "VL": {"en": ["vision-language"], "fr": ["vision-langue"]},
    "VLM": {"en": ["vision-language model"], "fr": ["modèle vision-langue"]},
    "VRAM": {"en": ["video random-access memory"], "fr": ["mémoire vidéo"]},
    "YAML": {
        "en": ["YAML Ain't Markup Language", "configuration file format"],
        "fr": ["YAML Ain't Markup Language", "format de fichier de configuration"],
    },
}

#: Named and coined things, not initials: expanding them would mean inventing
#: an expansion. Kept here so the exemption is visible and arguable.
NAMES = {
    "Agent2Agent",
    "AI",
    "Blackwell",
    "DGX",
    "EXAMPLES",
    "EXEMPLES",
    "HyperText",
    "GB10",
    "GitHub",
    "Grace",
    "HTML5",
    "JavaScript",
    "LANDSCAPE",
    "LICENSE",
    "LangChain",
    "LangGraph",
    "LISEZMOI",  # a filename, like README and PAYSAGE above it
    "LiteLLM",
    "LlamaIndex",
    "ToolHive",
    "Bifrost",
    "MacBook",
    "NVIDIA",
    "NeMo",
    "OpenAI",
    "PyTorch",
    "OpenCode",
    "PAYSAGE",
    "PowerShell",
    "PreToolUse",
    "PRO",
    "README",
    "RTX",
    "SIL",
    "SIZING",
    "SKILL",
    "TruffleHog",
    "Ubuntu",
    "clients",
    "docs",
    "macOS",
    "vLLM",
    # Section markers and severity names, which are literals the project
    # defines rather than abbreviations.
    "BLOCKER",
    "GATED",
    "WARNING",
    "SUGGESTION",
    "TABLE",
    "START",
    "END",
    "FIGURE",
    "TEAM",
    "SITE",
    "NOTE",
    # Literal labels drawn in the figures, and file names the pages show.
    "FLOOR",
    "PLANCHER",
    "AGENTS",
    "CLAUDE",
    "BUY",
    "LOAD",
    "MODEL",
    "WARN",
}

#: Names that happen to contain an abbreviation. "AI Helpers" is a suite and
#: "LLM Guard" a product; neither is the reader being asked to know what the
#: letters stand for, so these spans are blanked before the check runs. The
#: generic use of the same letters, two sentences later, still counts.
NAME_PHRASES = [
    "AI Helpers",
    "Guardrails AI",
    "Kong AI Gateway",
    "LLM Guard",
    "Gemini CLI",
    "Qwen3-VL",
    "SWE-bench",
    "BSD-3-Clause",  # the identifier the license is registered under
]

#: What may stand between two words of a spelled-out phrase: ordinary space, a
#: line break, a non-breaking space, or a dash of any width. "key-value" with a
#: hyphen, the same with an en dash, and "key value" plain are one phrase to the
#: reader this rule exists for -- and a compound adjective, as in "a
#: continuous-integration gate", explains a term exactly as well as two plain
#: words do.
SEP = r"[\s\u00a0\u2010-\u2015-]+"

FENCE = re.compile(r"^(```|~~~)")
INLINE = re.compile(r"`[^`]*`")
TARGET = re.compile(r"https?://\S+|\]\([^)]*\)")

#: Scripts, styles and the document head carry structured data and class
#: names, not sentences.
NOT_PROSE = re.compile(
    r"<script\b.*?</script>|<style\b.*?</style>|<head\b.*?</head>|<svg\b.*?</svg>"
    r"|<pre\b.*?</pre>|<code\b.*?</code>|<!--.*?-->",
    re.S | re.I,
)
#: Where one thought ends, in markup. Headings are deliberately absent: a
#: heading and the block beneath it are one unit, so "<h2>MoE</h2>" followed by
#: "<p>mixture of experts</p>" is a term introduced with its expansion.
BLOCK_END = re.compile(r"</(?:p|li|figcaption|td|th|summary|dt|dd|div)>", re.I)
TAG = re.compile(r"<[^>]+>")


def _blank_names(text: str) -> str:
    """Replace each product name with blanks of the same length.

    Same length because every offset in the flattened text indexes into the
    line and paragraph maps; shortening the string would misreport lines.
    """
    for phrase in NAME_PHRASES:
        text = re.sub(
            SEP.join(re.escape(w) for w in phrase.split()),
            lambda m: " " * len(m.group(0)),
            text,
            flags=re.I,
        )
    return text


class Prose:
    """A file's prose, flattened, with every position traceable to its line.

    Flattened on purpose. The documentation is hard-wrapped at 80 columns, so
    "mixture of experts" is routinely split as "mixture of\nexperts"; a check
    that read one line at a time called that unexplained and would have had
    the prose rewritten to satisfy the checker rather than the reader. The
    line numbers survive the flattening because they are what makes a report
    actionable.
    """

    def __init__(self, path: pathlib.Path) -> None:
        if path.suffix == ".html":
            self._from_markup(path)
            return
        chunks: list[str] = []
        self.lines: list[int] = []  # one line number per character
        self.paras: list[int] = []  # one paragraph index per character
        inside = False
        para = 0
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FENCE.match(line.strip()):
                inside = not inside
                continue
            if inside:
                continue
            if not line.strip():
                para += 1
                continue
            text = TARGET.sub(" ", INLINE.sub(" ", line)) + " "
            chunks.append(text)
            self.lines.extend([n] * len(text))
            self.paras.extend([para] * len(text))
        self.text = _blank_names("".join(chunks))

    def _from_markup(self, path: pathlib.Path) -> None:
        """Same idea for an assembled page: text only, one block one thought.

        Line numbers are kept so a report can point somewhere, even though the
        fix belongs in the page module rather than in the built file.
        """
        chunks: list[str] = []
        self.lines = []
        self.paras = []
        para = 0
        raw = NOT_PROSE.sub(" ", path.read_text(encoding="utf-8"))
        for n, line in enumerate(raw.splitlines(), 1):
            ends = bool(BLOCK_END.search(line))
            text = html.unescape(TAG.sub(" ", line)) + " "
            if text.strip():
                chunks.append(text)
                self.lines.extend([n] * len(text))
                self.paras.extend([para] * len(text))
            if ends or not line.strip():
                para += 1
        self.text = _blank_names("".join(chunks))

    def line_at(self, offset: int) -> int:
        return self.lines[offset]

    def para_at(self, offset: int) -> int:
        return self.paras[offset]


def first_use(prose: Prose, term: str) -> tuple[int, int] | None:
    """The (line, paragraph) where `term` is first used, plural tolerated."""
    pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}s?(?![A-Za-z0-9])")
    match = pattern.search(prose.text)
    if not match:
        return None
    return prose.line_at(match.start()), prose.para_at(match.start())


def first_expansion(prose: Prose, spellings: list[str]) -> tuple[int, int] | None:
    """The (line, paragraph) where the term is first spelled out.

    Whitespace inside the spelling is matched loosely, so a line break in the
    middle of the phrase is not a failure -- the prose is hard-wrapped and
    where a sentence happens to break is not a fact about the vocabulary.
    """
    found = []
    for spelling in spellings:
        pattern = re.compile(SEP.join(re.escape(w) for w in spelling.split()), re.I)
        match = pattern.search(prose.text)
        if match:
            found.append((prose.line_at(match.start()), prose.para_at(match.start())))
    return min(found) if found else None


def _resolve(rel: str) -> pathlib.Path | None:
    """One listed file, or None when it is not on this machine.

    A `web/`-prefixed path follows the site, which now lives outside this
    repository: the spelling stays `web/index.html` because that is what a
    reader of `FILES` recognises and what the site still calls itself
    internally. Everything else is in the repository and resolves against
    `ROOT`.
    """
    if rel.startswith("web/"):
        return site_file(rel)
    path = ROOT / rel
    return path if path.is_file() else None


def gaps() -> list[tuple[str, str, int, int | None]]:
    """Every (file, term, used-on, explained-on) that breaks the rule."""
    out = []
    for rel, lang in FILES:
        path = _resolve(rel)
        if path is None:
            continue
        text = Prose(path)
        for term, by_lang in TERMS.items():
            spellings = by_lang.get(lang)
            if not spellings:
                continue
            used = first_use(text, term)
            if used is None:
                continue
            explained = first_expansion(text, spellings)
            if explained is None or explained[1] > used[1]:
                out.append((rel, term, used[0], explained[0] if explained else None))
    return out


def unknown() -> list[tuple[str, str, int]]:
    """Abbreviations the prose uses that the catalogue has never heard of.

    The catalogue is the weak point of a check like this: a term nobody
    thought to add is a term silently allowed. So the scan runs the other way
    too, over anything carrying two capitals, and anything neither catalogued
    nor named is reported.
    """
    token = re.compile(r"\b(?=[A-Za-z0-9]*[A-Z][A-Za-z0-9]*[A-Z])[A-Za-z][A-Za-z0-9]{1,11}\b")
    out = []
    for rel, _lang in FILES:
        path = _resolve(rel)
        if path is None:
            continue
        text = Prose(path)
        seen: set[str] = set()
        for m in token.finditer(text.text):
            tok = m.group(0)
            bare = tok[:-1] if tok.endswith("s") and tok[:-1] in TERMS else tok
            if bare in TERMS or bare in NAMES or bare in seen:
                continue
            seen.add(bare)
            out.append((rel, bare, text.line_at(m.start())))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--list", action="store_true", help="print the catalogue")
    args = parser.parse_args()

    if args.list:
        for term in sorted(TERMS):
            en = TERMS[term].get("en", ["--"])[0]
            fr = TERMS[term].get("fr", ["--"])[0]
            print(f"{term:8s}  {en:46s}  {fr}")
        print(f"\n{len(TERMS)} abbreviations, {len(NAMES)} names exempt")
        return 0

    bad = gaps()
    strange = unknown()
    for rel, term, used, explained in bad:
        where = f"spelled out only later, on line {explained}" if explained else "never spelled out"
        print(f"{rel}:{used}: {term} used before it is explained — {where}")
        if rel.endswith(".html"):
            print(f"    fix in {source_of(rel)}")
    for rel, term, line in strange:
        print(f"{rel}:{line}: {term} is in neither the catalogue nor NAMES")

    if bad or strange:
        print(f"\n{len(bad)} unexplained use(s), {len(strange)} uncatalogued term(s)")
        return 1
    print(f"every abbreviation is spelled out before use, across {len(FILES)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
