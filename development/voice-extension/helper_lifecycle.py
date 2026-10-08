"""Foreground, service-manager-friendly supervisor. No PID-based signalling.

The supervisor alone owns its Popen handle. Local control files are not a
security boundary against same-UID code, just like the canonical token file.
"""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

from voice_state import state_directory


def publish(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data), encoding='utf-8')
    os.replace(temporary, path)


class Ownership:
    """Kernel-released exclusive lock, including after supervisor crashes."""
    def __init__(self, path):
        self.file = path.open('a+b')
        self.file.seek(0, 2)
        if not self.file.tell():
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise ValueError('state already owned') from None

    def close(self):
        self.file.close()


def snapshot(state):
    try:
        data = json.loads((state/'helper-status.json').read_text(encoding='utf-8'))
        if not isinstance(data, dict) or not isinstance(data.get('heartbeat'), (int, float)):
            return {'state': 'unknown'}
        age = time.time()-data['heartbeat']
        instance = data.get('instance')
        if (not 0 <= age <= 3 or not isinstance(instance, str) or len(instance) != 32 or
                any(c not in '0123456789abcdef' for c in instance)):
            return {'state': 'unknown'}
        return data
    except FileNotFoundError:
        return {'state': 'stopped'}
    except (OSError, ValueError, KeyError, TypeError):
        return {'state': 'unknown'}


def worker(args, state):
    # Wrap server construction only, retaining the canonical handler/dispatch,
    # loopback host, auth and HTTP envelope unchanged. Publish readiness ONLY
    # after bind succeeds (health alone could belong to an unrelated listener).
    import sidecar_base
    from helper import make_app
    from transport import DisabledAuth, negotiate
    base = sidecar_base.ThreadingHTTPServer

    class ReadyServer(base):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            publish(state/'helper-ready.json', {'instance': args.instance})

    sidecar_base.ThreadingHTTPServer = ReadyServer
    auth = DisabledAuth()
    provider = None
    if args.lb_key_file:
        from lb_auth import LocalLBAuth
        auth = LocalLBAuth(args.lb_key_file)
        url = 'http://localhost:2455/backend-api/codex/realtime/calls?intent=quicksilver&architecture=avas'
        provider = lambda s, v: negotiate(s, v, auth, call_url=url)
    make_app(provider=provider, auth=auth, state_dir=state,
             port=args.port, token_file=args.token_file).serve()


