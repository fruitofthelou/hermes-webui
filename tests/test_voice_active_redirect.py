"""Native redirect is not a safe substitute for lock-fenced Steer admission.

Agent.redirect may invoke provider abort callbacks or Codex I/O. Unadapted redirect-capable Agents fail closed; the WebUI-owned adapter is
covered by real-Agent offline tests. Preserve Stop/finalizing fences.
"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from tests.test_real_steer import _clear_caches, _make_handler, _captured_response


@pytest.mark.parametrize('registered', [True, False])
@pytest.mark.parametrize('phase,expected', [('running', False), ('finalizing', False), ('cancelling', False)])
def test_redirect_capability_does_not_bypass_fenced_steer(_clear_caches, monkeypatch, registered, phase, expected):
    from api import config as cfg
    from api.streaming import _handle_chat_steer, WEBUI_LOCAL_CHAT_BACKEND

    sid, stream_id = 'voice-redirect', 'voice-stream'
    agent = SimpleNamespace(session_id=sid, _supports_active_turn_redirect=True,
                            redirect=Mock(return_value=True), steer=Mock(return_value=True))
    monkeypatch.setattr(cfg, 'STREAM_SESSION_OWNERS', {stream_id: sid})
    monkeypatch.setattr(cfg, 'AGENT_INSTANCES', {stream_id: agent} if registered else {})
    cfg.SESSION_AGENT_CACHE[sid] = (agent, 'sig')
    cfg.STREAMS[stream_id] = object()
    cfg.ACTIVE_RUNS[stream_id] = {'session_id': sid, 'backend': WEBUI_LOCAL_CHAT_BACKEND, 'phase': phase}
    with patch('api.streaming.get_session', return_value=SimpleNamespace(active_stream_id=stream_id)):
        handler = _make_handler()
        _handle_chat_steer(handler, {'session_id': sid, 'text': 'Use Brooklyn instead'})
    assert _captured_response(handler)['accepted'] is expected
    agent.redirect.assert_not_called()
    agent.steer.assert_not_called()
    if phase == 'running':
        assert _captured_response(handler)['fallback'] == 'immediate_redirect_unsupported'
