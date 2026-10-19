"""
Count what a session really costs, with the server's own tokenizer.

A coding agent's context window has a **floor**: the part paid on every single
request and that no compaction can reduce -- the system prompt, the tool
schemas, the charter, the knowledge index. Whatever is left is the only room
the conversation has to work in.

Clients get this wrong in both directions and the errors are expensive:

- A client *estimating* its own token count under-counts. One measured incident:
  a session believed it was under a 32,768-token limit and sent 40,433. The
  server counted for real, refused the whole request, and the session died. The
  gap was 55%, on French and on code, where client-side heuristics are weakest.
- A client can also be *silently* over the floor. Another measured incident: an
  agent harness injected 59 locally-installed skill descriptions into every
  system prompt -- 17,754 tokens, 68% of a 26,226-token floor against a declared
  context of 26,000. Compaction fired on turn one, had nothing to compact (a
  floor is not in the conversation), and the session looped
  `build -> compact -> build` forever, returning 8 tokens per turn. Nothing in
  the harness said a word.

The second failure is the reason this module exists. It is invisible to
inspection and obvious to measurement. So: measure, attribute every token to
the component that caused it, and **refuse to serve** a configuration that
leaves no room to work.

Three counting backends, in descending order of trust, and the result always
says which one was used:

1. ``server`` -- the serving engine's own ``/tokenize`` endpoint. Exact, and
   the only count that can refuse a request.
2. ``local`` -- the same tokenizer loaded in-process via ``tokenizers``. Exact
   for the model, but a different process than the one that will serve.
3. ``ratio`` -- characters divided by a measured characters-per-token figure.
   An estimate, labelled as one, never silently.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import os_helper as osh

#: Tokens that must remain free for the conversation itself, once the floor,
#: the compaction margin and the maximum output are all paid. Below this a
#: session cannot work: it compacts in a loop or gets refused outright. The
#: figure comes from the incident above, where the usable remainder reached
#: zero while every individual setting still looked reasonable.
MIN_WORKING_TOKENS = 5000

#: Fraction of the served context to declare to clients. A client that
#: estimates its own tokens under-counts; this margin absorbs the gap.
DECLARED_FRACTION = 0.80

#: Characters per token, measured on French and English technical prose with a
#: Mistral-family tokenizer. Used only by the ``ratio`` backend, and only when
#: no real tokenizer is reachable.
CHARS_PER_TOKEN = 4.0

#: The GPU is shared and sometimes saturated: a trivial /tokenize call has been
#: observed taking 20 seconds. Waiting beats returning an estimate.
TOKENIZE_TIMEOUT = 120

Backend = Literal["server", "local", "ratio"]


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------


class Counter:
    """Counts tokens, and is honest about how.

    Parameters
    ----------
    base_url : str, optional
        An OpenAI-compatible server root. When reachable, its ``/tokenize``
        endpoint is used -- the only count that can actually refuse a request.
    model : str, optional
        Model name to tokenize against. Required by the server backend.
    allow_ratio : bool
        When True (the default), fall back to a characters-per-token estimate
        if no real tokenizer is reachable. Set False to make an unavailable
        tokenizer an error instead: a deployment gate should not pass on an
        estimate.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        *,
        allow_ratio: bool = True,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.allow_ratio = allow_ratio
        self._local: Any = None
        self.backend: Backend = self._pick_backend()

    # -- backend selection ------------------------------------------------

    def _tokenize_root(self) -> str:
        """``/tokenize`` lives at the server root, not under ``/v1``."""
        root = self.base_url
        return root[: -len("/v1")] if root.endswith("/v1") else root

    def _server_works(self) -> bool:
        if not self.base_url or not self.model:
            return False
        try:
            return self._count_server("ping") > 0
        except Exception as exc:  # any failure here means "unusable", not "crash"
            osh.debug(f"Server tokenizer unavailable ({exc}); trying local.")
            return False

    def _load_local(self) -> bool:
        """Load the model's tokenizer in-process, if `tokenizers` is installed."""
        if not self.model:
            return False
        try:
            from tokenizers import Tokenizer  # optional extra, imported lazily
        except ImportError:
            osh.debug("`tokenizers` not installed; install ai-bunker[tokenizers].")
            return False
        try:
            self._local = Tokenizer.from_pretrained(self.model)
            return True
        except Exception as exc:
            osh.debug(f"Could not load a local tokenizer for {self.model!r} ({exc}).")
            return False

    def _pick_backend(self) -> Backend:
        if self._server_works():
            return "server"
        if self._load_local():
            return "local"
        osh.check(
            self.allow_ratio,
            "No tokenizer available and estimates are disallowed. Start the "
            "server, or `pip install ai-bunker[tokenizers]`, or pass "
            "allow_ratio=True to accept a labelled estimate.",
        )
        osh.warning(
            "Counting tokens by a characters-per-token ratio. This is an "
            "ESTIMATE: it is exactly the kind of figure that let a client send "
            "40,433 tokens to a 32,768-token server. Treat the result as "
            "indicative, not as a gate."
        )
        return "ratio"

    # -- counting ---------------------------------------------------------

    def _count_server(self, text: str) -> int:
        """Ask the serving engine to count.

        Uses ``httpx`` when it is installed and ``urllib`` otherwise. Not
        indifference: the gateway speaks httpx everywhere else, and a counter
        that reaches the network by a different route than the rest of the
        process is a counter that cannot be exercised by the same test
        harness -- which is how the "exact" path in the gateway went
        unverified long enough to ship broken.
        """
        url = f"{self._tokenize_root()}/tokenize"
        body = {"model": self.model, "prompt": text}
        try:
            import httpx  # optional: part of the [api] extra

            response = httpx.post(url, json=body, timeout=TOKENIZE_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
        except ImportError:
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=TOKENIZE_TIMEOUT) as response:
                payload = json.load(response)
        # vLLM returns {"count": n, "tokens": [...]}; be tolerant of either.
        if "count" in payload:
            return int(payload["count"])
        return len(payload.get("tokens", []))

    def count(self, text: str) -> int:
        """Token count for ``text`` using this counter's backend."""
        if not text:
            return 0
        if self.backend == "server":
            return self._count_server(text)
        if self.backend == "local":
            return len(self._local.encode(text).ids)
        return max(1, round(len(text) / CHARS_PER_TOKEN))

    @property
    def exact(self) -> bool:
        """Whether this count can be trusted to refuse a request."""
        return self.backend != "ratio"


