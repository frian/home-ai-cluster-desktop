import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtNetwork import QNetworkProxy  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QTextEdit  # noqa: E402

from home_ai_cluster_desktop import app as desktop  # noqa: E402


@pytest.fixture(scope="session")
def qt_app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.fixture
def server():
    received = []
    gate = threading.Event()
    plan = {
        "status": 200,
        "body": b'{"capabilities":["chat"]}',
        "wait": False,
        "chat_wait": False,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received.append(("GET", self.path, self.headers.get("Content-Length")))
            if plan["wait"]:
                gate.wait(10)
            self.send_response(plan["status"])
            if plan["status"] == 302:
                self.send_header("Location", "http://127.0.0.1:1/redirect-target")
            self.end_headers()
            try:
                self.wfile.write(plan["body"])
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            size = int(self.headers["Content-Length"])
            received.append(("POST", self.path, self.rfile.read(size)))
            if plan["chat_wait"]:
                gate.wait(10)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"content": "Hello", "adapter": "fixture", "node_id": "fixture"}
                ).encode()
            )

        def log_message(self, *_args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, received, plan, gate
    gate.set()
    httpd.shutdown()
    thread.join()
    httpd.server_close()


def until(qt_app, condition, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Qt condition did not occur")


def window_for(monkeypatch, qt_app, server):
    httpd, *_ = server
    monkeypatch.setattr(
        desktop,
        "CAPABILITIES_URL",
        f"http://127.0.0.1:{httpd.server_port}/diagnostics/caller-routable-capabilities",
    )
    monkeypatch.setattr(
        desktop, "CHAT_URL", f"http://127.0.0.1:{httpd.server_port}/v1/chat"
    )
    window = desktop.ChatWindow()
    window.show()
    return window


def observed(qt_app, window):
    until(qt_app, lambda: window.refresh_button.isEnabled())
    return window.capabilities_value.text()


def presented_messages(window):
    messages = []
    for frame in window.conversation.findChildren(QFrame):
        kind = frame.objectName().removeprefix("chat-message-")
        if kind not in {"user", "hac", "status"}:
            continue
        body = frame.findChild(QLabel, "chat-message-body")
        if body is None:
            response = frame.findChild(QTextEdit, "chat-message-body")
            assert response is not None
            text = response.toPlainText()
        else:
            text = body.text()
        messages.append(
            (kind, frame.findChild(QLabel, "chat-message-sender").text(), text)
        )
    return messages


def test_startup_refresh_replacement_and_no_automatic_observation(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    assert observed(qt_app, window) == "chat"
    assert received == [("GET", "/diagnostics/caller-routable-capabilities", None)]
    for _ in range(20):
        qt_app.processEvents()
        time.sleep(0.01)
    assert len(received) == 1
    plan["body"] = b'{"capabilities":["summarize","code"]}'
    window.refresh_button.click()
    assert observed(qt_app, window) == "code, summarize"
    assert len(received) == 2
    plan["body"] = b'{"capabilities":[]}'
    window.refresh_button.click()
    assert observed(qt_app, window) == "None"
    window.close()


def test_refresh_waits_without_queueing_or_blocking_chat(monkeypatch, qt_app, server):
    _, received, plan, gate = server
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    plan["wait"] = True
    window.refresh_button.click()
    until(qt_app, lambda: len(received) == 2)
    assert not window.refresh_button.isEnabled()
    assert window.send_button.isEnabled()
    window.refresh_capabilities()
    window.input.setPlainText("Private chat message")
    window.send_button.click()
    until(qt_app, lambda: window.send_button.isEnabled())
    assert presented_messages(window) == [
        ("user", "You", "Private chat message"),
        ("hac", "Home AI Cluster", "Hello"),
    ]
    assert window.capabilities_value.text() == "chat"
    assert len(received) == 3
    assert received[1] == ("GET", "/diagnostics/caller-routable-capabilities", None)
    gate.set()
    assert observed(qt_app, window) == "chat"
    assert presented_messages(window) == [
        ("user", "You", "Private chat message"),
        ("hac", "Home AI Cluster", "Hello"),
    ]
    window.close()


@pytest.mark.parametrize(
    "body",
    [
        b"invalid json",
        b"[]",
        b"{}",
        b'{"capabilities":"chat"}',
        b'{"capabilities":["chat"],"extra":1}',
        b'{"capabilities":["chat","chat"]}',
        b'{"capabilities":["chat"],"capabilities":[]}',
        b'{"capabilities":[42]}',
    ],
)
def test_bad_response_replaces_snapshot(monkeypatch, qt_app, server, body):
    _, _, plan, _ = server
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    plan["body"] = body
    window.refresh_button.click()
    assert observed(qt_app, window) == "Capabilities unavailable"
    window.close()


def test_unfamiliar_capability_is_presented(monkeypatch, qt_app, server):
    _, _, plan, _ = server
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    plan["body"] = b'{"capabilities":["future-capability"]}'
    window.refresh_button.click()
    assert observed(qt_app, window) == "future-capability"
    window.close()


@pytest.mark.parametrize("status", [302, 503])
def test_http_failure_and_redirect_are_bounded(monkeypatch, qt_app, server, status):
    _, received, plan, _ = server
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    plan.update(status=status, body=b"private details")
    window.refresh_button.click()
    assert observed(qt_app, window) == "Capabilities unavailable"
    assert len(received) == 2
    window.close()


def test_transport_failure_replaces_snapshot(monkeypatch, qt_app, server):
    monkeypatch.setattr(desktop, "CAPABILITY_WAIT_MS", 1000)
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    monkeypatch.setattr(desktop, "CAPABILITIES_URL", "http://127.0.0.1:1/unavailable")
    window.refresh_button.click()
    assert observed(qt_app, window) == "Capabilities unavailable"
    window.close()


def test_capability_wait_expires_and_late_reply_is_ignored(monkeypatch, qt_app, server):
    monkeypatch.setattr(desktop, "CAPABILITY_WAIT_MS", 100)
    _, received, plan, gate = server
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    plan.update(wait=True, body=b'{"capabilities":["code"]}')
    window.refresh_button.click()
    until(qt_app, lambda: len(received) == 2)
    until(qt_app, lambda: window.refresh_button.isEnabled())
    assert window.capabilities_value.text() == "Capabilities unavailable"
    gate.set()
    for _ in range(20):
        qt_app.processEvents()
        time.sleep(0.01)
    assert window.capabilities_value.text() == "Capabilities unavailable"
    window.close()


def test_chat_in_flight_does_not_block_refresh(monkeypatch, qt_app, server):
    _, received, plan, gate = server
    window = window_for(monkeypatch, qt_app, server)
    assert observed(qt_app, window) == "chat"
    plan["chat_wait"] = True
    window.input.setPlainText("Chat stays pending")
    window.send_button.click()
    until(qt_app, lambda: len(received) == 2)
    assert not window.send_button.isEnabled()
    assert window.refresh_button.isEnabled()
    plan["body"] = b'{"capabilities":["code"]}'
    window.refresh_button.click()
    assert observed(qt_app, window) == "code"
    assert not window.send_button.isEnabled()
    assert presented_messages(window) == [("user", "You", "Chat stays pending")]
    gate.set()
    until(qt_app, lambda: window.send_button.isEnabled())
    assert ("hac", "Home AI Cluster", "Hello") in presented_messages(window)
    assert window.capabilities_value.text() == "code"
    window.close()


def test_proxy_is_bypassed_and_get_has_no_chat_content(monkeypatch, qt_app, server):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    QNetworkProxy.setApplicationProxy(
        QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy, "127.0.0.1", 1)
    )
    try:
        window = window_for(monkeypatch, qt_app, server)
        assert observed(qt_app, window) == "chat"
        window.input.setPlainText("unsent secret")
        window.refresh_button.click()
        assert observed(qt_app, window) == "chat"
        _, received, _, _ = server
        assert received == [
            ("GET", "/diagnostics/caller-routable-capabilities", None),
            ("GET", "/diagnostics/caller-routable-capabilities", None),
        ]
        assert window.input.toPlainText() == "unsent secret"
        assert presented_messages(window) == []
        window.close()
    finally:
        QNetworkProxy.setApplicationProxy(QNetworkProxy())
