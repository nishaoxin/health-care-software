"""Run the complete existing regression suite in bounded, separate processes.

All tests use their own temporary or explicitly synthetic data. This runner does
not open a camera, install dependencies, prepare models, or edit reports in Git.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def batches():
    files = sorted((ROOT / 'tests').glob('test*.py'))
    groups = {'core': [], 'ui': [], 'integration': []}
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        # Isolate real integration files first. Match the interface keywords on
        # whole name parts so "quiet" or "guidance" is not read as a UI file.
        if 'integration' in path.stem or 'landmarks' in path.stem or path.name == 'test_app_joint_expansion_flow.py':
            groups['integration'].append(relative)
        elif re.search(r'(^|_)(ui|product|guides?|hub)(_|$)', path.stem):
            groups['ui'].append(relative)
        else:
            groups['core'].append(relative)
    flattened = [name for group in groups.values() for name in group]
    if len(flattened) != len(files) or len(set(flattened)) != len(files):
        raise RuntimeError('Test partition is incomplete or overlapping')
    return groups


def stop_owned_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        # This PID comes directly from Popen above; never enumerate or stop an
        # unrelated Python application or the user's desktop application.
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=20, check=False)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_batch(label, tests, output, timeout):
    logfile = output / (label + '.log')
    junit = output / (label + '.xml')
    args = [sys.executable, '-m', 'pytest', *tests, '-q', '-ra',
            '-o', 'faulthandler_timeout=120', '--junitxml=' + str(junit)]
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONUTF8='1', PYTHONUNBUFFERED='1')
    started = time.monotonic()
    timed_out = False
    print(f'RUN {label}: {len(tests)} file(s)', flush=True)
    with logfile.open('wb') as log:
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stop_owned_process(process)
            code = 124
        except BaseException:
            stop_owned_process(process)
            raise
    counts = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    if junit.is_file():
        document = ET.parse(junit).getroot()
        suites = [document] if document.tag == 'testsuite' else list(document.iter('testsuite'))
        for suite in suites:
            for name in counts:
                counts[name] += int(suite.get(name, '0'))
    lines = logfile.read_text(encoding='utf-8', errors='replace').splitlines()
    summaries = [line.strip() for line in lines if re.search(r'\b\d+ (?:passed|failed|skipped|error)', line)]
    result = {'batch': label, 'files': tests, 'exit_code': code, 'timed_out': timed_out,
              'duration_s': round(time.monotonic() - started, 2), 'junit': counts,
              'pytest_summary': summaries[-1] if summaries else 'No pytest result; inspect log',
              'log': logfile.name, 'junit_file': junit.name}
    print(f'{"PASS" if code == 0 else "FAIL"} {label}: {result["pytest_summary"]}', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('all', 'core', 'ui', 'integration'), default='all')
    parser.add_argument('--timeout', type=float, default=300, help='Maximum seconds per batch')
    parser.add_argument('--output', type=Path, help='New directory for logs, JUnit and summary JSON')
    parser.add_argument('--list', action='store_true', help='Show disjoint file groups without running tests')
    args = parser.parse_args()
    groups = batches()
    if args.list:
        print(json.dumps(groups, ensure_ascii=False, indent=2))
        return 0
    if args.timeout <= 0:
        parser.error('--timeout must be positive')
    output = (args.output or ROOT / '.runtime' / 'checks' / datetime.now().strftime('%Y%m%d-%H%M%S')).resolve()
    output.mkdir(parents=True, exist_ok=False)
    selected = list(groups) if args.suite == 'all' else [args.suite]
    queue = []
    for group in selected:
        if group == 'integration':
            queue.extend((Path(name).stem, [name]) for name in groups[group])
        elif groups[group]:
            queue.append((group, groups[group]))
    report = {'started_at_utc': datetime.now(timezone.utc).isoformat(), 'python_version': sys.version.split()[0],
              'suite': args.suite, 'partition_file_count': sum(map(len, groups.values())),
              'camera_opened_by_runner': False, 'results': []}
    for label, tests in queue:
        report['results'].append(run_batch(label, tests, output, args.timeout))
        report['success'] = all(item['exit_code'] == 0 for item in report['results'])
        (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        if not report['success']:
            print('Stopped at the failed batch. Remaining batches were not run.', flush=True)
            return 1
    report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['completed_batches'] = len(report['results'])
    (output / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Completed {len(queue)} batch(es). Evidence: {output}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
