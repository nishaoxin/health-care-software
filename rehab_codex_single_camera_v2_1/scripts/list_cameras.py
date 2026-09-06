"""List camera descriptors without opening capture streams. Run on target hardware."""
from __future__ import annotations
import argparse
import json
from dataclasses import asdict
from pathlib import Path
from camera_tools import enumerate_devices, show_devices


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=['dshow', 'msmf', 'v4l2', 'avfoundation'], default='dshow')
    parser.add_argument('--local-json', type=Path, help='Optional local-only descriptor file (contains device paths).')
    args = parser.parse_args()
    try:
        devices = enumerate_devices(args.backend)
        show_devices(devices)
        print(f'{len(devices)} entries; enumeration does not prove capture or image quality.')
        if args.local_json:
            args.local_json.parent.mkdir(parents=True, exist_ok=True)
            args.local_json.write_text(json.dumps([asdict(d) for d in devices], ensure_ascii=False, indent=2), encoding='utf-8')
            print('Wrote local descriptor file. Do not publish device instance paths.')
        return 0 if devices else 3
    except ImportError as exc:
        print(f'Missing dependency: {exc.name}', file=__import__('sys').stderr)
        return 2
    except Exception as exc:
        print(f'Enumeration failed: {type(exc).__name__}', file=__import__('sys').stderr)
        return 4


if __name__ == '__main__':
    raise SystemExit(main())
