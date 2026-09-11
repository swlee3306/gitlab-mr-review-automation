import tempfile
import unittest
from pathlib import Path

from reviewflow.core import Event, Finding, Store, UnsafeInput, run_once

SHA = 'a' * 40
NEW_SHA = 'b' * 40


def event(**kwargs):
    return Event(**({'project': 'example/service', 'iid': 7, 'sha': SHA,
                    'changes': {'app.py': {8: 'print("hello")'}}} | kwargs))


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / 'jobs.sqlite3')
        self.addCleanup(self.store.close)

    def test_duplicate_is_not_reviewed_twice(self):
        e = event(); calls = []
        def review(_):
            calls.append(1)
            return [Finding('app.py', 8, 'warning', 'Consider structured logging.')]
        self.assertEqual(run_once(self.store, e, lambda: SHA, review)['status'], 'completed')
        self.assertEqual(run_once(self.store, e, lambda: SHA, review)['status'], 'duplicate')
        self.assertEqual(len(calls), 1)

    def test_new_sha_is_another_job(self):
        self.assertNotEqual(event().key, event(sha=NEW_SHA).key)

    def test_stale_before_review(self):
        def must_not_run(_): raise AssertionError('review called')
        self.assertEqual(run_once(self.store, event(), lambda: NEW_SHA, must_not_run)['status'], 'superseded')

    def test_stale_after_review(self):
        heads = iter([SHA, NEW_SHA])
        result = run_once(self.store, event(), lambda: next(heads), lambda _: [Finding('app.py', 8, 'warning', 'Check this.')])
        self.assertEqual(result['status'], 'superseded')
        self.assertNotIn('findings', result)

    def test_transient_failure_can_retry(self):
        def fail(_): raise TimeoutError('sensitive upstream error')
        result = run_once(self.store, event(), lambda: SHA, fail)
        self.assertEqual(result, {'status': 'retry', 'attempts': 1})
        self.assertEqual(run_once(self.store, event(), lambda: SHA, lambda _: [])['status'], 'completed')

    def test_retry_budget(self):
        def fail(_): raise TimeoutError()
        for _ in range(3): result = run_once(self.store, event(), lambda: SHA, fail)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(run_once(self.store, event(), lambda: SHA, lambda _: [])['status'], 'failed')

    def test_outside_changed_lines_rejected(self):
        result = run_once(self.store, event(), lambda: SHA, lambda _: [Finding('app.py', 99, 'warning', 'Bad position')])
        self.assertEqual(result['status'], 'invalid_review')

    def test_secret_input_never_reaches_reviewer(self):
        e = event(changes={'config.py': {1: 'password = "not-a-real-password"'}})
        with self.assertRaises(UnsafeInput): run_once(self.store, e, lambda: SHA, lambda _: [])

    def test_sensitive_file_blocked(self):
        with self.assertRaises(UnsafeInput):
            run_once(self.store, event(changes={'.env': {1: 'DEBUG=true'}}), lambda: SHA, lambda _: [])

    def test_db_contains_no_diff(self):
        marker = 'unique-source-content-never-persisted'
        run_once(self.store, event(changes={'app.py': {8: marker}}), lambda: SHA, lambda _: [])
        self.assertNotIn(marker.encode(), self.store.path.read_bytes())

    def test_duplicate_survives_reopening(self):
        run_once(self.store, event(), lambda: SHA, lambda _: [])
        with Store(self.store.path) as reopened:
            self.assertEqual(run_once(reopened, event(), lambda: SHA, lambda _: [])['status'], 'duplicate')

    def test_invalid_identity(self):
        for kw in ({'iid': True}, {'iid': 0}, {'sha': 'main'}, {'project': '../service'}, {'sha': SHA.upper()}):
            with self.subTest(kw=kw), self.assertRaises(ValueError): event(**kw)

    def test_unknown_reviewer_exception_is_redacted(self):
        def fail(_): raise RuntimeError('do-not-print-this')
        result = run_once(self.store, event(), lambda: SHA, fail)
        self.assertEqual(result['status'], 'failed')
        self.assertNotIn('do-not-print-this', str(result))

    def test_two_connections_claim_only_once(self):
        e=event()
        with Store(self.store.path) as other:
            self.assertEqual(self.store.claim(e, 100)[0], 'running')
            self.assertEqual(other.claim(e, 101)[0], 'busy')

    def test_expired_worker_cannot_finish_reclaimed_work(self):
        e=event();_,first=self.store.claim(e, 100, lease=5)
        _,second=self.store.claim(e, 106, lease=5)
        self.assertFalse(self.store.finish(e.key,first,'completed'))
        self.assertTrue(self.store.finish(e.key,second,'completed'))

    def test_conflicting_content_rejected(self):
        self.store.claim(event(),100)
        with self.assertRaises(UnsafeInput):
            self.store.claim(event(changes={'app.py':{8:'different content'}}),101)

    def test_reviewer_cannot_mutate_event(self):
        e=event()
        with self.assertRaises(TypeError): e.changes['app.py'][8]='changed'

    def test_secret_in_reviewer_output_rejected(self):
        r=run_once(self.store,event(),lambda:SHA,lambda _:[Finding('app.py',8,'warning','password = "synthetic-output"')])
        self.assertEqual(r['status'],'invalid_review')

    def test_diff_budget(self):
        with self.assertRaises(ValueError):event(changes={'app.py':{1:'a'*256001}})


if __name__ == '__main__': unittest.main()
