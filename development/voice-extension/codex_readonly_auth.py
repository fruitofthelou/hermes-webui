"""Approved read-only Codex file adapter. No refresh, writes, keyring or fallback."""
import base64
import json
import os
import time
from pathlib import Path

class ReadOnlyCodexAuth:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('CODEX_HOME') or str(Path.home()/'.codex'))/'auth.json'

    def load(self):
        from transport import ProbeError
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise ValueError()
            data = json.loads(raw)
            if data.get('auth_mode') not in (None, 'chatgpt'):
                raise ValueError()
            tokens = data.get('tokens')
            token, account = tokens['access_token'], tokens['account_id']
            if not all(isinstance(v,str) and v and v == v.strip() and not any(c in v for c in '\r\n') for v in (token, account)):
                raise ValueError()
            parts = token.split('.')
            if len(parts) != 3:
                raise ValueError()
            claims = json.loads(base64.urlsafe_b64decode(parts[1] + '=' * (-len(parts[1]) % 4)))
            expiry = claims.get('exp')
            if not isinstance(expiry, (int,float)):
                raise ValueError()
        except Exception:
            raise ProbeError('codex-login-unavailable',503) from None
        # Inspect expiry only, not a local verification of JWT authenticity.
        if expiry <= time.time() + 60:
            raise ProbeError('codex-login-expired',503)
        return token, account
