"""Offline integration with the installed AIAgent, not a steer/redirect mock.

Set HERMES_WEBUI_AGENT_DIR/PYTHONPATH to the Agent checkout for this suite.
"""
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api import config, streaming
from api.voice_correction import correction_agent_class, drain_corrections
from tests.test_real_steer import _captured_response, _make_handler
from tests.test_steer_cancel_ordering import scene as _ordering_scene

scene = _ordering_scene


@pytest.fixture
def real_agent(monkeypatch):
    from run_agent import AIAgent
    cls = correction_agent_class(AIAgent)
    # Offline control-plane fixture. Native interrupt/clear/drain/steer methods
    # and the native conversation redirect consumer are exercised unchanged.
    agent = cls.__new__(cls)
    agent.session_id = 'original'
    agent.api_mode = 'chat_completions'
    agent.platform = 'webui'
    agent._supports_active_turn_redirect = True
    agent._pending_redirect_lock = threading.Lock()
    agent._pending_steer_lock = threading.Lock()
    agent._pending_redirect = agent._pending_steer = None
    agent._model_request_active = threading.Event()
    agent._model_request_active.set()
    agent._interrupt_requested = False
    agent._interrupt_message = None
    agent._hard_interrupt_requested = threading.Event()
    agent._execution_thread_id = None
    agent._active_children_lock = threading.Lock()
    agent._active_children = []
    agent.quiet_mode = True
    return agent


def install(scene, real_agent, registered):
    lock, _ = scene
    config.AGENT_INSTANCES.clear()
    if registered:
        config.AGENT_INSTANCES['run'] = real_agent
    config.SESSION_AGENT_CACHE['original'] = (real_agent, 'sig')
    return lock


def submit():
    handler = _make_handler()
    streaming._handle_chat_steer(handler, {'session_id': 'original', 'text': 'Use Brooklyn instead'})
    return _captured_response(handler)


@pytest.mark.parametrize('registered', [True, False])
def test_real_agent_model_correction_is_immediate(scene, real_agent, registered):
    install(scene, real_agent, registered)
    assert submit()['accepted'] is True
    assert real_agent._pending_redirect == 'Use Brooklyn instead'
    assert real_agent._pending_steer is None
    assert real_agent._interrupt_requested is True
    assert real_agent.clear_interrupt(preserve_redirect=True) is True
    assert real_agent._drain_pending_redirect() == 'Use Brooklyn instead'


@pytest.mark.parametrize('registered', [True, False])
def test_real_agent_stop_first_rejects_correction(scene, real_agent, registered):
    install(scene, real_agent, registered)
    assert streaming.cancel_stream('run') is True
    assert submit()['accepted'] is False
    assert real_agent._pending_redirect is None
    assert real_agent.clear_interrupt(preserve_redirect=True) is False


@pytest.mark.parametrize('registered', [True, False])
def test_real_agent_correction_first_stop_dominates(scene, real_agent, registered):
    install(scene, real_agent, registered)
    assert submit()['accepted'] is True
    assert streaming.cancel_stream('run') is True
    assert real_agent._pending_redirect is None
    assert real_agent._interrupt_requested is True
    assert real_agent.clear_interrupt(preserve_redirect=True) is False


@pytest.mark.parametrize('registered', [True, False])
@pytest.mark.parametrize('raises', [False, True])
def test_abort_never_runs_under_admission_lock(scene, real_agent, registered, raises):
    lock = install(scene, real_agent, registered)
    def abort(reason):
        assert lock.owner != threading.get_ident()
        if raises:
            raise RuntimeError('offline abort failure')
    real_agent._active_request_abort = abort
    result = submit()
    assert result == {'accepted': False, 'fallback': 'immediate_redirect_unsupported', 'stream_id': 'run'}
    assert real_agent._pending_redirect is None
    assert streaming.cancel_stream('run') is True


