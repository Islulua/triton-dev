import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile

import pytest


@pytest.fixture
def make_sdk(tmp_path):
    def create(name="TX82_SDK_Daily_2026-10-22-02-52", root=None, complete=True):
        sdk = (root or tmp_path / "sdks") / name
        for part in ("bin", "lib", "wheel") if complete else ("lib",):
            (sdk / part).mkdir(parents=True, exist_ok=True)
        if complete:
            for package in ("raops", "torch_raisa", "triton"):
                path = sdk / "wheel" / f"{package}-0.1.0-py3-none-any.whl"
                files = {
                    f"{package}/__init__.py": "SYNTHETIC_TEST_PACKAGE = True\n",
                    f"{package}-0.1.0.dist-info/METADATA": f"Metadata-Version: 2.1\nName: {package}\nVersion: 0.1.0\n",
                    f"{package}-0.1.0.dist-info/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
                }
                record = f"{package}-0.1.0.dist-info/RECORD"
                files[record] = "\n".join(f"{key},," for key in [*files, record]) + "\n"
                with ZipFile(path, "w") as archive:
                    for key, value in files.items():
                        archive.writestr(key, value)
        return sdk
    return create


@pytest.fixture
def http_directory(tmp_path):
    servers = []
    def start(directory):
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(directory), **kwargs)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append((server, thread))
        return f"http://127.0.0.1:{server.server_port}/"
    yield start
    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
