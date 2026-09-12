"""Bounded loopback-only synthetic fixture for browser UI QA; no patient data."""
from pathlib import Path
import json
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.family_demo import FamilyDemo


def main():
    with tempfile.TemporaryDirectory(prefix='silver-browser-test-') as folder:
        demo = FamilyDemo(folder, '127.0.0.1')
        expired = threading.Event()
        def shutdown():
            if not expired.is_set():
                expired.set()
                demo.stop()
        timer = threading.Timer(240, shutdown)
        timer.daemon = True
        timer.start()
        try:
            demo.request()
            print(json.dumps(demo.status(), ensure_ascii=True), flush=True)
            for line in sys.stdin:
                if expired.is_set() or line.strip() == 'stop':
                    break
                if line.strip() == 'approve':
                    pending = demo.status()['pending']
                    if len(pending) == 1:
                        demo.approve(pending[0])
                print(json.dumps(demo.status(), ensure_ascii=True), flush=True)
        finally:
            timer.cancel()
            shutdown()


if __name__ == '__main__':
    main()
