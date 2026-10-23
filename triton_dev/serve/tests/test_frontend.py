import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from triton_dev.serve.service import handler_factory
from triton_dev.serve.tasks import TaskManager


def test_static_ui_and_same_origin_tasks_keep_boundaries(tmp_path):
    root = tmp_path / 'ui'
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_text('<h1>local application</h1>')
    (root / 'assets/main.js').write_text('console.log("local")')
    outside = tmp_path / 'outside.txt'
    outside.write_text('must not be served')
    (root / 'assets/escape.txt').symlink_to(outside)
    manager = TaskManager(tmp_path / 'tasks', {})
    token = 'local-test-token-12345678'
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory([], manager, token, root))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        with urllib.request.urlopen(base) as response:
            assert b'local application' in response.read()
            assert response.headers['X-Content-Type-Options'] == 'nosniff'
        with urllib.request.urlopen(base + '/assets/main.js') as response:
            assert 'javascript' in response.headers['Content-Type']
        for path in ('/assets/escape.txt', '/assets/%2e%2e/%2e%2e/outside.txt', '/unregistered'):
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(base + path)
        request = urllib.request.Request(base + '/api/jobs', headers={'Authorization': 'Bearer ' + token, 'Origin': base})
        with urllib.request.urlopen(request) as response:
            assert json.load(response)['data'] == []
        request = urllib.request.Request(base + '/api/jobs', headers={'Origin': base})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        manager.close()
