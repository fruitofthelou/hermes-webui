"""Offline portable lifecycle evidence: real subprocesses, synthetic token only."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest
from helper import make_app
from voice_state import state_directory

HERE = Path(__file__).resolve().parent
SCRIPT = HERE/'helper_lifecycle.py'


def wait_for(check, timeout=12):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError('timed out waiting for offline helper')


@pytest.fixture(autouse=True)
def extension_import_path(monkeypatch):
    # Repository test cleanup restores sys.path between tests. Reapply only this
    # extension's path for lazy imports, without changing global suite cleanup.
    monkeypatch.syspath_prepend(str(HERE))


@pytest.fixture
def setup(tmp_path):
    token = tmp_path/'synthetic.token'
    token.write_text('synthetic-offline-token', encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    manifest = tmp_path/'manifest.json'
    manifest.write_text(json.dumps({'extensions':[{'id':'subscription-voice','sidecar':{
        'origin':f'http://127.0.0.1:{port}','health_path':'/health','proxy_auth':'token-v1'}}]}))
    state = tmp_path/'state'
    args = ['--state-dir',str(state),'--port',str(port),'--token-file',str(token),'--manifest',str(manifest)]
    env = os.environ.copy()
    for key in ('HERMES_VOICE_STATE_DIR','HERMES_WEBUI_EXTENSION_DIR'):
        env.pop(key, None)
    env['PYTHONDONTWRITEBYTECODE']='1'
    return state, port, args, env


def cli(action, args, env):
    return subprocess.run([sys.executable,str(SCRIPT),action,*args], env=env,
                          capture_output=True, text=True, timeout=15)


def status(state):
    try:
        return json.loads((state/'helper-status.json').read_text())
    except (OSError, ValueError):
        return {}


def request(port, path, data=None, token=True):
    headers = {'Content-Type':'application/json'}
    if token:
        headers['X-Hermes-Sidecar-Token']='synthetic-offline-token'
    req = urllib.request.Request(f'http://127.0.0.1:{port}'+path,
        data=json.dumps(data).encode() if data is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req,timeout=2) as response:
            return response.status,json.load(response)
    except urllib.error.HTTPError as error:
        return error.code,json.load(error)


def test_real_supervised_disabled_auth_roundtrip(setup):
    state,port,args,env=setup
    before = {p.name:p.read_bytes() for p in HERE.glob('*.jsonl')}
    process=subprocess.Popen([sys.executable,str(SCRIPT),'start',*args],env=env,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        wait_for(lambda:status(state).get('state')=='running')
        assert cli('status',args,env).returncode==0
        assert request(port,'/health',token=False)[0]==200
        assert request(port,'/capability',token=False)[0]==401
        assert request(port,'/capability')[1]['auth']=='auth-not-enabled'
        assert request(port,'/shutdown',{})[0]==404
        assert cli('start',args,env).returncode==2  # duplicate owner leaves child alive
        assert request(port,'/health',token=False)[0]==200
        code,job=request(port,'/negotiations',{'sdp':'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n','voice':'arbor'})
        assert code==202
        def settled():
            result=request(port,'/negotiations/'+job['id']+'/poll',{'capability':job['capability']})[1]
            return result if result['state']!='pending' else None
        assert wait_for(settled)['error']=='auth-not-enabled'
        for event in ('delivery_unconfirmed','delivery_interrupted'):
            assert request(port,'/diagnostics',{'event':event,'code':'offline','stage':'test','request_id':'r1','secret':'never-store'})[0]==200
        assert request(port,'/audit',{'kind':'transcript','text':'not-consented'})[1]=={'recorded':False,'enabled':False}
        assert not (state/'voice-audit'/'voice-audit.jsonl').exists()
        rows=[json.loads(line) for line in (state/'diagnostic-trace.jsonl').read_text().splitlines()]
        assert {r['event'] for r in rows} >= {'delivery_unconfirmed','delivery_interrupted','negotiation_error'}
        assert all('secret' not in r for r in rows)
        assert cli('stop',args,env).returncode==0
        assert process.wait(timeout=10)==0
        assert not (state/'helper-status.json').exists()
        assert cli('stop',args,env).returncode==0
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',port))
        assert {p.name:p.read_bytes() for p in HERE.glob('*.jsonl')}==before
    finally:
        if process.poll() is None:
            cli('stop',args,env)
            process.wait(timeout=12)


def test_unrelated_listener_collision_is_not_killed(setup):
    state,port,args,env=setup
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',port));listener.listen()
        assert cli('start',args,env).returncode==2
        assert not (state/'helper-status.json').exists()
        assert cli('stop',args,env).returncode==0
        with socket.create_connection(('127.0.0.1',port),timeout=2):
            connection,_=listener.accept();connection.close()


def test_preflight_never_reads_credentials_and_checks_manifest(setup,tmp_path):
    state,port,args,env=setup
    args += ['--lb-key-file',str(tmp_path/'nonexistent-credential')]
    result=cli('preflight',args,env)
    assert result.returncode==0
    assert json.loads(result.stdout)['credentials_read'] is False
    manifest=Path(args[args.index('--manifest')+1])
    data=json.loads(manifest.read_text());data['extensions'][0]['sidecar']['origin']='http://127.0.0.1:1'
    manifest.write_text(json.dumps(data))
    refused = cli('preflight',args,env)
    assert refused.returncode==2
    assert json.loads(refused.stderr)['category']=='manifest_endpoint_mismatch'
    assert str(tmp_path) not in refused.stderr


def test_state_explicit_outside_assets_and_isolated(tmp_path,monkeypatch):
    monkeypatch.delenv('HERMES_VOICE_STATE_DIR',raising=False)
    assert state_directory() is None
    with pytest.raises(ValueError):state_directory(required=True)
    with pytest.raises(ValueError):state_directory('relative')
    with pytest.raises(ValueError):state_directory(HERE/'runtime')
    custom_assets=tmp_path/'assets'
    monkeypatch.setenv('HERMES_WEBUI_EXTENSION_DIR',str(custom_assets))
    with pytest.raises(ValueError):state_directory(custom_assets/'nested')
    for name in ('test','production'):
        root=tmp_path/name
        app=make_app(state_dir=root)
        app._token_path=tmp_path/'missing-token'
        assert app._dispatch('GET','/capability',{},lambda:b'')[0]==503
        assert not (root/'voice-audit'/'enabled').exists()
    assert (tmp_path/'test').resolve() != (tmp_path/'production').resolve()


def test_readiness_probe_requires_http_response(monkeypatch):
    import helper_lifecycle
    import http.client
    observed = []

    class Connection:
        def __init__(self, host, port, timeout):
            observed.append((host, port, timeout))
        def request(self, method, path):
            assert (method, path) == ('GET', '/health')
        def getresponse(self):
            raise TimeoutError('synthetic delayed listener')
        def close(self):
            observed.append('closed')

    monkeypatch.setattr(http.client, 'HTTPConnection', Connection)
    assert helper_lifecycle.local_health_ready(12345) is False
    assert observed == [('127.0.0.1', 12345, .5), 'closed']


def test_stale_status_never_signals_pid(setup):
    state,port,args,env=setup
    state.mkdir()
    (state/'helper-status.json').write_text(json.dumps({'state':'running','heartbeat':0,'pid':os.getpid(),'instance':'old'}))
    assert cli('stop',args,env).returncode==2
    assert cli('status',args,env).returncode==1
    (state/'helper-status.json').write_text('malformed')
    assert cli('stop',args,env).returncode==2
