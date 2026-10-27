"""
The layer-streaming engine, behind an OpenAI-compatible socket.

Why this is an adapter and not a reimplementation
-------------------------------------------------
`AirLLM <https://github.com/lyogavin/airllm>`_ is imported, never vendored.
The decision was made on what the two halves of it actually are.

The part that looks worth copying -- "load one layer, run it, free it" -- is
twenty lines and is not the work. The work is the per-architecture layer-name
mapping (Llama, Qwen and its mixture-of-experts and vision variants, DeepSeek,
Mistral, Phi, Gemma, ChatGLM, Baichuan, InternLM, Yi), the safetensors
splitting, the block-wise quantization of the shards, and the prefetch that
keeps the pipeline fed. That is the half that churns, every time a model family
ships with its layers named something new, and a vendored copy of it decays in
silence: it keeps working for the models it knew and refuses the one you
actually wanted, with a KeyError.

So this project copies none of it, and copies none of the weight of it either.
``airllm`` brings PyTorch, transformers, accelerate and safetensors -- some two
and a half gibibytes of wheels -- and ``pip install ai-bunker`` must not. It
lives behind the ``airllm`` extra, it is imported lazily, and a deployment that
only ever runs ``sizing`` or ``doctor`` never meets it.

Licensing says the same thing. AirLLM is Apache-2.0 and this project is
BSD-3-Clause: compatible to depend on, and vendoring would move an Apache
NOTICE obligation into a Berkeley Software Distribution licensed tree for no
gain.

Nor does it load the checkpoint itself, if it can help it
---------------------------------------------------------
``best-engine-ai-helper`` is this suite's owner of "which local model, on what
hardware, through which backend", and its ``offload`` module is the suite's
AirLLM adapter. :func:`_loader` therefore prefers
``best_engine_ai_helper.airllm_load`` and only imports ``airllm`` directly when
the installed helper does not offer it.

That is the same deference the rest of this package already practises --
``catalog/serving.yaml`` says out loud that "which model fits this laptop"
belongs to the helper -- and it buys one thing worth having: exactly one place
in the suite passes keyword arguments to ``AutoModel.from_pretrained``. A
renamed option upstream, a new sharding flag, a workaround for one model
family: absorbed once, not in every package that wanted a streamed model.

What is left here, and why it is not duplication:

**The socket.** The helper's ``generate`` is a Python call that blocks and
returns a string, because AirLLM is a library and not a daemon. This gateway
proxies HTTP and nothing else. The OpenAI-compatible surface below -- streaming
frames, keepalives, the refusals -- is what turns a library into something
:mod:`ai_bunker.gateway` can treat as an upstream, and it exists nowhere else
in the suite.

**The server arithmetic.** :mod:`ai_bunker.fallback` sizes streaming against
``catalog/serving.yaml``: weight footprint per quantization, key-value cache
geometry, the context that cache will actually allow beside the shards, and the
comparison against a priced accelerator. The helper's catalogue does not carry
those, by the same division that makes :mod:`ai_bunker.sizing` exist alongside
the helper's ``recommend``.

Why a separate process, and not inside the gateway
--------------------------------------------------
The gateway is a proxy. Every upstream it has ever talked to is a URL, which
is what lets it screen, budget, audit and refuse without knowing what is at
the other end. Importing an inference engine into it would put model weights,
PyTorch and a generation loop holding the global interpreter lock inside the
one process whose job is to answer ``/health`` promptly -- a defect this
project has already fixed once, in the inbound pipeline, and should not
reintroduce by a different door.

So the engine runs here, alone, speaking the dialect the gateway already
knows::

    ai-bunker airllm serve --model /models/Qwen3-Coder-Next --port 8003

and the gateway is told about it the way it is told about anything else::

    upstreams:
      fallback:
        base_url: http://127.0.0.1:8003/v1
        served_context: 8192
        remote: false
        model: /models/Qwen3-Coder-Next

Nothing in ``gateway.py`` changes, no new configuration key exists, and the
screening, the budget and the decision log apply to a streamed-off-disk answer
exactly as they do to a vLLM one. That is the whole benefit of the shape.

What this is honest about
-------------------------
The arithmetic in :mod:`ai_bunker.fallback` is tested. **This module's engine
path is not**, in the sense that matters: its tests drive it against a stub
that implements the two methods a transformers-style model exposes, because
the real path needs a multi-gibibyte checkpoint and hours of wall clock to
produce one paragraph. The HTTP surface, the chat templating, the streaming
framing and the refusals are covered; "this produces the same tokens as
transformers would" is not a claim made here.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import os_helper as osh

# FastAPI reads a handler's annotations out of its **module** globals. With
# `from __future__ import annotations` every annotation is a string, so a
# `Request` imported inside `create_app` is invisible when the route is built
# -- and FastAPI falls back to treating the parameter as a query field, which
# answers every POST with `422 {"loc": ["query", "request"]}`. Measured
# exactly that way. So the import is at module scope, and guarded, because a
# machine that only runs the arithmetic has no reason to have FastAPI.
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse, StreamingResponse

    HAVE_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the environment
    HAVE_FASTAPI = False
    Request = Any  # type: ignore[assignment,misc]

#: How long a stream may go without sending anything before a keepalive
#: comment is written. Layer streaming produces a token every few seconds at
#: best, and an intermediary that closes an idle connection would turn a slow
#: answer into a failed one.
KEEPALIVE_S = 5.0

#: Said in two places -- the suite's adapter raising and a direct import
#: failing -- so it is spelled once. Both extras resolve to the same `airllm`
#: distribution, and a user sent to the wrong line installs the right thing by
#: accident or gives up; neither is acceptable from a refusal.
_MISSING_ENGINE = (
    "The layer-streaming fallback needs the AirLLM runtime, which this project does not "
    "install by default because it brings PyTorch with it:\n\n"
    "    pip install 'ai-bunker[airllm]'              # or\n"
    "    pip install 'best-engine-ai-helper[airllm]'  # the same distribution\n\n"
    "Everything in `ai-bunker fallback` works without it -- the decision of whether to "
    "stream is arithmetic, and only running the engine needs the engine."
)

#: Default port. Deliberately not 8000 or 8001: those are where this project's
#: documentation puts the gateway and the resident engine, and a fallback that
#: collides with the thing it is a fallback for is a bad afternoon.
DEFAULT_PORT = 8003


class Engine(Protocol):
    """The two things this module needs from a loaded model.

    Exactly the transformers surface AirLLM presents, and no more, so the
    tests can supply a stub and so swapping the engine for another
    layer-streaming implementation is a change in :func:`load_engine` alone.
    """

    tokenizer: Any

    def generate(self, input_ids: Any, **kwargs: Any) -> Any: ...


@dataclass
class Loaded:
    """A loaded engine and the facts a report needs about it."""

    engine: Engine
    model: str
    context: int
    compression: str | None


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def is_local_checkpoint(model: str) -> bool:
    """Whether ``model`` names something already on this disk.

    A Hugging Face repository id is ``owner/name`` and nothing else, so the
    test is simply whether the string resolves to a directory that looks like
    a checkpoint. Deliberately conservative: a path that exists but holds no
    configuration is not a checkpoint, and treating it as one would turn a
    typo into a silent download.
    """
    if not model:
        return False
    path = Path(model).expanduser()
    if not path.is_dir():
        return False
    return any((path / name).exists() for name in ("config.json", "model.safetensors.index.json"))


def load_engine(
    model: str,
    *,
    context: int = 8192,
    compression: str | None = None,
    shards_dir: str | None = None,
    hf_token: str | None = None,
    delete_original: bool = False,
    allow_download: bool = False,
) -> Loaded:
    """Load one checkpoint through AirLLM, with the import failure spelled out.

    The first call on a checkpoint **splits it layer by layer onto disk**,
    which reads the whole thing, writes the whole thing again, and takes as
    long as the download did. Nothing here hides that: a caller that does not
    expect a quiet half-hour on first use will report it as a hang.

    Parameters
    ----------
    model : str
        A Hugging Face repository id, or a local path to one.
    context : int
        Maximum sequence length to accept. The KV cache for it is resident, so
        this is the figure that decides whether a small card can run the model
        at all -- see :func:`ai_bunker.fallback.size_streaming`.
    compression : {'4bit', '8bit'}, optional
        AirLLM block-wise compression of the shards. Fewer bytes per layer is
        fewer bytes off the disk per token, and under streaming that is the
        only thing throughput depends on, so this is the single most effective
        knob here. It needs ``bitsandbytes``, which the extra does not pull in
        because it does not build everywhere.
    shards_dir : str, optional
        Where to keep the split checkpoint. Worth setting: it wants about as
        much room as the original, and the default lands beside the model.
    hf_token : str, optional
        For a gated repository. Read from the environment through
        ``os-helper`` when not given, so it never has to be written down.
    delete_original : bool
        Remove the unsplit checkpoint once the shards exist. Reclaims the
        space; makes the next tool that wants the plain checkpoint re-download
        it. Off by default.
    allow_download : bool
        Permit fetching ``model`` from a model hub. **Off by default**, which
        is the sovereignty rule and not a convenience: a repository id is
        refused rather than quietly downloaded, and a local path sets
        ``HF_HUB_OFFLINE`` so the loader cannot check a hub for a newer
        revision either.

    Returns
    -------
    Loaded
        The engine and what it was loaded with.
    """
    # Offline by default, and this is the project's sovereignty rule rather
    # than a convenience. Handing a repository id to a loader makes it reach a
    # third-party hub; a deployment whose argument is that nothing leaves the
    # local network does not do that because a flag defaulted the other way.
    # So a local path loads, a repository id is REFUSED, and downloading is a
    # decision an operator takes in as many words -- the same rule this project
    # applies to a premium route.
    #
    # Checked BEFORE the import, deliberately. A deployment that is going to be
    # refused should learn that now, not after being told to install two and a
    # half gibibytes of wheels -- and the refusal stays testable on a machine
    # that will never have the engine.
    local = is_local_checkpoint(model)
    osh.check(
        local or allow_download,
        f"{model!r} is not a local checkpoint, so loading it would fetch it from a model hub "
        "over the internet. This project does not do that by default. Either point --model at "
        "a path you already have, or pass allow_download=True / `--allow-download` to say out "
        "loud that this deployment may reach a third party.",
    )
    if not local:
        osh.warning(
            f"[airllm] fetching {model} from a model hub. This deployment is reaching a third "
            "party for the duration of the download."
        )
    else:
        # Belt as well as braces: transformers will happily check a hub for a
        # newer revision of a local path unless it is told not to.
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

    # Not `osh.get_config` directly: it raises when a key resolves nowhere,
    # which is right for something a program cannot run without and wrong for
    # a token only a gated repository needs. `config._from_environment` is the
    # wrapper this project already uses for exactly that distinction, and it
    # swallows the message as well as the exception -- "HF_TOKEN is not set" is
    # not a line to print on a machine loading a local checkpoint.
    from ai_bunker.config import _from_environment  # lazy: avoids a cycle at import

    token = hf_token or _from_environment("HF_TOKEN", "huggingface") or None
    if compression:
        osh.check(
            compression in ("4bit", "8bit"),
            f"compression must be '4bit' or '8bit', not {compression!r}",
        )

    osh.info(
        f"[airllm] loading {model}"
        + (f" with {compression} compression" if compression else "")
        + ". First use splits the checkpoint layer by layer, which takes as long as the "
        "download did and needs as much disk again."
    )
    engine = _loader()(
        model,
        compression=compression,
        shards_dir=shards_dir,
        hf_token=token,
        delete_original=delete_original,
    )
    return Loaded(engine=engine, model=model, context=context, compression=compression)


def _loader() -> Callable[..., Any]:
    """The function that turns a checkpoint reference into a loaded engine.

    Resolved at call time, and in a deliberate order.

    ``best_engine_ai_helper.airllm_load`` **first**. That package is this
    suite's owner of "which local model, on what hardware, through which
    backend", and its ``offload`` module is the suite's AirLLM adapter. Going
    through it means one place in the suite passes arguments to
    ``AutoModel.from_pretrained``, so a change upstream -- a renamed keyword, a
    new sharding option, a workaround for one model family -- is absorbed once
    rather than in every package that wanted a streamed model.

    Importing ``airllm`` directly **second**, so this module keeps working on a
    machine that has the engine and an older helper. The fallback is not a
    preference; it is the version skew that a two-repository suite actually
    has, and without it this file would be pinned to a release of its sibling.
    """
    try:
        from best_engine_ai_helper import airllm_load  # lazy: the suite's adapter
    except ImportError:
        pass
    else:

        def through_the_suite(
            model: str,
            *,
            compression: str | None,
            shards_dir: str | None,
            hf_token: str | None,
            delete_original: bool,
        ) -> Any:
            try:
                return airllm_load(
                    model,
                    compression=compression,
                    layer_shards_saving_path=shards_dir,
                    hf_token=hf_token,
                    delete_original=delete_original,
                )
            except ImportError as exc:
                # The helper names its own extra, which is correct for its own
                # users and confusing for one who was told to install
                # `ai-bunker[airllm]` by this project. Either works -- both
                # resolve to the same `airllm` distribution -- so the message
                # says so rather than sending somebody to the wrong line.
                raise ImportError(_MISSING_ENGINE + f"\n\nThe suite said: {exc}") from exc

        return through_the_suite

    try:
        from airllm import AutoModel  # lazy on purpose: see the module docstring
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(_MISSING_ENGINE) from exc

    def directly(
        model: str,
        *,
        compression: str | None,
        shards_dir: str | None,
        hf_token: str | None,
        delete_original: bool,
    ) -> Any:
        kwargs: dict[str, Any] = {}
        if compression:
            kwargs["compression"] = compression
        if shards_dir:
            kwargs["layer_shards_saving_path"] = shards_dir
        if hf_token:
            kwargs["hf_token"] = hf_token
        if delete_original:
            kwargs["delete_original"] = True
        return AutoModel.from_pretrained(model, **kwargs)

    return directly


# ---------------------------------------------------------------------------
# Prompting
# ---------------------------------------------------------------------------


def render_prompt(tokenizer: Any, messages: list[dict[str, Any]]) -> str:
    """Turn OpenAI-shaped messages into the string this checkpoint expects.

    The tokenizer's own chat template when it has one, because getting the
    special tokens wrong does not fail loudly -- it degrades the answer, and
    on an engine that takes an hour per answer a silent degradation is
    expensive to notice.
    """
    flat = [
        {
            "role": str(m.get("role") or "user"),
            "content": m.get("content")
            if isinstance(m.get("content"), str)
            # The multimodal shape: a list of parts. Only the text parts can
            # go to a text model, and dropping the rest silently would answer
            # a different question than the one asked.
            else " ".join(
                str(p.get("text") or "")
                for p in (m.get("content") or [])
                if isinstance(p, dict) and p.get("type") == "text"
            ),
        }
        for m in messages
    ]
    template = getattr(tokenizer, "apply_chat_template", None)
    if template is not None and getattr(tokenizer, "chat_template", None):
        return str(template(flat, tokenize=False, add_generation_prompt=True))
    # No template: a plain transcript, which is what a base model wants anyway.
    body = "\n\n".join(f"{m['role']}: {m['content']}" for m in flat)
    return f"{body}\n\nassistant:"


def _encode(tokenizer: Any, prompt: str, context: int) -> Any:
    return tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=context,
        return_attention_mask=False,
    )


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def generate_text(
    loaded: Loaded,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 256,
    temperature: float | None = None,
) -> str:
    """One blocking completion. Minutes to hours; that is the regime."""
    tok = loaded.engine.tokenizer
    encoded = _encode(tok, render_prompt(tok, messages), loaded.context)
    kwargs: dict[str, Any] = {"max_new_tokens": max_tokens, "use_cache": True}
    if temperature is not None and temperature > 0:
        kwargs["do_sample"] = True
        kwargs["temperature"] = temperature
    out = loaded.engine.generate(encoded["input_ids"], **kwargs)
    text = tok.decode(out[0], skip_special_tokens=True)
    prompt_text = tok.decode(encoded["input_ids"][0], skip_special_tokens=True)
    return text[len(prompt_text) :] if text.startswith(prompt_text) else text


def generate_stream(
    loaded: Loaded,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int = 256,
    temperature: float | None = None,
) -> Iterator[str]:
    """Yield text as it is produced, falling back to one chunk if it cannot.

    Streaming matters more here than anywhere else in this project, and for
    the opposite of the usual reason. A resident engine streams so the reader
    sees progress; this one streams so the *connection survives* -- a client
    waiting forty minutes for a complete body will give up, and several
    intermediaries will give up for it.

    ``transformers``'s ``TextIteratorStreamer`` is used when the engine's
    ``generate`` accepts it. When it does not -- a different layer-streaming
    engine, or a stub -- the whole completion is produced and yielded as one
    chunk rather than failing, and the caller cannot tell the difference
    except in the timing.
    """
    try:
        from transformers import TextIteratorStreamer  # lazy: the extra is optional
    except ImportError:  # pragma: no cover - transformers comes with airllm
        yield generate_text(loaded, messages, max_tokens=max_tokens, temperature=temperature)
        return

    tok = loaded.engine.tokenizer
    encoded = _encode(tok, render_prompt(tok, messages), loaded.context)
    streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
    kwargs: dict[str, Any] = {
        "max_new_tokens": max_tokens,
        "use_cache": True,
        "streamer": streamer,
    }
    if temperature is not None and temperature > 0:
        kwargs["do_sample"] = True
        kwargs["temperature"] = temperature

    failure: list[BaseException] = []

    def run() -> None:
        try:
            loaded.engine.generate(encoded["input_ids"], **kwargs)
        except BaseException as exc:  # re-raised on the main thread
            failure.append(exc)
        finally:
            # Unconditionally, and this is the important line. The iterator
            # blocks on a queue with no timeout, so the only thing that ends
            # it is the stop signal `end()` writes. An engine that accepts the
            # `streamer` keyword, ignores it and returns the answer the
            # ordinary way therefore hangs the request **forever** -- not
            # slowly, which on an engine measured in minutes per answer is
            # indistinguishable from working. Calling it here is also safe
            # when the engine already called it: the consumer has left the
            # loop on the first stop signal and a second one is never read.
            streamer.end()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    produced = False
    for piece in streamer:
        if piece:
            produced = True
            yield piece
    worker.join()

    if produced:
        # Partial output followed by a failure still has to surface: a stream
        # that stops early and reports success is the worst of the options.
        if failure:
            raise failure[0]
        return

    if failure and not isinstance(failure[0], TypeError):
        raise failure[0]

    # Either the engine refused the `streamer` keyword, or it accepted it,
    # ignored it, and returned the answer the ordinary way. Both end here with
    # nothing streamed, and yielding nothing would report an empty completion
    # as a successful one.
    yield generate_text(loaded, messages, max_tokens=max_tokens, temperature=temperature)


# ---------------------------------------------------------------------------
# The socket
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk(model: str, delta: dict[str, Any], finish: str | None = None) -> dict[str, Any]:
    return {
        "object": "chat.completion.chunk",
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def create_app(load: Callable[[], Loaded]) -> Any:
    """An OpenAI-compatible application in front of one loaded engine.

    Parameters
    ----------
    load : callable
        Returns the :class:`Loaded` engine. Called once, on the first request
        rather than at import, so the process starts and answers ``/health``
        while a checkpoint is still being split -- which can take half an
        hour, and during which an operator needs to be able to tell the
        difference between "working" and "wedged".

    Returns
    -------
    fastapi.FastAPI
        With ``/health``, ``/v1/models`` and ``/v1/chat/completions``.
    """
    osh.check(HAVE_FASTAPI, "The engine's socket needs `pip install 'ai-bunker[api]'`.")

    app = FastAPI(title="ai-bunker layer-streaming engine", version="1")
    state: dict[str, Any] = {"loaded": None, "loading": False, "error": None}
    lock = threading.Lock()

    def engine() -> Loaded:
        with lock:
            if state["loaded"] is None:
                state["loading"] = True
                try:
                    state["loaded"] = load()
                except BaseException as exc:
                    state["error"] = str(exc)
                    raise
                finally:
                    state["loading"] = False
            return state["loaded"]  # type: ignore[return-value]

    @app.get("/health")
    async def health() -> dict[str, Any]:
        """Deliberately does not load the engine, so it can report *during* a load."""
        loaded = state["loaded"]
        return {
            "status": "ok" if loaded else ("loading" if state["loading"] else "idle"),
            "engine": "airllm",
            "model": loaded.model if loaded else None,
            "context": loaded.context if loaded else None,
            "compression": loaded.compression if loaded else None,
            "error": state["error"],
            # Said in the health check because it is the fact most likely to
            # be mistaken for a fault: this engine is slow by construction.
            "interactive": False,
            "note": (
                "Layer-streaming engine: the whole checkpoint is read off storage for every "
                "generated token. Expect fractions of a token per second. See "
                "`ai-bunker fallback` for the arithmetic on this machine."
            ),
        }

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        loaded = state["loaded"]
        if loaded is None:
            return {"object": "list", "data": []}
        return {
            "object": "list",
            "data": [
                {
                    "id": loaded.model,
                    "object": "model",
                    "owned_by": "ai-bunker",
                    "context_length": loaded.context,
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        try:
            body = await request.json()
        except (ValueError, TypeError):
            return JSONResponse({"error": {"message": "Body is not JSON."}}, status_code=400)

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            return JSONResponse(
                {"error": {"message": "`messages` must be a non-empty list."}}, status_code=400
            )

        try:
            loaded = engine()
        except ImportError as exc:
            return JSONResponse({"error": {"message": str(exc)}}, status_code=501)
        except Exception as exc:  # a load failure is a 503, not a crash
            return JSONResponse({"error": {"message": str(exc)}}, status_code=503)

        max_tokens = int(body.get("max_tokens") or body.get("max_completion_tokens") or 256)
        temperature = body.get("temperature")
        temperature = float(temperature) if temperature is not None else None

        if not body.get("stream"):
            text = generate_text(loaded, messages, max_tokens=max_tokens, temperature=temperature)
            return {
                "object": "chat.completion",
                "model": loaded.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": text},
                        "finish_reason": "stop",
                    }
                ],
            }

        def body_stream() -> Iterator[str]:
            yield _sse(_chunk(loaded.model, {"role": "assistant", "content": ""}))
            # The generation runs on a worker so the keepalive can be written
            # while nothing is coming. Without it a seven-second-per-token
            # answer sits silent long enough for a proxy to close it.
            pieces: queue.Queue[tuple[str, Any]] = queue.Queue()

            def pump() -> None:
                try:
                    for piece in generate_stream(
                        loaded, messages, max_tokens=max_tokens, temperature=temperature
                    ):
                        pieces.put(("delta", piece))
                except BaseException as exc:  # relayed to the client
                    pieces.put(("error", exc))
                pieces.put(("done", None))

            threading.Thread(target=pump, daemon=True).start()
            while True:
                try:
                    kind, value = pieces.get(timeout=KEEPALIVE_S)
                except queue.Empty:
                    yield ": waiting on a layer read\n\n"
                    continue
                if kind == "delta":
                    yield _sse(_chunk(loaded.model, {"content": value}))
                elif kind == "error":
                    yield _sse({"error": {"message": f"{type(value).__name__}: {value}"}})
                    break
                else:
                    yield _sse(_chunk(loaded.model, {}, finish="stop"))
                    yield "data: [DONE]\n\n"
                    break

        return StreamingResponse(
            body_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def serve(
    *,
    model: str,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    context: int = 8192,
    compression: str | None = None,
    shards_dir: str | None = None,
    eager: bool = False,
    allow_download: bool = False,
) -> None:
    """Run the engine's socket.

    Binds to localhost by default, for the reason the gateway does: a tool
    whose whole argument is sovereignty does not listen on every interface the
    moment it starts.
    """
    # Before anything opens. Loading is lazy so that `/health` can answer while
    # a checkpoint is being split, and the cost of that is a configuration
    # error arriving as a per-request failure: `--model owner/name` without
    # `--allow-download` used to start a socket that refused every request it
    # ever received. A reference this process can never load is a reason not to
    # start, so it is checked here as well -- cheaply, since it is a
    # filesystem test and not a load.
    osh.check(
        is_local_checkpoint(model) or allow_download,
        f"{model!r} is not a local checkpoint, so serving it would fetch it from a model hub "
        "over the internet. This project does not do that by default. Either point --model at "
        "a path you already have, or pass --allow-download to say out loud that this "
        "deployment may reach a third party.",
    )

    try:
        import uvicorn  # lazy: the extra is optional
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Running the engine needs `pip install 'ai-bunker[api]'`.") from exc

    def load() -> Loaded:
        return load_engine(
            model,
            context=context,
            compression=compression,
            shards_dir=shards_dir,
            allow_download=allow_download,
        )

    app = create_app(load)
    if eager:
        # Split and load before the socket opens, so a scripted deployment
        # fails at start rather than on the first request an hour later.
        started = time.monotonic()
        load()
        osh.info(f"[airllm] loaded in {time.monotonic() - started:.0f}s")
    uvicorn.run(app, host=host, port=port, log_level="info")
