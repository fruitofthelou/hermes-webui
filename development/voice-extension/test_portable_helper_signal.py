"""POSIX supervisor signal exit evidence (Windows uses local owned stop)."""
import os
import signal
import socket
import subprocess
import sys

import pytest
from test_portable_helper import SCRIPT, setup, status, wait_for


@pytest.mark.skipif(os.name == 'nt', reason='Windows terminate is a hard kill; use owned local stop')
def test_sigterm_reaps_owned_child(setup):
    state,port,args,env=setup
    process=subprocess.Popen([sys.executable,str(SCRIPT),'start',*args],env=env,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        wait_for(lambda:status(state).get('state')=='running')
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=12)==0
        assert not (state/'helper-status.json').exists()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',port))
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=12)
