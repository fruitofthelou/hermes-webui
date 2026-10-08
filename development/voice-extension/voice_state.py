"""Explicit private runtime storage; source/assets are never a state default."""
import os
from pathlib import Path

STATE_ENV = 'HERMES_VOICE_STATE_DIR'


def state_directory(value=None, required=False):
    value = value or os.environ.get(STATE_ENV)
    if not value:
        if required:
            raise ValueError('explicit voice state directory required')
        return None  # library/offline tests: no persistence by default
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError('voice state directory must be absolute')
    path = path.resolve()
    assets = Path(__file__).resolve().parent
    configured_assets = os.environ.get('HERMES_WEBUI_EXTENSION_DIR')
    forbidden = [assets]
    # A checkout is source too, even when only its extension subdir is served.
    for parent in assets.parents:
        if (parent/'.git').exists():
            forbidden.append(parent)
            break
    if configured_assets:
        forbidden.append(Path(configured_assets).expanduser().resolve())
    if any(path == root or root in path.parents for root in forbidden):
        raise ValueError('voice state must be outside extension assets')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


class NullSink:
    enabled = False

    def append(self, *args, **kwargs):
        return False

    def load(self):
        return None
