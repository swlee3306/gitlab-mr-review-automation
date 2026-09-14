"""Read-only GitLab REST adapter. Never follows redirects or posts comments."""
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .core import Event


class GitLabError(ValueError):
    """Safe diagnostic code, without a response body, URL or credential."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def added_lines(diff):
    if not isinstance(diff, str) or len(diff.encode()) > 256_000:
        raise GitLabError('diff_budget')
    result = {}; old_left = new_left = 0; line = None
    for row in diff.splitlines():
        if row.startswith('@@ '):
            if old_left or new_left: raise GitLabError('incomplete_hunk')
            m = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', row)
            if not m: raise GitLabError('invalid_hunk')
            old_left = int(m[2]) if m[2] is not None else 1
            new_left = int(m[4]) if m[4] is not None else 1
            line = int(m[3])
            if old_left > 5000 or new_left > 5000: raise GitLabError('diff_budget')
        elif row == '\\ No newline at end of file':
            continue
        elif line is None:
            if not row.startswith(('diff ', 'index ', '--- ', '+++ ', 'new file ', 'deleted file ')):
                raise GitLabError('unsupported_diff')
        elif row.startswith('+'):
            if line in result: raise GitLabError('overlapping_hunks')
            result[line] = row[1:]; line += 1; new_left -= 1
        elif row.startswith('-'):
            old_left -= 1
        elif row.startswith(' '):
            line += 1; old_left -= 1; new_left -= 1
        else:
            raise GitLabError('invalid_diff_line')
        if min(old_left, new_left) < 0: raise GitLabError('hunk_overflow')
    if old_left or new_left: raise GitLabError('incomplete_hunk')
    return result


class GitLabReader:
    def __init__(self, base_url, token, *, allow_loopback=False):
        url = urlsplit(base_url)
        loopback = allow_loopback and url.scheme == 'http' and url.hostname in {'localhost', '127.0.0.1', '::1'}
        if (url.scheme != 'https' and not loopback) or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise GitLabError('invalid_origin')
        if not isinstance(token, str) or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
            raise GitLabError('invalid_token')
        self.base = base_url.rstrip('/') + '/api/v4'
        self.token = token
        self.opener = build_opener(NoRedirect())

    def get(self, path):
        if not path.startswith('/projects/'): raise GitLabError('invalid_api_path')
        request = Request(self.base + path, headers={'PRIVATE-TOKEN': self.token, 'Accept': 'application/json'}, method='GET')
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000: raise GitLabError('response_budget')
                payload = json.loads(raw)
                return payload, response.headers.get('X-Next-Page', '')
        except HTTPError as error:
            error.close()
            raise GitLabError('http_' + str(error.code)) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise GitLabError('transport_or_payload') from None

    def path(self, project, iid):
        if not isinstance(project, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)+', project) or type(iid) is not int or iid < 1:
            raise GitLabError('invalid_identity')
        return '/projects/' + quote(project, safe='') + '/merge_requests/' + str(iid)

    def head(self, project, iid):
        payload, _ = self.get(self.path(project, iid))
        sha = payload.get('sha') if isinstance(payload, dict) else None
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', sha):
            raise GitLabError('invalid_head')
        return sha

    def event(self, project, iid):
        before = self.head(project, iid); changes = {}
        for page in range(1, 11):
            payload, next_page = self.get(self.path(project, iid) + '/diffs?per_page=100&page=' + str(page))
            if not isinstance(payload, list): raise GitLabError('invalid_diffs')
            for change in payload:
                if not isinstance(change, dict) or change.get('too_large') or change.get('collapsed'):
                    raise GitLabError('incomplete_diff')
                if change.get('deleted_file'): continue
                path = change.get('new_path')
                if not isinstance(path, str) or path in changes: raise GitLabError('invalid_diff_path')
                lines = added_lines(change.get('diff'))
                if lines: changes[path] = lines
                if len(changes) > 100: raise GitLabError('file_budget')
            if not next_page: break
            if next_page != str(page + 1): raise GitLabError('invalid_pagination')
        else:
            raise GitLabError('pagination_budget')
        if self.head(project, iid) != before: raise GitLabError('head_changed')
        if not changes: raise GitLabError('no_added_text')
        return Event(project, iid, before, changes)
