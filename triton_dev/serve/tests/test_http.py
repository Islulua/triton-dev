import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from triton_dev.serve.service import handler_factory


def test_loopback_capabilities_endpoint():
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory([{"command_id": "doctor"}]))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/capabilities") as response:
            assert json.load(response)["data"] == [{"command_id": "doctor"}]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
