"""Server-initiated wakeup turns must keep the session's own model (custom fix).

Async ``delegate_task`` completions and background-process notices re-enter a
chat through ``start_session_turn`` on a bare background thread. That thread has
no request-profile context, so before this fix the model lookup ran against the
DEFAULT profile's catalog. For a chat on a named profile whose saved model is
provider-qualified (``@anthropic:claude-opus-5-5``), a default catalog that does
not list the provider made the resolver substitute the default profile's
default model -- silently moving the conversation to another provider.

Upstream report: nesquena/hermes-webui#8096 (closed "not planned").

The fix mirrors what the streaming worker already does (api/streaming.py):
  A. resolve the wakeup model inside
     ``profiles.profile_scope_for_detached_worker(session.profile)``;
  B. treat the session's saved ``model_explicit_pick_signature`` as a deliberate
     pick and pass ``explicit_model_pick=True`` to the resolver.

The resolver itself runs for real in these tests; only the catalog, session
lookup, workspace, profile secret-env loading and the turn launch are stubbed.
"""
from __future__ import annotations

import contextlib
import types

import pytest

SAVED_MODEL = "@anthropic:claude-opus-5-5"
SAVED_PROVIDER = "anthropic"
DEFAULT_PROFILE_DEFAULT = "glm-5.3-flash-abliterated"
MOLTY_DEFAULT = "gpt-6-luna"


def _catalog(active_provider, default_model, provider_ids):
    return {
        "active_provider": active_provider,
        "default_model": default_model,
        "groups": [
            {"provider": pid, "provider_id": pid, "models": [{"id": f"{pid}-model", "label": pid}]}
            for pid in provider_ids
        ],
    }


# Default profile: Anthropic NOT listed (mirrors the 2026-10-19 incident).
DEFAULT_CATALOG = _catalog(
    "experiential-ai", DEFAULT_PROFILE_DEFAULT, ["experiential-ai", "codex-lb", "openrouter"]
)
# Named profile "molty": Anthropic listed.
MOLTY_CATALOG = _catalog("codex-lb", MOLTY_DEFAULT, ["codex-lb", "experiential-ai", "openrouter", "anthropic"])
# Named profile whose catalog ALSO lacks the provider (stale-pick repair case).
MOLTY_CATALOG_NO_ANTHROPIC = _catalog("codex-lb", MOLTY_DEFAULT, ["codex-lb", "openrouter"])


@pytest.fixture
def harness(monkeypatch):
    from api import models as models_mod
    from api import profiles as profiles_mod
    from api import routes as routes_mod

    state = {
        "catalogs": {"molty": MOLTY_CATALOG},
        "catalog_profiles_seen": [],
        "start_run_kwargs": None,
    }

    def _make_session(*, profile="molty", explicit=True, model=SAVED_MODEL, provider=SAVED_PROVIDER):
        sig = models_mod.model_explicit_pick_signature(model, provider) if explicit else None
        s = types.SimpleNamespace(
            session_id="sess-wakeup",
            model=model,
            model_provider=provider,
            model_explicit_pick_signature=sig,
            profile=profile,
            workspace="/tmp/ws-wakeup",
            process_wakeup_pause={},
        )
        s.save = lambda **_kw: None
        state["session"] = s
        monkeypatch.setattr(routes_mod, "get_session", lambda _sid: state["session"])
        return s

    def _fake_get_available_models(*, prefer_cache=False, force_refresh=False):
        name = profiles_mod.get_active_profile_name()
        state["catalog_profiles_seen"].append(name)
        return state["catalogs"].get(name, DEFAULT_CATALOG)

    monkeypatch.setattr(routes_mod, "get_available_models", _fake_get_available_models)
    monkeypatch.setattr(
        routes_mod, "_resolve_chat_workspace_with_recovery", lambda _s, _req: "/tmp/ws-wakeup"
    )
    # No profile config.yaml in the isolated test home: no profile defaults.
    monkeypatch.setattr(routes_mod, "_read_profile_model_config", lambda _s, _p: (None, None, None))

    # Keep the REAL request-profile TLS binding (that is what selects the
    # catalog) but never load a named profile's .env secrets in tests.
    @contextlib.contextmanager
    def _no_env(*_a, **_kw):
        yield

    monkeypatch.setattr(profiles_mod, "profile_env_for_background_worker", _no_env)

    def _capture_start_run(s, **kwargs):
        state["start_run_kwargs"] = kwargs
        return {"_status": 200, "stream_id": "stream-wakeup", "session_id": s.session_id}

    monkeypatch.setattr(routes_mod, "_start_run", _capture_start_run)

    import api.background_process as bp_mod

    monkeypatch.setattr(bp_mod, "get_session_channel", lambda _sid: None)

    # The wakeup thread starts with NO request profile, like the drain thread.
    profiles_mod.clear_request_profile()
    yield types.SimpleNamespace(
        routes=routes_mod, profiles=profiles_mod, state=state, make_session=_make_session
    )
    profiles_mod.clear_request_profile()


