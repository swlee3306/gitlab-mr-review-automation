import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from reviewflow.__main__ import load_event


class CLITests(unittest.TestCase):
    def test_demo(self):
        p=subprocess.run([sys.executable,'-m','reviewflow','demo'],capture_output=True,text=True)
        self.assertEqual(p.returncode,0)
        self.assertIn('"status": "completed"',p.stdout)
        self.assertIn('"status": "duplicate"',p.stdout)

    def test_duplicate_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'event.json';p.write_text('{"iid":1,"iid":2}')
            with self.assertRaises(ValueError):load_event(p)

    def test_bad_input_exit_is_safe(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'event.json';p.write_text('SYNTHETIC_NOT_JSON')
            result=subprocess.run([sys.executable,'-m','reviewflow','review',str(p),'--head','a'*40,'--db',str(Path(d)/'state.db')],capture_output=True,text=True)
            self.assertEqual(result.returncode,2)
            self.assertNotIn('SYNTHETIC_NOT_JSON',result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