def local_health_ready(port):
    """Bounded loopback-only probe; no proxy, token, credential or provider call."""
    import http.client
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=.5)
    try:
        connection.request('GET', '/health')
        response = connection.getresponse()
        return response.status == 200 and len(response.read(4097)) <= 4096
    except (OSError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def supervise(args, state):
    lock = Ownership(state/'helper-owner.lock')
    child = None
    stopping = False
    instance = secrets.token_hex(16)
    status = state/'helper-status.json'
    ready = state/'helper-ready.json'
    stop = state/('helper-stop-'+instance)
    def request_stop(*unused):
        nonlocal stopping
        stopping = True
    previous = {}
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, request_stop)
        ready.unlink(missing_ok=True)
        command = [sys.executable, str(Path(__file__).resolve()), '_worker',
                   '--state-dir', str(state), '--port', str(args.port),
                   '--token-file', str(args.token_file), '--instance', instance]
        if args.lb_key_file:
            command += ['--lb-key-file', str(args.lb_key_file)]
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        # No inherited fallback to a real token file or implicit credential route.
        env['HERMES_EXT_SIDECAR_TOKEN_FILE'] = str(args.token_file)
        child = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic()+10
        running = False
        while not stopping:
            if child.poll() is not None:
                raise ValueError('helper exited; check port and explicit paths')
            if not running and ready.exists():
                data = json.loads(ready.read_text(encoding='utf-8'))
                running = data.get('instance') == instance and local_health_ready(args.port)
            if not running and time.monotonic() > deadline:
                raise ValueError('helper startup timed out')
            publish(status, {'state': 'running' if running else 'starting',
                             'instance': instance, 'port': args.port,
                             'heartbeat': time.time()})
            if stop.exists():
                stopping = True
            time.sleep(.1)
        return 0
    finally:
        if child is not None and child.poll() is None:
            child.terminate()  # owned handle, NEVER a stored PID or port occupant
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)
        status.unlink(missing_ok=True)
        ready.unlink(missing_ok=True)
        stop.unlink(missing_ok=True)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        lock.close()  # persistent lock inode: unlinking it would introduce races


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'status', 'stop', 'preflight', '_worker'])
    parser.add_argument('--state-dir', required=True)
    parser.add_argument('--port', type=int)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('manifest.json'))
    parser.add_argument('--token-file', type=Path)
    parser.add_argument('--lb-key-file', type=Path)
    parser.add_argument('--instance', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        state = state_directory(args.state_dir, required=True)
        if args.action == 'status':
            data = snapshot(state)
            print(json.dumps({k: data[k] for k in ('state', 'port') if k in data}))
            return 0 if data['state'] == 'running' else 1
        if args.action == 'stop':
            data = snapshot(state)
            if data['state'] == 'stopped':
                return 0
            if data['state'] not in ('running', 'starting'):
                raise ValueError('ownership stale; refusing to signal any process')
            instance = data['instance']
            (state/('helper-stop-'+instance)).touch(mode=0o600)
            deadline = time.monotonic()+8
            while time.monotonic() < deadline:
                current = snapshot(state)
                if current.get('instance') != instance:
                    (state/('helper-stop-'+instance)).unlink(missing_ok=True)
                    return 0
                time.sleep(.1)
            raise ValueError('stop not acknowledged; no PID was signalled')
        if not args.port or not 1 <= args.port <= 65535:
            raise ValueError('explicit port in 1..65535 required')
        for name in ('token_file', 'lb_key_file'):
            path = getattr(args, name)
            if path is not None and not path.is_absolute():
                raise ValueError('explicit file paths must be absolute')
        if args.token_file is None:
            raise ValueError('explicit token file required')
        if args.action in ('start', 'preflight'):
            manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
            entry = next((e for e in manifest.get('extensions', []) if e.get('id') == 'subscription-voice'), None)
            sidecar = entry.get('sidecar', {}) if entry else {}
            if (sidecar.get('origin') != f'http://127.0.0.1:{args.port}' or
                    sidecar.get('proxy_auth') != 'token-v1' or sidecar.get('health_path') != '/health'):
                raise ValueError('manifest and helper endpoint must agree')
            if args.action == 'preflight':
                print(json.dumps({'valid': True, 'port': args.port, 'credentials_read': False}))
                return 0
        if args.action == '_worker':
            if not args.instance:
                raise ValueError('worker requires instance')
            worker(args, state)
            return 0
        return supervise(args, state)
    except (ValueError, OSError) as error:
        # Fixed categories expose the failure without leaking paths or secrets.
        known = {
            'state already owned': 'state_already_owned',
            'helper exited; check port and explicit paths': 'helper_startup_failed',
            'helper startup timed out': 'helper_startup_timeout',
            'ownership stale; refusing to signal any process': 'ownership_stale',
            'stop not acknowledged; no PID was signalled': 'stop_unacknowledged',
            'manifest and helper endpoint must agree': 'manifest_endpoint_mismatch',
            'voice state directory must be absolute': 'state_path_not_absolute',
            'explicit voice state directory required': 'state_path_required',
            'voice state must be outside extension assets': 'state_inside_assets',
            'explicit file paths must be absolute': 'file_path_not_absolute',
            'explicit token file required': 'token_path_required',
            'explicit port in 1..65535 required': 'invalid_port',
        }
        category = known.get(str(error), 'filesystem_or_configuration_error')
        print(json.dumps({'ok': False, 'category': category, 'credentials_disclosed': False}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
