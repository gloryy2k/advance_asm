"""Check protocol dependency separately from Starlette's in-process TestClient."""
import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn


def test_uvicorn_auto_websocket_protocol_is_available():
    from uvicorn.protocols.websockets.auto import AutoWebSocketsProtocol
    assert AutoWebSocketsProtocol is not None, "Install the pinned websockets runtime dependency"


@pytest.mark.integration
def test_real_uvicorn_websocket_handshake_and_replay(settings):
    # Local TCP only, no recon subprocess or target traffic. Still integration:
    # this intentionally exercises the real ASGI server's network protocol stack.
    from websockets.sync.client import connect
    from backend.main import create_app
    from backend.tests.p2_helpers import environment

    _, _, result = environment(settings)
    app = create_app(settings)
    asyncio.run(app.state.runner.logs.emit(result.scan_id, "done", status="done"))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                        log_level="warning", timeout_graceful_shutdown=2))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started:
            assert thread.is_alive() and time.monotonic() < deadline, "Uvicorn did not start"
            time.sleep(0.02)
        with connect(f"ws://127.0.0.1:{port}/ws/scan/{result.scan_id}?after=0", open_timeout=5) as client:
            assert client.response.status_code == 101
            event = json.loads(client.recv(timeout=5))
            assert event["type"] == "done" and event["status"] == "done"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
        assert not thread.is_alive(), "Uvicorn failed to shut down"
