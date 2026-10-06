"""Bound the PostgreSQL suite without an orphan keeping a tee pipe open."""
import os
import signal
import subprocess
import sys
from pathlib import Path


def main():
    if os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('ENVIRONMENT') != 'staging':
        raise SystemExit('Dedicated CI staging required.')
    log = Path('backend-integration.log')
    with log.open('w') as output:
        process = subprocess.Popen([sys.executable,'-m','pytest','-vv','--maxfail=5',
            '--durations=10','-o','faulthandler_timeout=30'],
            stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            result = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=5)
            result = 124
    # A regular file cannot keep this reader waiting on an orphan's pipe FD.
    print(log.read_text(),flush=True)
    if result == 124:
        print('Backend suite exceeded five minutes; preserved diagnostic log.',flush=True)
    raise SystemExit(result)


if __name__ == '__main__':
    main()
