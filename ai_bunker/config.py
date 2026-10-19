"""
Gateway configuration.

Loaded through ``os-helper``'s :func:`get_config`, which has a defined
fallback order -- a config file, then ``.env`` files, then the process
environment -- so a deployment can put its API key wherever its platform makes
that safe without the gateway caring which.

The sovereignty posture is a configuration fact, not a slogan: a deployment
with no ``remote`` provider cannot reach the internet at inference time, and
:meth:`Settings.sovereign` says so rather than leaving it to be inferred.

Author
------
Warith Harchaoui
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import os_helper as osh
import yaml

from ai_bunker.budget import DECLARED_FRACTION, MIN_WORKING_TOKENS

DEFAULT_CONFIG = "config/gateway.yaml"


@dataclass
class Upstream:
    """One place the gateway can send a request."""

    name: str
    base_url: str
    api_key: str = ""
    #: What the engine actually serves. The budget is measured against this.
    served_context: int = 131_072
    #: True when the request leaves the local network. Recorded so every
    #: routed request can be logged as such, rather than discovered later.
    remote: bool = False

    @property
    def tokenize_url(self) -> str:
        root = self.base_url.rstrip("/")
        return root[: -len("/v1")] if root.endswith("/v1") else root


@dataclass
class Settings:
    """Everything the gateway needs to run."""

    api_key: str = ""
    charter_dir: str = "charter"
    rules_dir: str = "charter/rules"
    upstreams: dict[str, Upstream] = field(default_factory=dict)
    #: Model name -> upstream name. An unknown model falls back to ``default``,
    #: which is what makes a client that asks for `gpt-5.2` work against a
    #: local model without the client being reconfigured.
    routes: dict[str, str] = field(default_factory=dict)
    #: **Need** -> upstream name. The other way to route, and the one the
    #: 80/20 strategy actually describes: a request that declares what it is
    #: for ("code", "heavy reasoning") goes where that need is best served,
    #: rather than where a hardcoded model name happens to point.
    #:
    #: A client declares its need with ``X-AI-Bunker-Need``, or by asking for
    #: a model whose name IS a need. Needs are matched before model names,
    #: because a need is a statement about the work and a model name is an
    #: implementation detail the client should not have had to know.
    needs: dict[str, str] = field(default_factory=dict)
    #: Model to request upstream, per need. Without this the client's own
    #: model string is forwarded, which is usually right when the need and the
    #: upstream already agree.
    need_models: dict[str, str] = field(default_factory=dict)
    default_upstream: str = ""
    compaction_reserve: int = 0
    declared_fraction: float = DECLARED_FRACTION
    min_working_tokens: int = MIN_WORKING_TOKENS
    mark_provenance: bool = True
    enforce_budget: bool = True
    enforce_commands: bool = True
    audit_log: str = ""

    @property
    def sovereign(self) -> bool:
        """Whether any configured route can leave the local network."""
        return not any(u.remote for u in self.upstreams.values())

    def route(self, model: str, need: str = "") -> tuple[Upstream, str, str]:
        """Resolve a request to an upstream, a model, and the reason why.

        Three ways in, tried in this order:

        1. A declared **need** (``X-AI-Bunker-Need``). Most specific: the
           client said what the work is, which is the only thing it reliably
           knows. This is the 80/20 split made configurational -- routine work
           to the local model, heavy reasoning to a premium route -- without
           any client having to learn a model name.
        2. The **model name** matching a configured need, so a client with no
           custom-header support can still declare one by asking for
           ``"code"`` as its model.
        3. The **model name** matching a route, then the default.

        The reason is returned alongside, because a request that silently went
        somewhere other than the operator expected is the failure that costs
        money, and a log line naming the rule that sent it is the cheapest
        possible fix.

        Returns
        -------
        (upstream, model, why)
            The model is the one to request upstream, which may differ from
            what the client asked for when a need maps to a specific model.
        """
        asked = (need or "").strip().lower()
        if asked and asked in self.needs:
            name = self.needs[asked]
            resolved = self.need_models.get(asked, model)
            why = f"need {asked!r}"
        elif model.strip().lower() in self.needs:
            key = model.strip().lower()
            name = self.needs[key]
            resolved = self.need_models.get(key, model)
            why = f"model name {model!r} is a declared need"
        elif model in self.routes:
            name, resolved, why = self.routes[model], model, f"route for {model!r}"
        else:
            name, resolved, why = self.default_upstream, model, "the default upstream"
            if asked:
                # Silently ignoring a need is how an operator discovers, from
                # an invoice, that nothing was routing the way they thought.
                osh.warning(
                    f"[gateway] need {asked!r} is not configured; "
                    f"falling back to {name or 'nothing'}. Known needs: "
                    f"{', '.join(sorted(self.needs)) or 'none'}."
                )

        osh.check(
            bool(name) and name in self.upstreams,
            f"No upstream for model {model!r} (need {asked or 'none'}) and no usable "
            f"default. Configured upstreams: {', '.join(sorted(self.upstreams)) or 'none'}.",
        )
        return self.upstreams[name], resolved, why

    def upstream_for(self, model: str) -> Upstream:
        """Resolve a model name to an upstream. Kept for callers with no need."""
        return self.route(model)[0]


def _from_environment(key: str, label: str) -> str:
    """Resolve one key through os-helper's fallback order, or return empty.

    ``get_config`` raises when a key cannot be resolved anywhere, which is
    right for a program that cannot run without it and wrong here: a gateway
    with no API key configured is an unauthenticated gateway, which is a
    legitimate choice on a trusted network and something `doctor` should
    report rather than something startup should refuse.
    """
    import contextlib
    import io
    import os

    # Check the environment first. get_config's unresolved path prints to
    # stderr before raising, and an absent optional key is not something a
    # user needs to read on every single command.
    if os.environ.get(key):
        return str(os.environ[key])
    try:
        # Swallow the message as well as the exception. An unauthenticated
        # gateway is a legitimate choice on a trusted network, so "this key is
        # not set" is a state the caller reports (`doctor` does), not a line
        # every unrelated command has to print.
        with contextlib.redirect_stderr(io.StringIO()):
            return str(osh.get_config([key], label).get(key) or "")
    except Exception as exc:  # unresolved is a state, not a crash
        osh.debug(f"[gateway] {key} not set ({type(exc).__name__}: {exc}).")
        return ""


def _as_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return fallback


def load_settings(path: str | Path | None = None) -> Settings:
    """Load gateway settings from YAML, with environment overrides.

    Secrets are read through ``os-helper``'s :func:`get_config` so that an API
    key can live in the file, in a ``.env``, or in the environment, and the
    gateway does not have an opinion about which. A key written literally into
    the YAML is accepted and warned about: it is the spelling most likely to
    reach a git history.
    """
    p = Path(path or DEFAULT_CONFIG)
    raw: dict[str, Any] = {}
    if osh.file_exists(str(p)):
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    else:
        osh.debug(f"[gateway] no config at {p}; using defaults and the environment.")

    gateway = raw.get("gateway") or {}
    api_key = str(gateway.get("api_key") or "")
    if api_key and not api_key.startswith("${"):
        osh.warning(
            f"[gateway] {p} carries a literal api_key. Prefer ${{AI_BUNKER_API_KEY}} "
            "or a .env file: a key written into a config file is the spelling most "
            "likely to end up in a git history."
        )
    if not api_key or api_key.startswith("${"):
        api_key = _from_environment("AI_BUNKER_API_KEY", "ai-bunker gateway")

    upstreams: dict[str, Upstream] = {}
    for name, spec in (raw.get("upstreams") or {}).items():
        spec = spec or {}
        key = str(spec.get("api_key") or "")
        if key.startswith("${") and key.endswith("}"):
            key = _from_environment(key[2:-1], f"upstream {name}")
        upstreams[name] = Upstream(
            name=name,
            base_url=str(spec.get("base_url") or ""),
            api_key=key,
            served_context=int(spec.get("served_context") or 131_072),
            remote=_as_bool(spec.get("remote"), False),
        )

    budget = raw.get("budget") or {}
    enforcement = raw.get("enforcement") or {}

    settings = Settings(
        api_key=api_key,
        charter_dir=str(raw.get("charter_dir") or "charter"),
        rules_dir=str(raw.get("rules_dir") or "charter/rules"),
        upstreams=upstreams,
        routes=dict(raw.get("routes") or {}),
        needs={
            str(k).strip().lower(): str(v.get("upstream") if isinstance(v, dict) else v)
            for k, v in (raw.get("needs") or {}).items()
        },
        need_models={
            str(k).strip().lower(): str(v["model"])
            for k, v in (raw.get("needs") or {}).items()
            if isinstance(v, dict) and v.get("model")
        },
        default_upstream=str(raw.get("default_upstream") or next(iter(upstreams), "")),
        compaction_reserve=int(budget.get("compaction_reserve") or 0),
        declared_fraction=float(budget.get("declared_fraction") or DECLARED_FRACTION),
        min_working_tokens=int(budget.get("min_working_tokens") or MIN_WORKING_TOKENS),
        mark_provenance=_as_bool(enforcement.get("mark_provenance"), True),
        enforce_budget=_as_bool(enforcement.get("budget"), True),
        enforce_commands=_as_bool(enforcement.get("commands"), True),
        audit_log=str(raw.get("audit_log") or ""),
    )

    if not settings.sovereign:
        remote = [u.name for u in settings.upstreams.values() if u.remote]
        osh.warning(
            f"[gateway] {', '.join(remote)} routes off the local network. Requests sent "
            "there leave your infrastructure; every one is logged as such."
        )
    return settings
