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

#: Characters per token for the ``ratio`` backend, used only when no real
#: tokenizer is reachable.
#:
#: **2.5, not 4.0, and the difference is a safety property rather than a
#: precision one.** `scripts/measure_ratio.py` measures this against thirteen
#: real files from this repository and three tokenizer families, and the true
#: ratio runs from **2.51** (markup) to **4.23** (Python). Dividing by 4.0
#: therefore UNDER-counted most content, by up to 37% on the densest -- and
#: under-counting is the failure this project was founded on: a client that
#: estimated its own tokens and sent 40,433 to a 32,768-token server.
#:
#: An estimate is not advisory here. `Budget.verdict` is computed whatever the
#: backend and the gateway returns 413 on ``unusable``, so this figure can
#: refuse a request. A number that can refuse must never be optimistic, which
#: means taking the measured FLOOR rather than the mean.
#:
#: The cost is stated rather than hidden: at 2.5 the estimate over-counts
#: English prose by about 50%, so an unknown model may be told it has less room
#: than it does. That is the recoverable direction -- it produces a refusal that
#: names its own pessimism and the remedy -- and it is now the rare case, since
#: `Counter` resolves a real tokenizer for every family the catalogue knows.
#:
#: Re-measure with `python3 scripts/measure_ratio.py --check` after changing
#: this or adding a family.
CHARS_PER_TOKEN = 2.5

#: The GPU is shared and sometimes saturated: a trivial /tokenize call has been
#: observed taking 20 seconds. Waiting beats returning an estimate.
TOKENIZE_TIMEOUT = 120

#: And a much shorter one for the PROBE, which is a different question.
#:
#: `_server_works` asks each dialect to tokenize the word "ping". That is a
#: liveness check, not a measurement, and it should answer in milliseconds on
#: any engine that answers at all. Giving it the counting timeout meant three
#: dialects x 120 seconds = **six minutes** of a stalled engine before the
#: gateway fell back -- and the call is synchronous inside an async handler,
#: so for that whole time the event loop serves nobody.
#:
#: Measured against a `/tokenize` that sleeps six seconds: the first request
#: took 18 seconds, three probes deep, before this was separated.
#:
#: An engine that cannot tokenize "ping" in five seconds is an engine this
#: should stop waiting for and label an estimate, which is the honest answer
#: and the fast one.
PROBE_TIMEOUT = 5

#: The largest request this gateway will *look at*, as characters per token of
#: served context. Deliberately absurd: the measured floor is
#: :data:`CHARS_PER_TOKEN` = 2.5, so a request at this ceiling is about
#: thirteen times larger than the biggest one that could ever fit the engine.
#:
#: It exists because screening is linear in the length of what arrives and
#: nothing else bounded the total. :data:`~ai_bunker.rules.MAX_SCREEN_CHARS`
#: bounds a *slice*; a tool result arrives in as many slices as its length
#: requires. One 40 MB tool result -- a tool that read a large file, no
#: hostility required -- costs minutes of a synchronous screen inside an
#: asynchronous handler, during which the gateway serves nobody, and is then
#: forwarded to an engine that will refuse it for context length anyway.
#:
#: Note what this is *not*: it is not the budget verdict arriving earlier.
#: `measure_request` counts the system messages and the tool schemas, because
#: conversation is what compaction reduces -- so a request can be enormous,
#: pass the budget, and be forwarded. This is a separate, stated bound of the
#: same kind as `MAX_SCREEN_CHARS`, the breaker's 4,096 sessions and the 512
#: tool pins: a published ceiling, not an inference about something else.
#:
#: Thirty-two rather than, say, four, because refusing a request that would
#: have fitted is the worse failure. Real tokenizers run 2 to 6 characters per
#: token on real text; long runs of one character can push a byte-pair encoder
#: higher, and nobody should have to think about which side of this line their
#: build log falls on.
CEILING_CHARS_PER_TOKEN = 32


