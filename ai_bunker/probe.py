"""
Ask the engine what it serves, instead of believing the configuration file.

Why
---
``upstreams.<name>.served_context`` is the single most load-bearing figure in
this project. Every budget is measured against it, the context declared to
every client is a fraction of it, and the gateway refuses a session on its
arithmetic. :mod:`ai_bunker.config` says so in as many words.

Nothing checked it.

The guard that exists catches a *misspelled key*: ``served_kontext: 32768``
parsed, loaded, and left the gateway declaring 104,857 tokens against an
engine serving 32,768 -- the incident this project was built after, by one
letter and in silence. That hole is closed; keys the loader does not read are
now fatal in ``doctor``.

But ``served_context: 32768`` against an engine serving 8,192 is spelled
perfectly. It parses, it loads, it declares 26,214 tokens to every client, and
it reproduces the same incident with no typo to find. For a project whose
argument is that the only party who can count correctly is the one holding the
tokenizer, the number the counting is measured *against* was the one number
taken on trust.

So it is asked for. Ollama publishes the real context on ``/api/show``, and an
OpenAI-compatible server often publishes it on ``/v1/models``.

Which direction matters
-----------------------
Only one. Configured **above** what the engine serves is the founding
incident: the gateway admits a request the engine will reject. Configured
**below** is conservative -- capacity left on the table, nothing broken -- and
is a legitimate choice an operator may have made deliberately, so it is
reported and not refused.

The same asymmetry the figure audit learned twice: a bound is only useful in
the direction where being wrong costs something.

What this does not do
---------------------
It does not run in the request path, and it must not. A gateway that asked its
upstream for metadata on every turn would be adding a round trip to the thing
whose whole pitch is that it stays out of the way. The probe is also allowed
to fail: an engine that is down, or one that publishes nothing, is a *note*,
because a check that is permanently red is a check nobody reads.

Off the request path is not the same as once, though, and for a while this
module read as if it were. ``serve`` clamps before it admits anything and then
re-checks on a timer, on a plain thread, because the case one boot-time clamp
cannot see is an engine *replaced* underneath a gateway that is already
serving: it keeps the figure the old one served until somebody restarts. See
:func:`clamp_and_watch`, and :func:`reclamp` for why a repeated clamp is not
simply the boot clamp on a loop.

Standard library only, deliberately. ``httpx`` is in the ``[api]`` extra and
``doctor`` has to work on a machine with the base install.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import cycle at runtime, types only
    from .config import Upstream

#: Seconds. Short on purpose: this runs while an operator waits at a terminal,
#: and the answer is a nicety rather than a requirement.
TIMEOUT = 2.0

#: Keys an OpenAI-compatible ``/v1/models`` entry may carry the figure under.
#: ``max_model_len`` is vLLM's spelling, ``context_length`` is what
#: ``best-engine-ai-helper`` publishes, and the third is seen in the wild.
MODEL_KEYS = ("max_model_len", "context_length", "context_window")

#: Seconds between re-checks while a gateway is serving. Five minutes, which
#: is chosen rather than measured and says so: the thing it bounds is how long
#: a gateway can keep serving the wrong figure after somebody swaps the engine
#: under it, and there is no measurement that tells you how long that is
#: acceptable. Short enough that an engine swap is caught within a coffee,
#: long enough that an engine which never answers is asked twelve times an
#: hour rather than constantly.
RECHECK_INTERVAL = 300.0


def _get(url: str, payload: dict | None = None, timeout: float = TIMEOUT) -> dict | None:
    """One request, or None. Never raises.

    Every failure mode is the same answer here -- engine down, wrong path,
    HTML error page, a body that is not JSON -- because the caller does the
    same thing with all of them: says it could not ask.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        # Building the request is inside the try, not before it. `Request`
        # raises `ValueError` on a URL with no scheme, and an operator who
        # writes `base_url: 127.0.0.1:8001` has made a configuration mistake,
        # not a reason for `doctor` to end in a traceback. Found by the test
        # that asserts this function never raises.
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None
    return body if isinstance(body, dict) else None


