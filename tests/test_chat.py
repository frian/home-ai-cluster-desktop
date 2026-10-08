import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QTextCursor  # noqa: E402
from PySide6.QtNetwork import QNetworkProxy  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from home_ai_cluster_desktop import app as desktop  # noqa: E402

# Attribution is included only to satisfy the native result shape.
VALID_RESULT = {
    "content": "Hello",
    "adapter": "fixture-adapter",
    "model": None,
    "node_id": "fixture-node",
}


def result_body(**changes):
    return json.dumps({**VALID_RESULT, **changes}).encode()


@pytest.fixture(scope="session")
def qt_app():
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    yield application


@pytest.fixture
def server():
    received = []
    gate = threading.Event()
    plan = {
        "status": 200,
        "body": result_body(),
        "wait": False,
        "completed": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers["Content-Length"])
            received.append((self.path, json.loads(self.rfile.read(size))))
            if plan["wait"]:
                gate.wait(3)
            self.send_response(plan["status"])
            if plan["status"] == 302:
                self.send_header("Location", "/redirect-target")
            self.end_headers()
            try:
                self.wfile.write(plan["body"])
            except BrokenPipeError:
                pass
            plan["completed"] += 1

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


def until(qt_app, condition, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        qt_app.processEvents()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Qt condition did not occur")


def window_for(monkeypatch, qt_app, server, timeout=120):
    httpd, *_ = server
    monkeypatch.setattr(
        desktop, "CHAT_URL", f"http://127.0.0.1:{httpd.server_port}/v1/chat"
    )
    window = desktop.ChatWindow(timeout)
    window.show()
    return window


def send(window, message):
    window.input.setPlainText(message)
    window.send_button.click()


def test_enter_sends_and_shift_enter_inserts_newline(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server
    window.input.setPlainText("First line")
    window.input.moveCursor(QTextCursor.MoveOperation.End)
    QTest.keyClick(window.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert window.input.toPlainText() == "First line\n"
    assert received == []
    QTest.keyClick(window.input, Qt.Key.Key_Return)
    until(qt_app, lambda: len(received) == 1 and window.send_button.isEnabled())
    assert received[0][1]["messages"] == [{"role": "user", "content": "First line\n"}]
    assert window.input.toPlainText() == ""
    window.close()


def test_timeout_option():
    assert desktop.parse_args([]).timeout_seconds == 120
    for value in ("1", "300", "3600"):
        assert desktop.parse_args(["--timeout-seconds", value]).timeout_seconds == int(
            value
        )
    for value in ("0", "3601", "1.5", "bad"):
        with pytest.raises(SystemExit):
            desktop.parse_args(["--timeout-seconds", value])


def test_two_independent_sends_and_whitespace(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server
    send(window, "   \n")
    assert received == []
    send(window, "First")
    until(qt_app, lambda: window.send_button.isEnabled())
    assert "Home AI Cluster: Hello" in window.conversation.toPlainText()
    send(window, "Second")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    assert received == [
        (
            "/v1/chat",
            {"messages": [{"role": "user", "content": "First"}], "capability": "chat"},
        ),
        (
            "/v1/chat",
            {"messages": [{"role": "user", "content": "Second"}], "capability": "chat"},
        ),
    ]
    window.close()


def test_one_request_at_a_time_and_late_reply(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server, timeout=1)
    _, received, plan, gate = server
    plan["wait"] = True
    send(window, "Slow")
    until(qt_app, lambda: len(received) == 1)
    assert not window.send_button.isEnabled()
    assert window.waiting_label.isVisible()
    assert window.input.toPlainText() == ""
    window.send()  # Even a direct invocation cannot queue work.
    assert len(received) == 1
    until(qt_app, lambda: window.send_button.isEnabled(), seconds=2)
    assert "The request timed out." in window.conversation.toPlainText()
    assert not window.waiting_label.isVisible()
    assert window.input.hasFocus()
    plan["wait"] = False
    send(window, "New")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    gate.set()
    until(qt_app, lambda: plan["completed"] == 2)
    for _ in range(20):
        qt_app.processEvents()
        time.sleep(0.01)
    assert window.conversation.toPlainText().count("Home AI Cluster: Hello") == 1
    window.close()


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, b"bad json", "Home AI Cluster returned an invalid response."),
        (200, b"[]", "Home AI Cluster returned an invalid response."),
        (
            200,
            json.dumps({"adapter": "a", "node_id": "n"}).encode(),
            "Home AI Cluster returned an invalid response.",
        ),
        (200, result_body(content=42), "Home AI Cluster returned an invalid response."),
        (
            200,
            json.dumps({"content": "Hello", "node_id": "n"}).encode(),
            "Home AI Cluster returned an invalid response.",
        ),
        (200, result_body(adapter=""), "Home AI Cluster returned an invalid response."),
        (200, result_body(adapter=42), "Home AI Cluster returned an invalid response."),
        (
            200,
            json.dumps({"content": "Hello", "adapter": "a"}).encode(),
            "Home AI Cluster returned an invalid response.",
        ),
        (200, result_body(node_id=""), "Home AI Cluster returned an invalid response."),
        (200, result_body(node_id=42), "Home AI Cluster returned an invalid response."),
        (200, result_body(model=42), "Home AI Cluster returned an invalid response."),
        (500, b"private details", "Home AI Cluster could not complete the request."),
        (302, b"", "Home AI Cluster could not complete the request."),
    ],
)
def test_bounded_failures(monkeypatch, qt_app, server, status, body, expected):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    plan.update(status=status, body=body)
    send(window, "Test")
    until(qt_app, lambda: window.send_button.isEnabled())
    assert expected in window.conversation.toPlainText()
    assert not window.waiting_label.isVisible()
    assert window.input.hasFocus()
    assert len(received) == 1  # A redirect target was not requested.
    assert "private details" not in window.conversation.toPlainText()
    if status == 500:
        plan.update(status=200, body=result_body(content="Recovered"))
        send(window, "Try again")
        until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
        assert "Home AI Cluster: Recovered" in window.conversation.toPlainText()
    window.close()


def test_success_returns_focus_and_scrolls_to_newest_content(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    window.conversation.setPlainText(
        "\n".join(f"Earlier {item}" for item in range(100))
    )
    window.conversation.verticalScrollBar().setValue(0)
    send(window, "Newest")
    until(qt_app, lambda: window.send_button.isEnabled())
    scrollbar = window.conversation.verticalScrollBar()
    assert scrollbar.value() == scrollbar.maximum()
    assert not window.waiting_label.isVisible()
    assert window.input.hasFocus()
    window.close()


def test_bypasses_application_proxy(monkeypatch, qt_app, server):
    QNetworkProxy.setApplicationProxy(
        QNetworkProxy(QNetworkProxy.ProxyType.HttpProxy, "127.0.0.1", 1)
    )
    try:
        window = window_for(monkeypatch, qt_app, server)
        _, received, _, _ = server
        send(window, "Direct")
        until(qt_app, lambda: window.send_button.isEnabled())
        assert len(received) == 1
        assert "Home AI Cluster: Hello" in window.conversation.toPlainText()
        window.close()
    finally:
        QNetworkProxy.setApplicationProxy(QNetworkProxy())


def test_connection_failure_is_bounded(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server, timeout=1)
    monkeypatch.setattr(desktop, "CHAT_URL", "http://127.0.0.1:1/v1/chat")
    send(window, "Unavailable")
    until(qt_app, lambda: window.send_button.isEnabled(), seconds=3)
    conversation = window.conversation.toPlainText()
    assert any(
        message in conversation
        for message in ("Home AI Cluster is unavailable.", "The request timed out.")
    )
    assert "Traceback" not in conversation
    assert "127.0.0.1:1" not in conversation
    window.close()


@pytest.mark.parametrize("model_field", [None, "absent", "example-model"])
def test_optional_model_wire_shape(monkeypatch, qt_app, server, model_field):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    result = dict(VALID_RESULT)
    if model_field == "absent":
        del result["model"]
    else:
        result["model"] = model_field
    plan["body"] = json.dumps(result).encode()
    send(window, "Test")
    until(qt_app, lambda: window.send_button.isEnabled())
    assert "Home AI Cluster: Hello" in window.conversation.toPlainText()
    window.close()


def test_bypasses_environment_proxy(monkeypatch, qt_app, server):
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server
    send(window, "Direct")
    until(qt_app, lambda: window.send_button.isEnabled())
    assert len(received) == 1
    assert "Home AI Cluster: Hello" in window.conversation.toPlainText()
    window.close()
