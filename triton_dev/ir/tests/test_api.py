import base64
import json

from fastapi.testclient import TestClient

from triton_dev.platform.app import create_app
from triton_dev.platform.service import Platform


def test_ir_import_uses_session_csrf_and_real_location_parser(tmp_path):
    p = Platform('sqlite:///' + str(tmp_path / 'db.sqlite'), tmp_path / 'state')
    try:
        client = TestClient(create_app(p))
        assert client.get('/api/ir/compilers').status_code == 401
        user = client.post('/api/sessions', json={'name': 'IR tester'}).json()['data']
        body = {'data': base64.b64encode(json.dumps({'payload': {
            'python_source': {'file_path': '/work/k.py', 'code': 'x = 1\ny = x + 1', 'start_line': 1},
            'file_content': {'k.coreir': '%0 = arith.addi %a, %b loc("/work/k.py":2:5)'}
        }}).encode()).decode()}
        assert client.post('/api/ir/import', json=body).status_code == 403
        client.headers['X-CSRF-Token'] = user['csrf_token']
        response = client.post('/api/ir/import', json=body)
        assert response.status_code == 200, response.text
        assert response.json()['data']['documents'][0]['stages'][0]['mapping']['1']['line'] == 2
        assert client.get('/api/ir/compilers').json()['data']['compilers'] == []
        assert client.post('/api/ir/import', json={'data': '%%%'}).status_code == 400
        assert client.get('/api/ir/compilations/unknown').status_code == 404
        assert client.post('/api/ir/import', json=body, headers={'Origin': 'https://elsewhere.invalid'}).status_code == 403
    finally:
        p.close()