def _from_ollama(root: str, model: str, timeout: float) -> int | None:
    """Ollama's ``/api/show``.

    The figure lives in ``model_info`` under an architecture-prefixed key --
    ``qwen3.context_length``, ``llama.context_length`` -- so the architecture
    is not guessed, the suffix is matched. A model this machine has not pulled
    publishes nothing, which is the correct answer rather than a gap.
    """
    if not model:
        return None
    body = _get(f"{root}/api/show", {"model": model}, timeout)
    info = (body or {}).get("model_info")
    if not isinstance(info, dict):
        return None
    for key, value in info.items():
        if key.endswith(".context_length") and isinstance(value, int) and value > 0:
            return value
    return None


def _from_models(root: str, model: str, timeout: float) -> int | None:
    """An OpenAI-compatible ``/v1/models``.

    The named model first, then a sole entry if the server serves exactly one:
    a single-model deployment that spells the name differently from the
    configuration is common, and one entry leaves nothing to resolve.
    """
    body = _get(f"{root}/v1/models", None, timeout)
    entries = (body or {}).get("data")
    if not isinstance(entries, list) or not entries:
        return None
    candidates = [e for e in entries if isinstance(e, dict) and e.get("id") == model]
    if not candidates and len(entries) == 1 and isinstance(entries[0], dict):
        candidates = [entries[0]]
    for entry in candidates:
        for key in MODEL_KEYS:
            value = entry.get(key)
            if isinstance(value, int) and value > 0:
                return value
    return None


def served_context(upstream: Upstream, timeout: float = TIMEOUT) -> tuple[int | None, str]:
    """What the engine says it serves, and where the answer came from.

    Returns ``(None, reason)`` when nothing could be read. The reason is for a
    human: it is printed beside the check, and "the engine is not running" and
    "this engine publishes no context" are different things to be told.

    Parameters
    ----------
    upstream : Upstream
        The configured upstream. Its ``model`` is what gets asked about; an
        upstream with no model named can still be answered by a server that
        serves exactly one.
    timeout : float
        Seconds per request.

    Returns
    -------
    tuple[int | None, str]
        The measured context and its source, or ``None`` and why not.
    """
    root = upstream.tokenize_url
    found = _from_ollama(root, upstream.model, timeout)
    if found is not None:
        return found, "ollama /api/show"
    found = _from_models(root, upstream.model, timeout)
    if found is not None:
        return found, "/v1/models"
    return None, "the engine published no context length (or is not running)"


def clamp_to_engine(settings, timeout: float = TIMEOUT) -> list[str]:
    """Lower any ``served_context`` the engine contradicts, and say which.

    `doctor` *reports*; this *acts*, and only one of the two was enough.
    `doctor` is a command somebody runs, so a deployment whose engine is
    swapped under a running gateway keeps the stale figure until a human
    thinks to re-run it -- and the figure in question is the one every budget
    is measured against.

    **Downward only, and that is the whole safety argument.** Raising
    `served_context` from a probe would hand capacity to the gateway on the
    strength of one HTTP response: a server answering for a different model,
    or a proxy in between, could talk it into declaring room that does not
    exist, which is the failure this project exists to prevent. Lowering can
    only ever waste capacity. So a measurement above the configuration is
    reported and ignored, and a measurement below it wins.

    Called from ``serve`` and nowhere else -- deliberately not from
    ``State.__init__`` or a startup event, both of which every test that
    builds the application would run, turning the suite into something that
    makes network calls. Once, synchronously, where a human starts a server,
    and before anything is built on the answer.

    This is the boot half. :func:`reclamp` is the other half and is *not* this
    function on a timer: it measures against the configured ceiling rather
    than the live figure, which is the difference between re-checking and
    ratcheting. Read it before reaching for this one in a loop.

    Parameters
    ----------
    settings : Settings
        Mutated in place: each upstream's ``served_context`` may be lowered.
    timeout : float
        Seconds per request, per upstream.

    Returns
    -------
    list[str]
        One line per upstream worth telling the operator about. Empty when
        every configured figure already agrees with its engine, or when no
        engine would say.
    """
    notes = []
    for up in settings.upstreams.values():
        measured, source = served_context(up, timeout)
        if measured is None or measured >= up.served_context:
            continue
        notes.append(
            f"[gateway] {up.name}: served_context {up.served_context:,} is above the "
            f"{measured:,} this engine serves ({source}). Using {measured:,}. Every budget "
            f"and the context declared to clients follow the smaller number; fix the "
            f"configuration so this is not decided at boot."
        )
        up.served_context = measured
    return notes