@pytest.mark.parametrize('native', [True, False])
def test_codex_fails_closed_even_without_native_steer(scene, real_agent, native):
    install(scene, real_agent, True)
    real_agent.api_mode = 'codex_app_server'
    real_agent._codex_session = SimpleNamespace(request_steer=Mock()) if native else None
    assert submit()['fallback'] == 'immediate_redirect_unsupported'
    assert real_agent._pending_redirect is None
    if native:
        real_agent._codex_session.request_steer.assert_not_called()


@pytest.mark.parametrize('registered', [True, False])
def test_finalizing_rejects_and_native_slots_drain(scene, real_agent, registered):
    install(scene, real_agent, registered)
    assert submit()['accepted'] is True
    config.ACTIVE_RUNS['run']['phase'] = 'finalizing'
    assert submit()['fallback'] == 'not_running'
    assert drain_corrections(real_agent) == 'Use Brooklyn instead'
    assert drain_corrections(real_agent) is None


def test_compression_rotated_registered_identity(scene, real_agent):
    install(scene, real_agent, True)
    real_agent.session_id = 'continuation'
    config.SESSION_AGENT_CACHE['original'] = (Mock(session_id='original'), 'sig')
    assert submit()['accepted'] is True
    assert real_agent._drain_pending_redirect() == 'Use Brooklyn instead'
    config.SESSION_AGENT_CACHE['original'][0].steer.assert_not_called()


@pytest.mark.parametrize('mode', ['chat_completions', 'codex_responses', 'anthropic_messages'])
def test_explicit_supported_modes(scene, real_agent, mode):
    install(scene, real_agent, True)
    real_agent.api_mode = mode
    assert submit()['accepted'] is True
    assert submit()['accepted'] is True
    assert real_agent._drain_pending_redirect() == (
        'Use Brooklyn instead\n\n[Additional user correction]\nUse Brooklyn instead')


@pytest.mark.parametrize('mode', ['bedrock_converse', 'unknown', None])
def test_unknown_or_unverified_modes_fail_closed(scene, real_agent, mode):
    install(scene, real_agent, True)
    real_agent.api_mode = mode
    assert submit()['fallback'] == 'immediate_redirect_unsupported'
    assert real_agent._pending_redirect is None


def test_adapter_preserves_native_constructor_and_is_used_by_webui(real_agent):
    import inspect
    from run_agent import AIAgent
    assert inspect.signature(type(real_agent).__init__) == inspect.signature(AIAgent.__init__)
    assert issubclass(streaming._get_ai_agent(), type(real_agent))



@pytest.mark.parametrize('first', ['correction', 'finalize'])
def test_real_final_drain_ordering(scene, real_agent, first):
    from concurrent.futures import ThreadPoolExecutor
    lock = install(scene, real_agent, True)
    reached, release = threading.Event(), threading.Event()
    def finalize():
        with config.STREAMS_LOCK:
            config.ACTIVE_RUNS['run']['phase'] = 'finalizing'
            reached.set()
            assert release.wait(5)
        return drain_corrections(real_agent)
    if first == 'correction':
        assert submit()['accepted'] is True
    with ThreadPoolExecutor(max_workers=2) as pool:
        settlement = pool.submit(finalize)
        assert reached.wait(5)
        late = pool.submit(submit)
        assert lock.contender.wait(5)
        release.set()
        assert late.result(5)['fallback'] == 'not_running'
        assert settlement.result(5) == ('Use Brooklyn instead' if first == 'correction' else None)
    assert drain_corrections(real_agent) is None


def test_tool_boundary_preserves_native_steer(scene, real_agent):
    install(scene, real_agent, True)
    real_agent._executing_tools = True
    assert submit()['accepted'] is True
    assert real_agent._pending_redirect is None
    assert real_agent._interrupt_requested is False
    assert real_agent._drain_pending_steer() == 'Use Brooklyn instead'

