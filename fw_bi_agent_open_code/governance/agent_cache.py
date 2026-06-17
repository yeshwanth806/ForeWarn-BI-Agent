"""
Per-request agent cache — BYOK-safe construction of the ReAct agent.

Companion code for §6 of "Integrating AI into a Live BI Platform — The
Patterns That Actually Held Up". See the article for the architectural
context; this file shows the cache-key discipline that keeps user-supplied
API keys from leaking across tenants.

Behavior summary:
  - The ForeWarn-managed-key path caches the built agent across requests;
    the cost of constructing one is non-trivial.
  - The BYOK path (user-supplied API key in the request) rebuilds the agent
    fresh for every request, never caches it, and never reuses it for any
    other user. The `using_user_key` boolean is part of the cache key so the
    two paths cannot collide.

The non-obvious bit:
  `using_user_key` is in the cache *key* AND gates the cache *write*. Either
  alone would be wrong:
    - In the key only:  we'd never write a user-key entry, but we'd also do
      a needless dict lookup on every BYOK request.
    - Gating writes only:  two BYOK sessions could collide if `model_id` and
      `groups` matched and one had cached before the user-key check landed.
  The pairing is intentional.

Extracted from production code in ForeWarn-BI-Agent and lightly cleaned for
publication. `filter_tools` and provider detection are implemented in full;
the actual ChatModel / agent construction (`_build_chat_model`,
`create_react_agent`) is a thin adapter over LangChain / LangGraph, lazily
imported so the cache logic and provider detection run without those SDKs
installed. To exercise the cache-key discipline without any provider keys,
monkeypatch `_build_chat_model` and `create_react_agent` with fakes.
"""

# Per-request agent cache keyed by (model_id, frozenset(group_names), using_user_key).
# Production bounds this with a TTL/size-capped cache; kept as a plain dict here
# to keep the cache-key discipline — the point of this file — in focus.
_agent_cache: dict[tuple, object] = {}


def _build_agent_for_groups(model_id: str, all_tools, groups: frozenset[str],
                            api_key: str = ""):
    """Build (or reuse) a ReAct agent bound only to the tools in `groups`."""
    using_user_key = bool(api_key)
    cache_key = (model_id, groups, using_user_key)
    cached = _agent_cache.get(cache_key)
    if cached is not None:
        return cached

    selected = filter_tools(all_tools, set(groups))
    llm = _build_chat_model(model_id, api_key)
    agent = create_react_agent(llm, selected)

    # Only cache the ForeWarn-managed-key variants; user-key agents are
    # per-session by design — holding them forever would mix a user's key
    # into an agent another user could hit.
    if not using_user_key:
        _agent_cache[cache_key] = agent
    return agent


# ---------------------------------------------------------------------
# Tool filtering and provider detection — implemented in full.
# ---------------------------------------------------------------------

def _group_of(tool):
    """A tool's group, whether it's an object with `.group` or a dict."""
    if isinstance(tool, dict):
        return tool.get("group")
    return getattr(tool, "group", None)


def filter_tools(all_tools, group_names: set[str]):
    """Return only the tools whose group is in `group_names`."""
    return [t for t in all_tools if _group_of(t) in group_names]


def detect_provider(model_id: str) -> str:
    """Map a model_id to its provider by prefix — the same dispatch the UI's
    single model dropdown relies on."""
    mid = model_id.lower()
    if mid.startswith(("gemini", "models/gemini")):
        return "google"
    if mid.startswith(("gpt", "o1", "o3", "o4", "chatgpt")):
        return "openai"
    if mid.startswith("claude"):
        return "anthropic"
    raise ValueError(f"unknown provider for model_id {model_id!r}")


# ---------------------------------------------------------------------
# External boundary: ChatModel / agent construction.
#
# Provider detection above is fully real; the SDK construction below is a
# thin adapter. Imports are lazy so importing this module (and exercising
# the cache-key discipline with fakes) needs no provider SDKs and no keys.
# `api_key=""` means use the ForeWarn-managed env key for that provider.
# ---------------------------------------------------------------------

def _build_chat_model(model_id: str, api_key: str = ""):
    """Construct the LangChain ChatModel for `model_id` (provider by prefix)."""
    provider = detect_provider(model_id)
    key = api_key or None  # None -> the SDK reads the managed key from env
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model_id, api_key=key)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model_id, google_api_key=key)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model_id, api_key=key)
    raise ValueError(f"no ChatModel adapter for provider {provider!r}")


def create_react_agent(llm, tools):
    """Build a ReAct agent — delegates to LangGraph's prebuilt factory."""
    from langgraph.prebuilt import create_react_agent as _build
    return _build(llm, tools)