def configured_contexts(settings) -> dict[str, int]:
    """Every ``served_context`` as a human wrote it, before any probe lowers one.

    Must be taken *before* :func:`clamp_to_engine`, which mutates in place.
    :func:`clamp_and_watch` is the reason this is not left to callers to
    remember -- see the ratchet it exists to prevent, there.
    """
    return {name: up.served_context for name, up in settings.upstreams.items()}


def reclamp(settings, ceilings: dict[str, int], timeout: float = TIMEOUT) -> list[str]:
    """Re-apply the clamp, measuring each engine against what was *configured*.

    :func:`clamp_to_engine` lowers from whatever the live figure happens to be,
    which is right exactly once -- at boot, where the live figure is still the
    configured one. Run it on a timer and it becomes a ratchet: a single low
    reading from an engine that was reloading pins the gateway at that figure
    for the life of the process, and the only cure is a restart. The capacity
    is not wrong, it is just gone, and nothing says why.

    So the comparison here is always against the ceiling an operator wrote,
    never against the last thing a probe decided:

    ``served_context = min(configured, measured)``

    which leaves the safety argument exactly where :func:`clamp_to_engine` put
    it. **A probe still cannot raise anything.** The configured figure is a
    hard ceiling that no HTTP response can lift, so a server answering for a
    different model, or a proxy in the middle, cannot talk the gateway into
    announcing room that does not exist -- the founding incident. What a probe
    *can* now do is give back room it took away earlier, up to that ceiling and
    not one token past it.

    An engine that will not answer changes nothing. That is deliberate and it
    is the asymmetric case worth being careful about: restoring the configured
    figure because the engine went quiet would widen the bound on no evidence,
    at the moment evidence is least available. Silent, too -- a line every five
    minutes saying an engine still will not say is a log nobody reads, which
    the module docstring already argues about `doctor`.

    Parameters
    ----------
    settings : Settings
        Mutated in place.
    ceilings : dict[str, int]
        From :func:`configured_contexts`, taken before the first clamp.
    timeout : float
        Seconds per request, per upstream.

    Returns
    -------
    list[str]
        One line per upstream whose figure moved. Empty when nothing changed.
    """
    notes = []
    for name, up in settings.upstreams.items():
        ceiling = ceilings.get(name, up.served_context)
        measured, source = served_context(up, timeout)
        if measured is None:
            continue
        target = min(ceiling, measured)
        if target == up.served_context:
            continue
        if target < up.served_context:
            notes.append(
                f"[gateway] {name}: this engine now serves {measured:,}, below the "
                f"{up.served_context:,} in force ({source}). Using {target:,}. Every budget "
                f"and the context declared to clients follow the smaller number from here; "
                f"requests already admitted were admitted against the old figure."
            )
        else:
            notes.append(
                f"[gateway] {name}: this engine serves {measured:,} again ({source}), so the "
                f"{up.served_context:,} a probe lowered it to is given back up to the "
                f"configured {ceiling:,}. A probe never raises past what the configuration "
                f"says."
            )
        up.served_context = target
    return notes


