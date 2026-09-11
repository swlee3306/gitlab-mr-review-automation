"""Offline CLI: no credentials, network, webhooks or external publication."""
import argparse
import json
from pathlib import Path
import tempfile
import sqlite3

from .core import Event, Finding, Store, UnsafeInput, run_once


def fake_reviewer(event):
    return [Finding(path, line, 'warning', 'Consider structured logging instead of a print call.')
            for path, lines in event.changes.items() for line, text in lines.items()
            if text.lstrip().startswith('print(')]


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def reject_constant(_): raise ValueError('nonfinite JSON number')


def load_event(path):
    if path.stat().st_size > 512_000: raise ValueError('input size limit')
    data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(data, dict) or set(data) != {'project', 'iid', 'sha', 'changes'}: raise ValueError('event fields')
    if not isinstance(data['changes'], dict): raise ValueError('changes shape')
    for lines in data['changes'].values():
        if not isinstance(lines, dict) or any(not line.isdecimal() or str(int(line)) != line for line in lines):
            raise ValueError('noncanonical line number')
    data['changes'] = {path: {int(line): text for line, text in lines.items()} for path, lines in data['changes'].items()}
    return Event(**data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('demo', help='run a synthetic event twice to demonstrate deduplication')
    run = sub.add_parser('review', help='review a normalized local event with the fake reviewer')
    run.add_argument('event', type=Path)
    run.add_argument('--head', required=True, help='current commit SHA; supplied by the offline harness')
    run.add_argument('--db', type=Path, required=True, help='local state database')
    args = parser.parse_args()
    try:
        if args.command == 'demo':
            event = Event('example/service', 7, 'a' * 40, {'app.py': {8: 'print("hello")'}})
            with tempfile.TemporaryDirectory(prefix='reviewflow-') as directory, Store(Path(directory) / 'jobs.db') as store:
                for _ in range(2): print(json.dumps(run_once(store, event, lambda: event.sha, fake_reviewer), indent=2))
            return 0
        event = load_event(args.event)
        with Store(args.db) as store: result = run_once(store, event, lambda: args.head, fake_reviewer)
        print(json.dumps(result, indent=2))
        return 0 if result['status'] in {'completed', 'duplicate'} else 1
    except (ValueError, TypeError, AttributeError, OSError, sqlite3.Error, RecursionError):
        print(json.dumps({'status': 'invalid_input', 'message': 'Check the event schema, privacy policy and local file access.'}))
        return 2


if __name__ == '__main__': raise SystemExit(main())
