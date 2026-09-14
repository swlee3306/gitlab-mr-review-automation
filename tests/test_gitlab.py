from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from io import BytesIO
from urllib.error import HTTPError

from reviewflow.gitlab import GitLabReader, GitLabError, added_lines


class ReaderTests(unittest.TestCase):
    def test_http_error_response_is_closed(self):
        body = BytesIO(b'not-for-diagnostics')
        error = HTTPError('https://gitlab.example.com', 302, 'redirect', {}, body)
        class FailingOpener:
            def open(self, request, timeout):
                raise error
        reader = GitLabReader('https://gitlab.example.com', 'SYNTHETIC')
        reader.opener = FailingOpener()
        with self.assertRaisesRegex(GitLabError, '^http_302$'):
            reader.head('example/service', 1)
        self.assertTrue(body.closed)

    def reader(self, replies):
        reader = GitLabReader('https://gitlab.example.com', 'SYNTHETIC')
        iterator=iter(replies);reader.get=lambda _:next(iterator)
        return reader

    def test_line_mapping(self):
        self.assertEqual(added_lines('@@ -1,2 +1,3 @@\n context\n-old\n+new\n+more'),{2:'new',3:'more'})

    def test_new_file(self):
        self.assertEqual(added_lines('@@ -0,0 +1 @@\n+hello'),{1:'hello'})

    def test_truncated_hunk(self):
        with self.assertRaises(GitLabError):added_lines('@@ -1,2 +1,2 @@\n only-one')

    def test_budget(self):
        with self.assertRaises(GitLabError):added_lines('@@ -0,0 +1,6000 @@')

    def test_event(self):
        r=self.reader([({'sha':'a'*40},''),([{'new_path':'app.py','diff':'@@ -0,0 +1 @@\n+hello'}],''),({'sha':'a'*40},'')])
        self.assertEqual(r.event('example/service',1).changes['app.py'][1],'hello')

    def test_head_changed(self):
        r=self.reader([({'sha':'a'*40},''),([{'new_path':'app.py','diff':'@@ -0,0 +1 @@\n+hello'}],''),({'sha':'b'*40},'')])
        with self.assertRaisesRegex(GitLabError,'head_changed'):r.event('example/service',1)

    def test_collapsed_refused(self):
        r=self.reader([({'sha':'a'*40},''),([{'collapsed':True}], '')])
        with self.assertRaises(GitLabError):r.event('example/service',1)

    def test_invalid_origin_or_header(self):
        for url,token in [('http://gitlab.example.com','SYNTHETIC'),('https://user:pass@gitlab.example.com','SYNTHETIC'),('https://gitlab.example.com','bad\nheader')]:
            with self.subTest(url=url),self.assertRaises(GitLabError):GitLabReader(url,token)

    def test_http_roundtrip_and_redirect_not_followed(self):
        requests=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                requests.append((self.path,self.headers.get('PRIVATE-TOKEN')))
                if self.path.endswith('/2'):
                    self.send_response(302);self.send_header('Location','https://example.com/never-follow');self.end_headers();return
                self.send_response(200);self.end_headers();self.wfile.write(json.dumps({'sha':'a'*40}).encode())
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            reader=GitLabReader(f'http://127.0.0.1:{server.server_port}','SYNTHETIC',allow_loopback=True)
            self.assertEqual(reader.head('example/service',1),'a'*40)
            with self.assertRaisesRegex(GitLabError,'http_302'):reader.head('example/service',2)
            self.assertEqual(len(requests),2)
            self.assertTrue(all(token=='SYNTHETIC' for _,token in requests))
        finally:server.shutdown();server.server_close();thread.join()