def request_chars(request: Any) -> int:
    """Every character a request body carries, keys included.

    Iteratively, which is the point: a recursive walk over a request is a
    stack whose depth the caller chooses, and the whole reason this function
    exists is that a caller was choosing something unbounded. Two thousand
    levels of nesting cost two thousand list entries here and no frames.

    Keys are counted with values. They are characters the engine will tokenize
    and a request made of a million one-character keys is not cheaper than one
    made of a million one-character values.
    """
    total = 0
    stack: list[Any] = [request]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            total += len(item)
        elif isinstance(item, dict):
            for key, value in item.items():
                if isinstance(key, str):
                    total += len(key)
                stack.append(value)
        elif isinstance(item, (list, tuple)):
            stack.extend(item)
    return total


Backend = Literal["server", "local", "ratio"]

#: How to ask an engine to tokenize. The engines this project names do not
#: agree, and the disagreement is not cosmetic: vLLM takes ``{"model",
#: "prompt"}``, llama.cpp takes ``{"content"}``. Sending vLLM's body to
#: llama.cpp does not fail -- it returns ``{"tokens": []}``, a silent zero --
#: so a llama.cpp deployment fell back to estimates while believing it was
#: exact. Each dialect is probed and the one that answers is remembered.
TOKENIZE_DIALECTS: tuple[tuple[str, str], ...] = (
    ("vllm", "prompt"),
    ("llama.cpp", "content"),
)

