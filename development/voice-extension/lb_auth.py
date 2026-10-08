"""Explicit local LB credential reference; never copies or prints the key."""
from pathlib import Path
from transport import ProbeError
class LocalLBAuth:
    def __init__(self,path):self.path=Path(path)
    def load(self):
        try:
            if self.path.stat().st_size>8192:raise ValueError()
            token=self.path.read_text(encoding='utf-8-sig').strip()
            if not token or any(c.isspace() for c in token):raise ValueError()
            return token,None
        except Exception:raise ProbeError('lb-key-unavailable',503) from None