# ---------------------------------------------------------------------------
# Attribution
# ---------------------------------------------------------------------------


@dataclass
class Item:
    """One component of the floor, with what it costs and who caused it."""

    name: str
    owner: str
    tokens: int
    chars: int

    @property
    def share(self) -> float:  # filled in by Budget.render
        return 0.0


@dataclass
class Budget:
    """What a session costs before it has done any work."""

    backend: Backend
    exact: bool
    model: str | None
    items: list[Item]
    floor_tokens: int
    served_context: int
    declared_context: int
    compaction_reserve: int
    max_output: int
    compaction_starts_at: int
    working_tokens: int
    verdict: Literal["ok", "tight", "unusable"]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["items"] = [asdict(i) for i in self.items]
        return d

    @property
    def biggest(self) -> Item | None:
        """The component to attack first."""
        return max(self.items, key=lambda i: i.tokens) if self.items else None


# Known tool-schema owners, so a report can name the harness rather than say
# "something sent 3,164 tokens of JSON".
_SKILL_BLOCK = re.compile(r"<skill>[\s\S]*?</skill>")
_SKILL_NAME = re.compile(r"<name>")


def split_system(
    text: str, charter: str | None = None, index: str | None = None
) -> list[tuple[str, str, str]]:
    """Attribute each slice of a system prompt to its author.

    Attribution is the point. A floor nobody can decompose is a floor nobody
    can reduce, and the measured incident that motivates this module was
    invisible precisely because the harness reported one opaque total.

    Skill blocks are recognised by their tags, the charter and the knowledge
    index by their own leading text; whatever remains belongs to the client.
    The slices are disjoint and their concatenation is the whole prompt, so the
    itemised counts add up to the floor rather than approximating it.

    Returns
    -------
    list of (name, owner, body)
        One entry per attributed slice, in no particular order. Empty slices
        are omitted.
    """
    slices: list[tuple[str, str, str]] = []
    rest = text

    start = rest.find("<skill>")
    end = rest.rfind("</skill>")
    if start != -1 and end > start:
        stop = end + len("</skill>")
        block = rest[start:stop]
        count = len(_SKILL_NAME.findall(block))
        slices.append((f"agent skills ({count})", "client", block))
        rest = rest[:start] + rest[stop:]

    for label, body in (("charter", charter), ("knowledge index", index)):
        if not body:
            continue
        head = body.strip()[:200]
        if not head or head not in rest:
            continue
        at = rest.find(head)
        # Take exactly the known body, so the slice is the file and not
        # whatever happened to follow it in the prompt.
        taken = rest[at : at + len(body)]
        slices.append((label, "ai-bunker", taken))
        rest = rest[:at] + rest[at + len(body) :]

    if rest.strip():
        slices.append(("client system prompt", "client", rest))
    return [(n, o, b) for n, o, b in slices if b]


