"""Voice consumes structured run evidence, not error-looking prose."""
import pytest
from api.routes import _voice_task_outcome
from api.streaming import _classify_provider_error


def row(event, payload=None, seq=1):
    return {'event': event, 'payload': payload or {}, 'terminal': True, 'event_id': f'run:{seq}'}


@pytest.mark.parametrize('message,code', [
    ('insufficient_quota credits exhausted', 'quota_exhausted'),
    ('HTTP 429 rate limit', 'rate_limit'),
    ('HTTP 404 Model blocked by guardrail: 2 endpoints excluded', 'policy_blocked'),
    ('HTTP 401 unauthorized', 'auth_mismatch'),
    ('HTTP 404 model not found', 'model_not_found'),
    ('request timed out', 'timeout'),
    ('HTTP 503 backend exploded', 'backend_error'),
])
def test_structured_error_never_success(message, code):
    result = _voice_task_outcome([row('apperror', {'message': message, 'type': 'error'}), row('stream_end', seq=2)])
    assert result == {'status': 'failed', 'code': code, 'stage': 'terminal_journal', 'event_id': 'run:1'}
    assert message not in str(result)


@pytest.mark.parametrize('events,malformed', [([], 0), ([row('stream_end')], 0), ([row('done')], 1)])
def test_missing_transport_only_or_corrupt_evidence_is_unknown(events, malformed):
    assert _voice_task_outcome(events, malformed=malformed)['status'] == 'unconfirmed'


@pytest.mark.parametrize('flag', ['_error', '_interrupted', '_tool_limit_reached'])
def test_done_error_snapshot_is_not_success(flag):
    assert _voice_task_outcome([row('done', {'session': {'messages': [{'role': 'assistant', 'content': 'Error', flag: True}]}})])['status'] == 'failed'


def test_done_success_is_not_free_text_classified():
    assert _voice_task_outcome([row('done', {'session': {'messages': [{'role': 'assistant', 'content': 'Quota, policy, model not found, HTTP 401 and timeout are error categories.'}]}}), row('stream_end', seq=2)])['status'] == 'succeeded'
    assert _voice_task_outcome([row('cancel')])['status'] == 'cancelled'


@pytest.mark.parametrize('active,malformed,expected', [(False, 0, 'failed'), (False, 1, 'unconfirmed'), (True, 0, 'running')])
def test_stream_status_projects_journal_outcome(monkeypatch, active, malformed, expected):
    from urllib.parse import urlparse
    from api import routes, run_journal
    from tests.test_real_steer import _make_handler, _captured_response

    stream = 'voice-outcome-stream'
    monkeypatch.setattr(routes, 'STREAMS', {stream: object()} if active else {})
    monkeypatch.setattr(routes, '_stream_id_visible_to_request_profile', lambda *_: True)
    monkeypatch.setattr(routes, 'find_run_summary', lambda _: {'session_id': 'voice-session', 'terminal': True})
    monkeypatch.setattr(run_journal, 'read_run_events', lambda *_: {
        'events': [row('apperror', {'type': 'error', 'message': 'request timed out'}),
                   dict(row('pending_steer_leftover', seq=2), terminal=False), row('stream_end', seq=3)],
        'malformed': malformed,
    })
    handler = _make_handler()
    routes.handle_get(handler, urlparse('/api/chat/stream/status?stream_id=' + stream))
    payload = _captured_response(handler)
    assert payload['task_outcome']['status'] == expected
    if not active:
        assert payload['unconsumed_steering'] is True
    assert 'request timed out' not in str(payload)


def test_provider_policy_and_timeout_categories():
    assert _classify_provider_error('HTTP 404 Model blocked by guardrail')['type'] == 'policy_blocked'
    assert _classify_provider_error('request timed out')['type'] == 'timeout'
