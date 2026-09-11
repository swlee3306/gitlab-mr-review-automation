"""Small review state machine with persistent deduplication and fenced leases.

Adapters are callables; this module never performs network requests or publishes.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import time
from types import MappingProxyType
from typing import Callable, Mapping


class UnsafeInput(ValueError):
    """Input is unsuitable for the demo's review boundary."""


def sensitive(text: str) -> bool:
    return bool(re.search(
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----|'
        r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|glpat-[\w-]{16,}|hvs\.[\w-]{12,}|xox[baprs]-[\w-]{16,})|'
        r'(?i:password|passwd|api[_-]?key|access[_-]?token|secret)\s*[\"\x27]?\s*[:=]\s*[\"\x27][^\"\x27$<{]+[\"\x27]', text))


@dataclass(frozen=True)
class Event:
    project: str
    iid: int
    sha: str
    changes: Mapping[str, Mapping[int, str]]

    def __post_init__(self):
        if not isinstance(self.project, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)+', self.project):
            raise ValueError('invalid project')
        if type(self.iid) is not int or self.iid < 1:
            raise ValueError('invalid merge request number')
        if not isinstance(self.sha, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', self.sha):
            raise ValueError('invalid commit SHA')
        if not isinstance(self.changes, dict) or not 1 <= len(self.changes) <= 100:
            raise ValueError('expected 1 to 100 changed files')
        frozen = {}; total = 0
        for path, lines in self.changes.items():
            if not isinstance(path, str) or not path or len(path) > 240 or '\\' in path or any(ord(c) < 32 for c in path):
                raise ValueError('invalid relative path')
            if PurePosixPath(path).is_absolute() or '..' in path.split('/'):
                raise ValueError('invalid relative path')
            if not isinstance(lines, dict) or not lines:
                raise ValueError('expected changed line mapping')
            for line, source in lines.items():
                if type(line) is not int or line < 1 or not isinstance(source, str) or '\n' in source or '\r' in source:
                    raise ValueError('invalid changed line')
                total += len(source.encode('utf-8'))
            frozen[path] = MappingProxyType(dict(lines))
        if total > 256_000 or sum(map(len, self.changes.values())) > 5000:
            raise ValueError('review budget exceeded')
        object.__setattr__(self, 'changes', MappingProxyType(frozen))

    @property
    def key(self) -> str:
        return hashlib.sha256(json.dumps([self.project, self.iid, self.sha]).encode()).hexdigest()

    @property
    def digest(self) -> str:
        value = {path: dict(lines) for path, lines in self.changes.items()}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def inspect(self):
        for path, lines in self.changes.items():
            if any(part == '.env' or part.startswith('.env.') or part in {'.ssh', '.git'} for part in path.split('/')) or path.endswith(('.pem', '.key')):
                raise UnsafeInput('sensitive file excluded')
            if sensitive(path) or any(sensitive(text) for text in lines.values()):
                raise UnsafeInput('sensitive text excluded')


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    severity: str
    message: str


class Store:
    """Persist only identifiers, digest, attempts, lease deadline and status.

    A connection belongs to one worker/thread. Separate connections can compete
    for work using BEGIN IMMEDIATE; completion is fenced by the attempt number.
    """
    def __init__(self, path: Path):
        self.path = Path(path)
        self.db = sqlite3.connect(str(self.path), timeout=5)
        self.db.execute('CREATE TABLE IF NOT EXISTS jobs (key TEXT PRIMARY KEY, digest TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL, deadline REAL NOT NULL)')
        self.db.commit()

    def close(self): self.db.close()
    def __enter__(self): return self
    def __exit__(self, *args): self.close()

    def claim(self, event: Event, now: float, lease: int = 300):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            row = self.db.execute('SELECT digest,state,attempts,deadline FROM jobs WHERE key=?', (event.key,)).fetchone()
            if row and row[0] != event.digest:
                raise UnsafeInput('conflicting content for commit identity')
            if row and row[1] in {'completed', 'superseded', 'failed', 'invalid_review'}:
                result = ('duplicate' if row[1] == 'completed' else row[1], row[2])
            elif row and row[1] == 'running' and row[3] > now:
                result = ('busy', row[2])
            elif row and row[2] >= 3:
                self.db.execute('UPDATE jobs SET state=? WHERE key=?', ('failed', event.key))
                result = ('failed', row[2])
            else:
                attempt = row[2] + 1 if row else 1
                self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET state=excluded.state,attempts=excluded.attempts,deadline=excluded.deadline',
                                (event.key, event.digest, 'running', attempt, now + lease))
                result = ('running', attempt)
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def finish(self, key: str, attempt: int, status: str) -> bool:
        if status not in {'completed', 'superseded', 'failed', 'retry', 'invalid_review'}:
            raise ValueError('invalid terminal state')
        with self.db:
            changed = self.db.execute('UPDATE jobs SET state=?,deadline=0 WHERE key=? AND attempts=? AND state=?',
                                      (status, key, attempt, 'running'))
        return changed.rowcount == 1


def valid_finding(f: Finding, event: Event) -> bool:
    if not isinstance(f, Finding) or not isinstance(f.path, str) or type(f.line) is not int:
        return False
    if f.path not in event.changes or f.line not in event.changes[f.path]:
        return False
    return (f.severity in {'info', 'warning', 'error'} and isinstance(f.message, str)
            and 1 <= len(f.message) <= 500 and not any(ord(c) < 32 for c in f.message)
            and not sensitive(f.message))


def run_once(store: Store, event: Event, head: Callable[[], str], reviewer: Callable[[Event], list[Finding]]) -> dict:
    event.inspect()
    state, attempt = store.claim(event, time.time())
    if state != 'running':
        return {'status': state, 'attempts': attempt}
    findings = []
    try:
        if head() != event.sha:
            status = 'superseded'
        else:
            findings = reviewer(event)
            if not isinstance(findings, list) or len(findings) > 100 or not all(valid_finding(f, event) for f in findings):
                status = 'invalid_review'
            elif head() != event.sha:
                status = 'superseded'
            else:
                status = 'completed'
    except (TimeoutError, ConnectionError):
        status = 'retry' if attempt < 3 else 'failed'
    except Exception:
        # Exception strings can contain request data or credentials.
        status = 'failed'
    if not store.finish(event.key, attempt, status):
        return {'status': 'lease_lost', 'attempts': attempt}
    result = {'status': status, 'attempts': attempt}
    if status == 'completed':
        unique = list(dict.fromkeys(findings))
        result['findings'] = [asdict(f) for f in unique]
    return result
