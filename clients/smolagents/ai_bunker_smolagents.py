"""Point smolagents at the gateway.

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

    pip install smolagents

One warning that belongs here rather than in the documentation: a
``CodeAgent`` executes the model's Python locally by default. The gateway
refuses dangerous *shell* commands because it sees them as tool calls before
they run, and it cannot see an ``exec`` inside the harness at all. Use
``executor_type="docker"`` (or ``"e2b"``) for anything that is not a toy, and
read the sandboxing guide. This is the one risk a gateway genuinely does not
cover.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

import os

try:
    from smolagents import OpenAIModel
except ImportError:  # older smolagents shipped it as OpenAIServerModel
    from smolagents import OpenAIServerModel as OpenAIModel

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


def make_model(**kwargs) -> OpenAIModel:
    """Return a model that talks to the gateway.

    Parameters
    ----------
    **kwargs
        Forwarded to the model, and from there to the completion call, so a
        caller can set ``max_tokens`` or anything else without editing this
        file.

    Returns
    -------
    OpenAIModel
        Usable anywhere smolagents wants a model, including
        ``CodeAgent(tools=[], model=...)`` and ``ToolCallingAgent``.

    Examples
    --------
    >>> from smolagents import ToolCallingAgent  # doctest: +SKIP
    >>> agent = ToolCallingAgent(tools=[], model=make_model())  # doctest: +SKIP
    """
    kwargs.setdefault("temperature", AI_BUNKER_TEMPERATURE)
    return OpenAIModel(
        model_id=AI_BUNKER_MODEL,
        api_base=AI_BUNKER_URL,
        api_key=AI_BUNKER_API_KEY or "not-needed",
        **kwargs,
    )
