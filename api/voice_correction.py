"""WebUI-owned, non-I/O admission for interactive Hermes corrections.

No callback replacement: the native conversation loop consumes the native slot.
Interactive request workers observe _interrupt_requested themselves. Inline and
Codex transports require a request-scoped asynchronous cancellation API first.
"""
from functools import lru_cache


class VoiceCorrectionAdmission:
    def _webui_admit_correction(self, text):
        if (getattr(self, 'api_mode', None) not in ('chat_completions', 'codex_responses', 'anthropic_messages')
                or getattr(self, 'provider', None) == 'moa'
                or getattr(self, 'platform', None) in ('cron', 'subagent')
                or callable(getattr(self, '_active_request_abort', None))):
            return False, 'immediate_redirect_unsupported'
        if self._webui_uses_inline_request():
            return False, 'immediate_redirect_unsupported'
        lock = getattr(self, '_pending_redirect_lock', None)
        active = getattr(self, '_model_request_active', None)
        if lock is None or active is None:
            return False, 'immediate_redirect_unsupported'
        with lock:
            if self._interrupt_requested and not self._pending_redirect:
                return False, 'not_running'
            if active.is_set() and not getattr(self, '_executing_tools', False):
                existing = self._pending_redirect
                self._pending_redirect = (
                    f'{existing}\n\n[Additional user correction]\n{text}' if existing else text
                )
                self._interrupt_requested = True
                self._interrupt_message = None
                return True, None
            # No model request to abort. Native steer consumers handle preparation
            # and tool boundaries; never kill a tool for conversational guidance.
            with self._pending_steer_lock:
                existing = self._pending_steer
                self._pending_steer = f'{existing}\n{text}' if existing else text
            return True, None

    def _webui_claim_stop(self):
        # Only in-memory state. Native interrupt, tool fanout, compression fence
        # and provider abort remain outside WebUI registry locks.
        with self._pending_redirect_lock:
            self._interrupt_requested = True
            self._interrupt_message = 'Cancelled by user'
            self._pending_redirect = None

    def _webui_drain_corrections(self):
        redirect = self._drain_pending_redirect()
        steer = self._drain_pending_steer()
        return '\n'.join(t for t in (redirect, steer) if t) or None


@lru_cache(maxsize=8)
def correction_agent_class(base):
    """Keep the native constructor/signature and lifecycle, never patch instances."""
    if base is None or not callable(getattr(base, '_drain_pending_redirect', None)):
        return base
    from agent.chat_completion_helpers import should_use_direct_api_call
    # The classifier consults delegation context. Load it during construction,
    # never at first admission while a registry lock is held.
    from agent import delegation_context  # noqa: F401
    return type('WebUICorrectionAgent', (VoiceCorrectionAdmission, base), {
        '__module__': __name__,
        '_webui_uses_inline_request': should_use_direct_api_call,
    })


def admit_correction(agent, text):
    if isinstance(agent, VoiceCorrectionAdmission):
        return agent._webui_admit_correction(text)
    # Legacy Agent steer has no I/O; do not invoke redirect/native Codex I/O.
    if getattr(agent, '_supports_active_turn_redirect', False) is True:
        return False, 'immediate_redirect_unsupported'
    return bool(agent.steer(text)), None


def claim_stop(agent):
    if isinstance(agent, VoiceCorrectionAdmission):
        agent._webui_claim_stop()


def drain_corrections(agent):
    if isinstance(agent, VoiceCorrectionAdmission):
        return agent._webui_drain_corrections()
    drain = getattr(agent, '_drain_pending_steer', None)
    return drain() if callable(drain) else None