def _launched(h):
    kw = h.state["start_run_kwargs"]
    assert kw is not None, "wakeup turn was not launched"
    return kw["model"], kw["model_provider"], kw["normalized_model"]


def test_wakeup_keeps_explicitly_picked_model_on_named_profile(harness):
    """Reproduction of the 2026-10-19 incident: Opus pick must survive."""
    harness.make_session(explicit=True)
    resp = harness.routes.start_session_turn("sess-wakeup", "[ASYNC DELEGATION BATCH COMPLETE]")
    assert resp["_status"] == 200
    model, provider, normalized = _launched(harness)
    assert (model, provider) == (SAVED_MODEL, SAVED_PROVIDER)
    assert normalized is False
    assert DEFAULT_PROFILE_DEFAULT not in str(model)


def test_explicit_pick_alone_survives_a_catalog_missing_the_provider(harness):
    """Part B on its own: even when the profile's catalog lacks the provider."""
    harness.state["catalogs"]["molty"] = MOLTY_CATALOG_NO_ANTHROPIC
    harness.make_session(explicit=True)
    harness.routes.start_session_turn("sess-wakeup", "wakeup")
    model, provider, normalized = _launched(harness)
    assert (model, provider, normalized) == (SAVED_MODEL, SAVED_PROVIDER, False)


def test_wakeup_model_lookup_uses_the_session_profile_catalog(harness):
    """Part A on its own: no explicit-pick signature, so only the profile-scoped
    catalog (which lists Anthropic) can keep the saved model."""
    harness.make_session(explicit=False)
    harness.routes.start_session_turn("sess-wakeup", "wakeup")
    model, provider, normalized = _launched(harness)
    assert "molty" in harness.state["catalog_profiles_seen"]
    assert (model, provider, normalized) == (SAVED_MODEL, SAVED_PROVIDER, False)


def test_stale_pick_on_unavailable_provider_is_still_repaired(harness):
    """A non-explicit pick whose provider is absent from the session's OWN
    profile catalog is still repaired -- to that profile's default, never the
    default profile's model."""
    harness.state["catalogs"]["molty"] = MOLTY_CATALOG_NO_ANTHROPIC
    harness.make_session(explicit=False)
    harness.routes.start_session_turn("sess-wakeup", "wakeup")
    model, _provider, normalized = _launched(harness)
    assert normalized is True
    assert model == MOLTY_DEFAULT
    assert model != DEFAULT_PROFILE_DEFAULT


def test_mismatched_signature_is_not_treated_as_explicit(harness):
    s = harness.make_session(explicit=True)
    s.model_explicit_pick_signature = "@anthropic:some-older-model\x1fanthropic"
    harness.state["catalogs"]["molty"] = MOLTY_CATALOG_NO_ANTHROPIC
    harness.routes.start_session_turn("sess-wakeup", "wakeup")
    model, _provider, normalized = _launched(harness)
    assert normalized is True and model == MOLTY_DEFAULT


def test_profile_scope_is_restored_after_the_wakeup(harness):
    harness.make_session(explicit=True)
    harness.routes.start_session_turn("sess-wakeup", "wakeup")
    assert getattr(harness.profiles._tls, "profile", None) is None


def test_profile_scope_is_restored_when_resolution_raises(harness, monkeypatch):
    harness.make_session(explicit=True)

    def _boom(*_a, **_kw):
        raise RuntimeError("resolver failed")

    monkeypatch.setattr(harness.routes, "_resolve_compatible_session_model_state", _boom)
    with pytest.raises(RuntimeError):
        harness.routes.start_session_turn("sess-wakeup", "wakeup")
    assert getattr(harness.profiles._tls, "profile", None) is None


def test_default_profile_session_is_unchanged(harness):
    """A session with no named profile resolves exactly as before."""
    harness.make_session(profile=None, explicit=False, model="gpt-6-luna", provider="codex-lb")
    harness.routes.start_session_turn("sess-wakeup", "wakeup")
    model, provider, normalized = _launched(harness)
    assert (model, provider, normalized) == ("gpt-6-luna", "codex-lb", False)
    assert getattr(harness.profiles._tls, "profile", None) is None
