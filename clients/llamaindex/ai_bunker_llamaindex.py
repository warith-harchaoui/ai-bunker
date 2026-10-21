"""Point LlamaIndex at the gateway.

Thin on purpose, and thinner than the code-agent kits for a reason that is
structural rather than stylistic. A code agent is somebody else's loop: the kit
has to reach into it for the things that happen *before a request exists* --
bounded file reads, skill injection, when to compact. In a framework you write
the loop, so those are yours already and a kit that tried to set them would be
guessing at an application it cannot see.

What is left is the part the framework cannot get right on its own: which
endpoint to call, and what context window to believe.

Everything load-bearing is still enforced server-side and cannot be switched
off here -- the charter is injected into every request, tool output is screened
for secrets and injection, dangerous commands are refused, and the session
floor is counted with the engine's own tokenizer. Deleting this file changes
where the requests go, not what the rules are.

    pip install llama-index-llms-openai-like

``OpenAILike`` rather than ``OpenAI``: the latter validates the model name
against OpenAI's own catalogue and refuses anything it does not recognise,
which is every model a sovereign deployment serves.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import os

from llama_index.llms.openai_like import OpenAILike

#: Deployment facts, rendered in by ``ai-bunker adopt`` and overridable from the
#: environment so one checkout can be pointed at a second gateway without an
#: edit. These are not secrets; a rendered kit is meant to be committable.
AI_BUNKER_URL = os.environ.get("AI_BUNKER_URL", "{{AI_BUNKER_URL}}")
AI_BUNKER_MODEL = os.environ.get("AI_BUNKER_MODEL", "{{AI_BUNKER_MODEL}}")

#: Declared BELOW what the engine serves. A client estimates its own tokens
#: with its own rule and under-counts; one measured session believed it was
#: under 32,768 and sent 40,433, and the server refused the whole request.
#: ``GET /v1/models`` publishes the figure the gateway expects, and raising
#: this past it means being refused eventually rather than immediately.
AI_BUNKER_DECLARED_CONTEXT = int(
    os.environ.get("AI_BUNKER_DECLARED_CONTEXT", "{{AI_BUNKER_DECLARED_CONTEXT}}")
)

#: From the environment only, never rendered into this file. The URL and the
#: model name are facts about a deployment; a key is a credential, and a
#: credential written into a file is a credential in a git history.
AI_BUNKER_API_KEY = os.environ.get("AI_BUNKER_API_KEY", "")

#: Low by default. A charter is a set of instructions to follow rather than a
#: prompt to riff on, and a model that paraphrases its rules has not followed
#: them. Rendered in like the rest, and a caller can still pass its own.
AI_BUNKER_TEMPERATURE = float(os.environ.get("AI_BUNKER_TEMPERATURE", "{{AI_BUNKER_TEMPERATURE}}"))


def make_model(**kwargs) -> OpenAILike:
    """Return a large language model (LLM) that talks to the gateway.

    Parameters
    ----------
    **kwargs
        Forwarded to :class:`~llama_index.llms.openai_like.OpenAILike`, so a
        caller can override anything without editing this file --
        ``is_function_calling_model=False`` for a model that has no tool
        support, for instance.

    Returns
    -------
    OpenAILike
        Usable anywhere LlamaIndex wants an LLM, including
        ``Settings.llm`` and ``FunctionAgent(llm=...)``.

    Examples
    --------
    >>> from llama_index.core import Settings  # doctest: +SKIP
    >>> Settings.llm = make_model()  # doctest: +SKIP
    """
    kwargs.setdefault("temperature", AI_BUNKER_TEMPERATURE)
    kwargs.setdefault("is_chat_model", True)
    kwargs.setdefault("is_function_calling_model", True)
    return OpenAILike(
        model=AI_BUNKER_MODEL,
        api_base=AI_BUNKER_URL,
        api_key=AI_BUNKER_API_KEY or "not-needed",
        context_window=AI_BUNKER_DECLARED_CONTEXT,
        **kwargs,
    )