#: Ollama has no ``/tokenize`` at all, which is why every Ollama deployment
#: fell back to an estimate. It does report ``prompt_eval_count``: the engine's
#: own count of the prompt it just processed, which is the most authoritative
#: number available and needs no third-party service to obtain.
#:
#: Two details make it usable. The count includes the chat template, so "x"
#: comes back as 30 rather than 1 -- the overhead is measured once per model
#: and subtracted, and it is measured rather than assumed because it varies
#: with the template. And ``num_predict`` is 1 rather than 0, because 0 is
#: ignored and the engine generates a full response.
#:
#: Verified exact against a reference tokenizer on seven samples: 1, 2, 4, 7
#: and 100 tokens all matched after calibration.
OLLAMA_GENERATE = "/api/generate"


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
    tokenizer : str, optional
        Path to a ``tokenizer.json`` on this machine, used when the engine
        will not count for itself. A path rather than a model-hub id on
        purpose: resolving a hub repository is an outbound call, and this
        gateway's claim is that nothing leaves the local network.
    allow_engine_probe : bool
        Whether the engine may be asked to *evaluate* a prompt in order to
        count it. **False by default.** Ollama has no ``/tokenize`` but reports
        ``prompt_eval_count``, which is exact -- and obtaining it runs the text
        through the model, so it costs real compute and breaks the promise that
        measuring does not send. Worth having, never silently.
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
        tokenizer: str | None = None,
        allow_ratio: bool = True,
        allow_engine_probe: bool = False,
    ) -> None:
        self.allow_engine_probe = allow_engine_probe
        self.tokenizer = (tokenizer or "").strip()
        self.base_url = (base_url or "").rstrip("/")
        self.model = model
        self.allow_ratio = allow_ratio
        self._local: Any = None
        #: Resolved by the probe in `_server_works`; see TOKENIZE_DIALECTS.
        self._dialect: str = TOKENIZE_DIALECTS[0][1]
        #: Tokens Ollama's chat template adds, measured once in `_ollama_works`.
        self._template_overhead: int = 0
        self.backend: Backend = self._pick_backend()

    # -- backend selection ------------------------------------------------

    def _tokenize_root(self) -> str:
        """``/tokenize`` lives at the server root, not under ``/v1``."""
        root = self.base_url
        return root[: -len("/v1")] if root.endswith("/v1") else root

    def _server_works(self) -> bool:
        """Probe each dialect, and remember the one that answers.

        A zero here is as disqualifying as an exception: an engine that
        tokenizes "ping" into nothing is not tokenizing. That is exactly what
        llama.cpp does when handed vLLM's request body, and taking it at face
        value would mean every budget on that engine counted zero.
        """
        if not self.base_url or not self.model:
            return False
        for name, key in TOKENIZE_DIALECTS:
            try:
                if self._count_server("ping", key, probe=True) > 0:
                    self._dialect = key
                    osh.debug(f"Server tokenizer speaks the {name} dialect.")
                    return True
            except Exception as exc:  # unusable, not a crash
                osh.debug(f"Server tokenizer refused the {name} dialect ({exc}).")
        if self.allow_engine_probe and self._ollama_works():
            return True
        osh.debug("No /tokenize dialect answered; trying a local tokenizer file.")
        return False

    def _post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """One JSON round trip, by whichever client is installed."""
        try:
            import httpx  # optional: part of the [api] extra

            response = httpx.post(url, json=body, timeout=TOKENIZE_TIMEOUT)
            response.raise_for_status()
            return dict(response.json())
        except ImportError:
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=TOKENIZE_TIMEOUT) as response:
                return dict(json.load(response))

    def _ollama_count(self, text: str) -> int:
        """What Ollama says the prompt cost, before calibration."""
        root = self._tokenize_root()
        payload = self._post_json(
            f"{root}{OLLAMA_GENERATE}",
            {"model": self.model, "prompt": text, "stream": False, "options": {"num_predict": 1}},
        )
        count = payload.get("prompt_eval_count")
        if count is None:
            raise ValueError("no prompt_eval_count in the response")
        return int(count)

    def _ollama_works(self) -> bool:
        """Probe Ollama, and measure its chat-template overhead once.

        **Opt-in, because this one sends.** `prompt_eval_count` is exact and it
        is not a tokenizer: obtaining it means running the text through the
        model. `/v1/budget` promises to measure *without* sending, and a test
        asserts it -- rightly, because a planning endpoint that quietly
        consumes graphics-processor time is not one anybody can plan against.
        So this is never chosen automatically; an operator who wants the exact
        number on an engine with no `/tokenize` asks for it, knowing it costs a
        prompt evaluation.

        The overhead is measured rather than assumed because it is a property
        of the model's template, not of Ollama: on `qwen2.5:3b` it is 29
        tokens, and a different template is a different number. Calibrating
        from a one-character prompt and subtracting is what turns the engine's
        count of a *templated* prompt into a count of the caller's text --
        verified exact against a reference tokenizer at 1, 2, 4, 7 and 100
        tokens.
        """
        if not self.base_url or not self.model:
            return False
        try:
            single = self._ollama_count("x")
        except Exception as exc:  # unusable, not a crash
            osh.debug(f"Ollama-style counting unavailable ({exc}).")
            return False
        if single <= 0:
            return False
        # `x` is one token in every vocabulary this would be used with.
        self._template_overhead = single - 1
        self._dialect = "ollama"
        osh.debug(
            f"Counting with Ollama's own prompt_eval_count "
            f"(template overhead {self._template_overhead} tokens)."
        )
        return True

    def _load_local(self) -> bool:
        """Load a tokenizer from a file on this machine.

        **A path, never a model hub.** An earlier version of this resolved a
        Hugging Face repository id, which worked and was wrong for this
        project: resolving a repository is an outbound call, and a gateway
        whose entire claim is that nothing leaves the local network cannot
        phone a third party on startup to learn how to count. It also made the
        count depend on an account and a service that may not be there.

        So the operator points at a file. `tokenizer.json` ships beside most
        open weights and is readable offline, which makes this the sovereign
        way to be exact when the engine will not count for itself.
        """
        if not self.tokenizer:
            return False
        path = Path(self.tokenizer).expanduser()
        if not path.is_file():
            osh.warning(
                f"[budget] tokenizer file {self.tokenizer!r} does not exist; "
                "counting will fall back. Point `tokenizer:` at a tokenizer.json."
            )
            return False
        try:
            from tokenizers import Tokenizer  # optional extra, imported lazily
        except ImportError:
            osh.warning(
                f"[budget] {self.tokenizer!r} is configured but `tokenizers` is "
                "not installed; install ai-bunker[tokenizers]."
            )
            return False
        try:
            self._local = Tokenizer.from_file(str(path))
            return True
        except Exception as exc:  # unusable, not a crash
            osh.warning(f"[budget] {self.tokenizer!r} is not a usable tokenizer ({exc}).")
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

    def _count_server(self, text: str, key: str | None = None, *, probe: bool = False) -> int:
        """Ask the serving engine to count.

        Uses ``httpx`` when it is installed and ``urllib`` otherwise. Not
        indifference: the gateway speaks httpx everywhere else, and a counter
        that reaches the network by a different route than the rest of the
        process is a counter that cannot be exercised by the same test
        harness -- which is how the "exact" path in the gateway went
        unverified long enough to ship broken.
        """
        url = f"{self._tokenize_root()}/tokenize"
        budget = PROBE_TIMEOUT if probe else TOKENIZE_TIMEOUT
        # `model` is harmless to the engines that ignore it and required by
        # the ones that do not.
        body = {"model": self.model, key or self._dialect: text}
        try:
            import httpx  # optional: part of the [api] extra

            response = httpx.post(url, json=body, timeout=budget)
            response.raise_for_status()
            payload = response.json()
        except ImportError:
            request = urllib.request.Request(
                url,
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=budget) as response:
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
            if self._dialect == "ollama":
                # The engine counts the templated prompt; the caller asked
                # about their own text.
                return max(1, self._ollama_count(text) - self._template_overhead)
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

    # `max_output` was a parameter, a field, a docstring entry and a CLI flag,
    # and it appeared in no arithmetic at all: a deployment could ask for
    # 32,000 tokens of output on a 26,000-token window and every figure, every
    # warning and the exit code came back identical. These two checks are what
    # the name always implied.
    #
    # Deliberately NOT `working -= max_output`. The compaction margin already
    # absorbs a reply -- 26,000 declared less a 6,000 margin triggers at
    # 20,000, and a 4,096-token answer from 19,999 lands at 24,095, inside the
    # window -- so charging the conversation for it would double-count and
    # make every published figure wrong. The invariant is that the margin can
    # hold one reply, not that the conversation pays for one.
    if compaction_reserve and max_output > compaction_reserve:
        warnings.append(
            f"One reply can be {max_output:,} tokens and the compaction margin "
            f"is {compaction_reserve:,}. Compaction fires at {starts_at:,}, so a "
            f"single answer from just under that trigger reaches "
            f"{starts_at + max_output:,} -- past the declared context "
            f"({declared:,}), after the one mechanism that could have reduced it "
            "has already run. Raise the margin to at least the output, or lower "
            "the output."
        )

    # The admission bound, and it costs one addition: with an empty
    # conversation and nothing else resident, can this session produce a
    # single turn? A floor plus one reply that does not fit the served context
    # is a request the engine will refuse mid-generation, as a context-length
    # error nobody can act on -- which is the failure this module exists to
    # turn into a named refusal before anything is forwarded.
    if floor + max_output > served_context:
        warnings.append(
            f"The floor ({floor:,}) plus one reply ({max_output:,}) is "
            f"{floor + max_output:,} tokens, and this engine serves "
            f"{served_context:,}. This session cannot produce one turn even "
            "with an empty conversation."
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
        # It said "cannot gate a deployment", and it gates: the verdict below
        # is computed whatever the backend, and the gateway returns 413 on
        # `unusable`. Saying otherwise was the kind of claim this project
        # exists to catch, so the text now says what actually happens --
        # pessimistically, by design, with the remedy named.
        warnings.append(
            "Counted by a characters-per-token ratio, not by a tokenizer, and "
            "deliberately on the pessimistic side: it never reports fewer "
            "tokens than the text really costs, so it over-counts ordinary "
            "prose by roughly half. This figure DOES gate -- a session it "
            "calls unusable is refused -- so start the engine's tokenizer or "
            "install the `tokenizers` extra to be judged on a real count."
        )

    verdict: Literal["ok", "tight", "unusable"]
    if working < min_working or floor + max_output > served_context:
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