def measure_request(
    request: dict[str, Any],
    *,
    counter: Counter,
    served_context: int,
    charter: str | None = None,
    knowledge_index: str | None = None,
    compaction_reserve: int = 0,
    max_output: int = 4096,
    declared_context: int | None = None,
    min_working: int = MIN_WORKING_TOKENS,
) -> Budget:
    """Measure the floor of one captured OpenAI-format request.

    Only the system messages and the tool schemas are the floor. User and
    assistant turns are conversation, which compaction *can* reduce, so
    counting them here would hide the problem this module exists to find.

    Parameters
    ----------
    request : dict
        A request body as a client sends it: ``messages``, ``tools``.
    counter : Counter
        The token counter. Its backend is recorded in the result, because a
        number's trustworthiness is part of the number.
    served_context : int
        What the engine actually serves (vLLM's ``--max-model-len``).
    charter, knowledge_index : str, optional
        ai-bunker's own contributions, passed so they are attributed rather
        than lumped into the client's prompt. A deployment should be able to
        see what its own guardrails cost.
    compaction_reserve : int
        Tokens the client keeps free as a compaction margin.
    max_output : int
        Maximum completion length the client will request. Recorded for the
        report; it does not reduce conversation space, because it is covered by
        the gap between the declared and the served context.
    declared_context : int, optional
        What the client is told its window is. Defaults to
        ``served_context * DECLARED_FRACTION``.
    min_working : int
        Conversation space below which the verdict is ``unusable``.

    Returns
    -------
    Budget
        The itemised floor, the remaining working space, and the verdict.
    """
    messages = request.get("messages") or []
    tools = request.get("tools") or []

    items: list[Item] = []

    # Tool schemas come first because they are usually the largest line item
    # and because no client ever shows them to anyone.
    if tools:
        blob = json.dumps(tools, ensure_ascii=False)
        items.append(Item(f"tool schemas ({len(tools)})", "client", counter.count(blob), len(blob)))

    system_text = "\n".join(
        str(m.get("content") or "") for m in messages if m.get("role") == "system"
    )
    for name, owner, body in split_system(system_text, charter, knowledge_index):
        items.append(Item(name, owner, counter.count(body), len(body)))

    floor = sum(i.tokens for i in items)
    declared = int(declared_context or served_context * DECLARED_FRACTION)
    starts_at = max(declared - compaction_reserve, 0)
    working = starts_at - floor

    warnings: list[str] = []

    if declared >= served_context:
        warnings.append(
            f"Declared context ({declared:,}) is not below the served context "
            f"({served_context:,}). A client that estimates its own tokens "
            "under-counts, and that margin is the only protection while a turn "
            "grows: this configuration will eventually send more than the "
            "server accepts, and the server refuses whole requests."
        )

    if floor >= starts_at:
        warnings.append(
            f"The floor ({floor:,} tokens) is at or above the compaction "
            f"trigger ({starts_at:,}). Compaction will fire on every turn with "
            "nothing to reduce -- a floor is not in the conversation. Expect a "
            "session that loops and never answers."
        )

    if working < min_working:
        biggest = max(items, key=lambda i: i.tokens, default=None)
        blame = ""
        if biggest and floor:
            blame = (
                f" The largest component is {biggest.name} at "
                f"{biggest.tokens:,} tokens ({biggest.tokens / floor:.0%} of the "
                f"floor, owned by the {biggest.owner}); start there."
            )
        warnings.append(
            f"Only {working:,} tokens are left for the conversation, below the "
            f"{min_working:,} this deployment requires.{blame}"
        )

    if not counter.exact:
        warnings.append(
            "Counted by ratio, not by a tokenizer. This figure cannot gate a "
            "deployment: start the server, or install the `tokenizers` extra."
        )

    verdict: Literal["ok", "tight", "unusable"]
    if working < min_working:
        verdict = "unusable"
    elif working < min_working * 3:
        verdict = "tight"
    else:
        verdict = "ok"

    return Budget(
        backend=counter.backend,
        exact=counter.exact,
        model=counter.model,
        items=sorted(items, key=lambda i: -i.tokens),
        floor_tokens=floor,
        served_context=served_context,
        declared_context=declared,
        compaction_reserve=compaction_reserve,
        max_output=max_output,
        compaction_starts_at=starts_at,
        working_tokens=working,
        verdict=verdict,
        warnings=warnings,
    )


def load_request(path: str | Path) -> dict[str, Any]:
    """Load a captured request body from JSON."""
    p = Path(path)
    osh.check(osh.file_exists(str(p)), f"No captured request at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    osh.check(isinstance(data, dict), f"{p} is not a JSON object")
    return data