def watch(
    settings,
    ceilings: dict[str, int],
    *,
    report: Callable[[str], None],
    interval: float = RECHECK_INTERVAL,
    timeout: float = TIMEOUT,
    stop: threading.Event | None = None,
) -> threading.Thread:
    """Keep asking, on a timer, for as long as the process serves.

    A daemon thread, and a plain one rather than anything on the event loop.
    The requests in this module are blocking ``urllib`` by deliberate choice --
    the module docstring says why -- and a blocking call on an async loop is
    the defect this project has already fixed twice: a tokenizer probe that
    stopped the gateway answering anybody for the length of its own timeout.
    Off the loop it cannot do that, whatever the engine does.

    The first measurement is *not* here. :func:`clamp_and_watch` takes it
    synchronously, before the server is built on the answer, because a figure
    that is only correct a few minutes after boot is a figure the first
    requests were served against wrongly.

    What this gives up, stated rather than implied: capacity can now change
    under a running gateway, so two requests a minute apart may have been
    admitted against different figures. That is the point of it -- the
    alternative is serving the stale number until somebody restarts -- but it
    means the declared context is no longer constant for the life of a
    process, and anything that caches it per-process would be wrong.

    Parameters
    ----------
    settings, ceilings, timeout
        As :func:`reclamp`.
    report : Callable[[str], None]
        Where the notes go. ``osh.warning`` from the serve path.
    interval : float
        Seconds between checks. Tests pass something small.
    stop : threading.Event, optional
        Set it to end the loop. Waited on rather than slept through, so the
        thread stops when asked instead of at the end of its nap.

    Returns
    -------
    threading.Thread
        Already started.
    """
    ending = stop if stop is not None else threading.Event()

    def loop() -> None:
        while not ending.wait(interval):
            for note in reclamp(settings, ceilings, timeout):
                report(note)

    thread = threading.Thread(target=loop, name="ai-bunker-probe", daemon=True)
    thread.start()
    return thread


def clamp_and_watch(
    settings,
    *,
    report: Callable[[str], None],
    interval: float = RECHECK_INTERVAL,
    timeout: float = TIMEOUT,
    stop: threading.Event | None = None,
) -> threading.Thread:
    """The whole serve-time story, in the order that makes it correct.

    Three steps that have to happen in this sequence, which is why they live
    here and not in the caller: read the configured ceilings, *then* clamp
    once, *then* start re-checking against those ceilings. Snapshot after the
    clamp instead and the ceiling is whatever the first probe decided, which
    is the ratchet :func:`reclamp` exists to avoid -- a mistake available to
    anybody wiring these three calls up by hand, so they are not offered
    separately to the serve path.
    """
    ceilings = configured_contexts(settings)
    for note in clamp_to_engine(settings, timeout):
        report(note)
    return watch(settings, ceilings, report=report, interval=interval, timeout=timeout, stop=stop)


def mismatch(upstream: Upstream, timeout: float = TIMEOUT) -> tuple[bool, str]:
    """Whether the configured context is safe, and a sentence saying why.

    ``(True, ...)`` means safe: either the engine serves at least what the
    configuration claims, or it would not say. Only *configured above served*
    is ``False``, because only that direction admits a request the engine will
    reject.
    """
    measured, source = served_context(upstream, timeout)
    if measured is None:
        return True, f"{upstream.name}: context not verified — {source}"
    if upstream.served_context > measured:
        return False, (
            f"{upstream.name}: served_context is {upstream.served_context:,} and the engine "
            f"serves {measured:,} ({source}). The gateway would declare "
            f"{upstream.served_context:,} worth of room against an engine that has "
            f"{measured:,} — which is the incident this project was built after, spelled "
            f"correctly. Lower served_context to {measured:,}."
        )
    if upstream.served_context < measured:
        return True, (
            f"{upstream.name}: served_context {upstream.served_context:,} is below the "
            f"engine's {measured:,} ({source}) — safe, and capacity left unused if that "
            f"was not deliberate"
        )
    return True, f"{upstream.name}: served_context {upstream.served_context:,} matches ({source})"