@pytest.mark.parametrize('registered', [True, False])
@pytest.mark.parametrize('first', ['stop', 'correction'])
def test_real_agent_deterministic_control_edge(scene, real_agent, registered, first):
    from concurrent.futures import ThreadPoolExecutor
    lock = install(scene, real_agent, registered)
    reached, release = threading.Event(), threading.Event()
    if first == 'correction':
        native_admit = type(real_agent)._webui_admit_correction
        # Class-level test barrier, not a production instance callback patch.
        def gate(self, text):
            reached.set()
            assert release.wait(5)
            return native_admit(self, text)
        type(real_agent)._webui_admit_correction = gate
        action = submit
        contender = lambda: streaming.cancel_stream('run')
    else:
        native_publish = streaming.update_active_run
        def gate(*args, **kwargs):
            reached.set()
            assert release.wait(5)
            return native_publish(*args, **kwargs)
        streaming.update_active_run = gate
        action = lambda: streaming.cancel_stream('run')
        contender = submit
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            earlier = pool.submit(action)
            assert reached.wait(5)
            later = pool.submit(contender)
            assert lock.contender.wait(5)
            release.set()
            a, b = earlier.result(5), later.result(5)
        assert (a if first == 'correction' else b)['accepted'] is (first == 'correction')
        assert real_agent._pending_redirect is None
        assert real_agent.clear_interrupt(preserve_redirect=True) is False
    finally:
        release.set()
        if first == 'correction':
            type(real_agent)._webui_admit_correction = native_admit
        else:
            streaming.update_active_run = native_publish


def test_native_redirect_consumer_keeps_prefix_and_roles(scene, real_agent):
    from agent.conversation_loop import _apply_active_turn_redirect
    install(scene, real_agent, True)
    messages = [{'role': 'user', 'content': 'Original task'}]
    original = dict(messages[0])
    real_agent._current_streamed_assistant_text = 'Visible partial reply'
    assert submit()['accepted'] is True
    assert real_agent.clear_interrupt(preserve_redirect=True)
    _apply_active_turn_redirect(real_agent, messages, real_agent._drain_pending_redirect())
    assert messages[0] == original
    assert [m['role'] for m in messages] == ['user', 'assistant', 'user']
    assert messages[-1]['content'] == 'Use Brooklyn instead'
    assert messages[-2]['content'] == 'Visible partial reply'


def test_stop_abort_blocking_does_not_hold_registry_lock(scene, real_agent):
    from concurrent.futures import ThreadPoolExecutor
    install(scene, real_agent, True)
    entered, release = threading.Event(), threading.Event()
    def blocking_abort(reason):
        entered.set()
        assert release.wait(5)
    real_agent._active_request_abort = blocking_abort
    with ThreadPoolExecutor(max_workers=1) as pool:
        stopping = pool.submit(streaming.cancel_stream, 'run')
        try:
            assert entered.wait(5)
            assert submit()['accepted'] is False
            assert real_agent.clear_interrupt(preserve_redirect=True) is False
        finally:
            release.set()
        assert stopping.result(5) is True


def test_real_interruptible_worker_observes_admitted_correction(scene, real_agent, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from agent import chat_completion_helpers as helpers
    install(scene, real_agent, True)
    entered, release = threading.Event(), threading.Event()
    def offline_dispatch(agent, kwargs, **unused):
        entered.set()
        assert release.wait(5)
        return SimpleNamespace(choices=[])
    monkeypatch.setattr(helpers, '_dispatch_nonstreaming_api_request', offline_dispatch)
    real_agent._compute_non_stream_stale_timeout = lambda kwargs: 900
    real_agent._touch_activity = lambda *args: None
    real_agent._close_request_openai_client = lambda *args, **kwargs: None
    real_agent._record_interrupted_provider_wait = lambda *args, **kwargs: None
    real_agent.model = 'offline-test'
    real_agent.provider = 'offline'
    real_agent.base_url = 'http://127.0.0.1:1'
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            request = pool.submit(helpers.interruptible_api_call, real_agent,
                                  {'model': 'offline-test', 'messages': []})
            assert entered.wait(5)
            assert submit()['accepted'] is True
            with pytest.raises(InterruptedError):
                request.result(4)
    finally:
        release.set()
    assert real_agent.clear_interrupt(preserve_redirect=True)
    assert real_agent._drain_pending_redirect() == 'Use Brooklyn instead'
