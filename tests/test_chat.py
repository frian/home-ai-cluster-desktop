import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QPalette, QTextCursor, QTextDocument  # noqa: E402
from PySide6.QtNetwork import QNetworkProxy, QNetworkReply  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QTextEdit  # noqa: E402

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
        "post_waits": [],
        "post_bodies": [],
        "completed": 0,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            size = int(self.headers["Content-Length"])
            received.append((self.path, json.loads(self.rfile.read(size))))
            wait = plan["post_waits"].pop(0) if plan["post_waits"] else plan["wait"]
            body = plan["post_bodies"].pop(0) if plan["post_bodies"] else plan["body"]
            if wait:
                gate.wait(3)
            self.send_response(plan["status"])
            if plan["status"] == 302:
                self.send_header("Location", "/redirect-target")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError):
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


def test_compact_chat_action_row_initial_layout(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    qt_app.processEvents()

    assert window.new_conversation_button.isVisible()
    assert window.new_conversation_button.isEnabled()
    assert window.send_button.isVisible()
    assert window.send_button.isEnabled()
    assert not window.stop_waiting_button.isVisible()
    assert not window.waiting_label.isVisible()
    assert window.action_row.indexOf(window.new_conversation_button) >= 0
    assert window.action_row.indexOf(window.waiting_label) >= 0
    assert window.action_row.indexOf(window.send_button) >= 0
    assert window.action_row.indexOf(window.stop_waiting_button) >= 0
    assert window.new_conversation_button.x() < window.send_button.x()
    assert window.new_conversation_button.width() < window.centralWidget().width()
    assert window.send_button.width() < window.centralWidget().width()
    assert window.send_button.geometry().right() > window.centralWidget().width() // 2
    window.close()


def test_compact_chat_action_row_is_centered_within_content_width(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    window.resize(1600, 900)
    qt_app.processEvents()

    container = window.action_container
    central = window.centralWidget()
    assert container.maximumWidth() == window._conversation_column.maximumWidth()
    assert container.width() == desktop.CONTENT_MAX_WIDTH
    assert container.width() < central.width()
    assert abs(container.geometry().center().x() - central.rect().center().x()) <= 2
    assert window.new_conversation_button.x() < container.width() // 2
    assert window.send_button.geometry().right() > container.width() // 2
    window.close()


def test_compact_chat_action_container_expands_at_default_width(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    qt_app.processEvents()

    container = window.action_container
    assert container.width() < container.maximumWidth()
    assert container.width() > (
        window.new_conversation_button.width() + window.send_button.width()
    )
    assert window.new_conversation_button.geometry().left() >= 0
    assert window.send_button.geometry().right() < container.width()
    window.close()


def test_message_input_is_centered_and_palette_contrasted(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    window.resize(1600, 900)
    qt_app.processEvents()

    central = window.centralWidget()
    input_palette = window.input.palette()
    assert window.input.maximumWidth() == desktop.CONTENT_MAX_WIDTH
    assert window.input.maximumWidth() == window.action_container.maximumWidth()
    assert window.input.width() == desktop.CONTENT_MAX_WIDTH
    assert window.input.width() < central.width()
    assert abs(window.input.geometry().center().x() - central.rect().center().x()) <= 2
    assert window.input.height() == 100
    assert input_palette.color(QPalette.ColorRole.Base) == input_palette.color(
        QPalette.ColorGroup.Active, QPalette.ColorRole.Window
    ).darker(desktop.INPUT_BACKGROUND_DARKENING_FACTOR)
    window.close()


def test_message_input_expands_without_clipping_at_default_width(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    qt_app.processEvents()

    assert window.input.width() < window.input.maximumWidth()
    assert window.input.width() > window.input.minimumSizeHint().width()
    assert window.input.geometry().left() >= 0
    assert window.input.geometry().right() < window.centralWidget().width()
    assert window.input.height() == 100
    window.close()


def test_compact_chat_action_row_pending_request(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    plan["wait"] = True

    send(window, "Pending")
    until(qt_app, lambda: len(received) == 1 and window._reply is not None)

    assert window.new_conversation_button.isVisible()
    assert not window.new_conversation_button.isEnabled()
    assert not window.send_button.isVisible()
    assert window.stop_waiting_button.isVisible()
    assert window.stop_waiting_button.isEnabled()
    assert window.waiting_label.isVisible()
    assert window.waiting_label.x() < window.stop_waiting_button.x()
    assert window.waiting_label.x() > window.action_container.width() // 2
    assert (
        window.stop_waiting_button.geometry().right() < window.action_container.width()
    )
    window.stop_waiting_button.click()
    window.close()


def test_compact_chat_action_row_stop_waiting_restores_normal_controls(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    plan["wait"] = True

    send(window, "Pending")
    until(qt_app, lambda: len(received) == 1 and window._reply is not None)
    window.stop_waiting_button.click()

    assert window.new_conversation_button.isVisible()
    assert window.new_conversation_button.isEnabled()
    assert window.send_button.isVisible()
    assert window.send_button.isEnabled()
    assert not window.stop_waiting_button.isVisible()
    assert not window.waiting_label.isVisible()
    window.close()


def test_compact_chat_action_row_completed_request_restores_normal_controls(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server

    send(window, "Complete")
    until(qt_app, lambda: len(received) == 1 and window.send_button.isEnabled())

    assert window.new_conversation_button.isVisible()
    assert window.new_conversation_button.isEnabled()
    assert window.send_button.isVisible()
    assert not window.stop_waiting_button.isVisible()
    assert not window.waiting_label.isVisible()
    window.close()


def presented_messages(window):
    messages = []
    for frame in window.conversation.findChildren(QFrame):
        kind = frame.objectName().removeprefix("chat-message-")
        if kind not in {"user", "hac", "status"}:
            continue
        messages.append(
            (
                kind,
                frame.findChild(QLabel, "chat-message-sender").text(),
                message_body(frame),
            )
        )
    return messages


def message_body(frame):
    label = frame.findChild(QLabel, "chat-message-body")
    if label is not None:
        return label.text()
    response = frame.findChild(QTextEdit, "chat-message-body")
    assert response is not None
    return response.toPlainText()


def response_body(frame):
    body = frame.findChild(QTextEdit, "chat-message-body")
    assert body is not None
    return body


def response_for(message, qt_app, width=600):
    body = desktop.HacResponseBody(message)
    body.resize(width, 200)
    body.show()
    qt_app.processEvents()
    return body


def test_native_markdown_renders_supported_structures_without_link_activation(qt_app):
    source = """# Heading

**bold** and *italic* with `inline code`

1. first
2. second

- outer
  - nested

> quoted

```python
print("code")
```

| Left | Right |
| --- | --- |
| one | two |

[ordinary link](https://example.invalid/path)
"""
    body = response_for(source, qt_app)
    html = body.document().toHtml().lower()
    assert not body._showing_plain_text
    assert "<h1" in html and "font-weight" in html and "font-style" in html
    assert "<ol" in html and "<ul" in html and "<table" in html
    assert "quoted" in html and "href=" in html
    assert body.textInteractionFlags() == Qt.TextInteractionFlag.TextSelectableByMouse
    assert not body.resource_request_observed
    body.close()


def test_raw_html_is_inert_markdown_text(qt_app):
    source = '<img src="https://example.invalid/image.png"><b>not HTML</b>'
    body = response_for(source, qt_app)
    assert source in body.toPlainText()
    assert not body.resource_request_observed
    assert "<img" not in body.document().toHtml().lower()
    body.close()


@pytest.mark.parametrize(
    "url",
    [
        "https://example.invalid/image.png",
        "http://example.invalid/image.png",
        "file:///not-permitted/image.png",
        "relative-image.png",
        "data:image/png;base64,AAAA",
    ],
)
def test_resource_requests_fall_back_to_exact_original_plain_text(qt_app, url):
    source = f"Before image.\n\n![alternative text]({url})\n\nAfter image."
    body = response_for(source, qt_app)
    assert body.resource_request_observed
    assert body._showing_plain_text
    assert body.toPlainText() == source
    assert body.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    body.close()


def test_blocking_document_never_delegates_a_resource_load(qt_app):
    document = desktop.ResourceBlockingDocument()
    assert (
        document.loadResource(0, desktop.QUrl("https://example.invalid/image")) is None
    )
    assert document.resource_requested


def test_layout_resource_request_falls_back_before_markdown_is_presented(qt_app):
    source = "Before\n\n![alternative](https://example.invalid/image.png)\n\nAfter"
    document = desktop.ResourceBlockingDocument()
    document.setDocumentMargin(0)
    document.setMarkdown(
        source,
        QTextDocument.MarkdownFeature.MarkdownDialectGitHub
        | QTextDocument.MarkdownFeature.MarkdownNoHTML,
    )
    document.setTextWidth(400)
    assert not document.resource_requested
    document.size()  # Qt requests the image during the forced layout.
    assert document.resource_requested

    body = response_for(source, qt_app, width=400)
    assert body.resource_request_observed
    assert body._showing_plain_text
    assert body.toPlainText() == source
    assert body.heightForWidth(400) == int(body.document().size().height())
    body.close()


def test_late_resource_observation_falls_back_during_resize(qt_app):
    source = "# Safe initially\n\nThis becomes plain text if Qt asks for a resource."
    body = response_for(source, qt_app)
    document = body.document()
    assert isinstance(document, desktop.ResourceBlockingDocument)
    assert not body._showing_plain_text
    document.resource_requested = True  # Controlled stand-in for a late Qt lookup.
    body.resize(500, 200)
    qt_app.processEvents()
    assert body._showing_plain_text
    assert body.resource_request_observed
    assert body.toPlainText() == source
    body.close()


def test_late_resource_observation_before_paint_falls_back(qt_app):
    source = "# Safe initially\n\nThis becomes plain text if Qt asks for a resource."
    body = response_for(source, qt_app)
    document = body.document()
    assert isinstance(document, desktop.ResourceBlockingDocument)
    document.resource_requested = True  # Controlled pre-paint observation.
    body.repaint()
    qt_app.processEvents()
    assert body._showing_plain_text
    assert body.resource_request_observed
    assert body.toPlainText() == source
    body.close()


@pytest.mark.parametrize(
    "source",
    [
        "```\n" + "x" * 1200 + "\n```",
        "```\n" + "long words " * 200 + "\n```",
        "Text before\n\n```\n" + "x" * 1200 + "\n```\n\nText after",
    ],
)
def test_oversized_code_uses_exact_plain_text_fallback(qt_app, source):
    body = response_for(source, qt_app, width=430)
    assert body._showing_plain_text
    assert body.toPlainText() == source
    body.selectAll()
    body.copy()
    assert qt_app.clipboard().text() == source
    body.close()


def test_table_presentation_re_evaluates_as_available_width_changes(qt_app):
    headers = [f"Column {number}" for number in range(12)]
    source = "| " + " | ".join(headers) + " |\n"
    source += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    source += "| " + " | ".join(["value"] * len(headers)) + " |"
    body = response_for(source, qt_app, width=260)
    assert body._showing_plain_text
    assert body.toPlainText() == source
    body.resize(1400, 200)
    qt_app.processEvents()
    assert not body._showing_plain_text
    body.resize(260, 200)
    qt_app.processEvents()
    assert body._showing_plain_text
    assert body.toPlainText() == source
    body.close()


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


def test_successful_sends_retain_complete_chronological_context(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server
    send(window, "   \n")
    assert received == []
    send(window, "First")
    until(qt_app, lambda: window.send_button.isEnabled())
    assert ("hac", "Home AI Cluster", "Hello") in presented_messages(window)
    assert not window.stop_waiting_button.isVisible()
    send(window, "Second")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    assert received == [
        (
            "/v1/chat",
            {"messages": [{"role": "user", "content": "First"}], "capability": "chat"},
        ),
        (
            "/v1/chat",
            {
                "messages": [
                    {"role": "user", "content": "First"},
                    {"role": "assistant", "content": "Hello"},
                    {"role": "user", "content": "Second"},
                ],
                "capability": "chat",
            },
        ),
    ]
    window.close()


def test_failed_and_empty_turns_do_not_enter_later_context(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    plan["post_bodies"] = [
        result_body(content="First response"),
        b"not JSON",
        result_body(content=""),
        result_body(content="Final response"),
    ]
    for message in ("First", "Failed", "Empty", "Final"):
        send(window, message)
        until(qt_app, lambda: window.send_button.isEnabled())
    assert received[-1][1]["messages"] == [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Final"},
    ]
    assert window._successful_messages == [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Final"},
        {"role": "assistant", "content": "Final response"},
    ]
    window.close()


def test_new_conversation_clears_window_context_but_preserves_unsent_input(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server
    send(window, "First")
    until(qt_app, lambda: window.send_button.isEnabled())
    window.input.setPlainText("Keep this draft")
    window.new_conversation_button.click()
    assert window._successful_messages == []
    assert presented_messages(window) == []
    assert window.input.toPlainText() == "Keep this draft"
    send(window, "Fresh")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    assert received[-1][1]["messages"] == [{"role": "user", "content": "Fresh"}]
    window.close()


def test_new_conversation_cannot_clear_pending_request(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    plan["wait"] = True
    send(window, "Pending")
    until(qt_app, lambda: window._reply is not None)
    assert not window.new_conversation_button.isEnabled()
    window.new_conversation()
    assert presented_messages(window) == [("user", "You", "Pending")]
    assert window._reply is not None
    window.stop_waiting()
    assert window.new_conversation_button.isEnabled()
    window.close()


def test_new_conversation_after_stop_keeps_late_result_abandoned(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, gate = server
    plan["wait"] = True
    plan["body"] = result_body(content="Late response")
    send(window, "Abandoned")
    until(qt_app, lambda: len(received) == 1)
    window.stop_waiting()
    window.new_conversation()
    assert presented_messages(window) == []
    gate.set()
    until(qt_app, lambda: plan["completed"] == 1)
    for _ in range(5):
        qt_app.processEvents()
    assert presented_messages(window) == []
    assert window._successful_messages == []
    window.close()


def test_context_bound_is_utf8_content_only_and_preserves_rejected_input(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, _, _ = server
    exact = "é" * (desktop.CHAT_CONTEXT_LIMIT_BYTES // 2)
    send(window, exact)
    until(qt_app, lambda: window.send_button.isEnabled())
    assert len(received) == 1
    assert received[0][1]["messages"] == [{"role": "user", "content": exact}]
    rejected = "x"
    window.input.setPlainText(rejected)
    window.send()
    assert len(received) == 1
    assert window.input.toPlainText() == rejected
    assert window._successful_messages[0]["content"] == exact
    assert "too large" in presented_messages(window)[-1][2]
    window.close()


def test_original_markdown_response_is_retained_for_next_request(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    markdown = "# Heading\n\n**exact source**"
    plan["post_bodies"] = [result_body(content=markdown), result_body(content="Done")]
    send(window, "First")
    until(qt_app, lambda: window.send_button.isEnabled())
    send(window, "Second")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    assert received[1][1]["messages"] == [
        {"role": "user", "content": "First"},
        {"role": "assistant", "content": markdown},
        {"role": "user", "content": "Second"},
    ]
    window.close()


def test_messages_are_separate_units_in_chronological_order(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    plan["body"] = result_body(content="First response\nwith another line")
    send(window, "First request\nwith another line")
    until(qt_app, lambda: window.send_button.isEnabled())
    plan["body"] = result_body(content="Second response")
    send(window, "Second request")
    until(qt_app, lambda: window.send_button.isEnabled())
    assert presented_messages(window) == [
        ("user", "You", "First request\nwith another line"),
        ("hac", "Home AI Cluster", "First response with another line"),
        ("user", "You", "Second request"),
        ("hac", "Home AI Cluster", "Second response"),
    ]
    window.close()


def test_html_looking_text_is_presented_literally(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    literal = '<script>alert("hello")</script>'
    plan["body"] = result_body(content=literal)
    send(window, literal)
    until(qt_app, lambda: window.send_button.isEnabled())
    messages = presented_messages(window)
    assert messages == [("user", "You", literal), ("hac", "Home AI Cluster", literal)]
    for frame in window.conversation.findChildren(QFrame):
        if frame.objectName() in {
            "chat-message-user",
            "chat-message-hac",
            "chat-message-status",
        }:
            body = frame.findChild(QLabel, "chat-message-body")
            if body is not None:
                assert body.textFormat() == Qt.TextFormat.PlainText
            else:
                assert response_body(frame).toPlainText() == literal
    window.close()


def test_hac_responses_render_markdown_with_selection_and_proportional_spacing(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    response = "# Heading\n\n**bold** and *italic* with `code`"
    plan["body"] = result_body(content=response)
    send(window, "Show literal response")
    until(qt_app, lambda: window.send_button.isEnabled())

    frame = next(
        frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-hac"
    )
    body = response_body(frame)
    assert body.toPlainText() == "Heading\nbold and italic with code"
    assert body.toHtml() != response
    assert body.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert body.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert body.document().firstBlock().blockFormat().lineHeight() == 130

    baseline = QTextEdit()
    baseline.setFont(body.font())
    baseline.setPlainText(response)
    baseline.document().setDocumentMargin(0)
    baseline.document().setTextWidth(body.width())
    assert body.heightForWidth(body.width()) > baseline.document().size().height()

    body.selectAll()
    body.copy()
    assert qt_app.clipboard().text() == body.toPlainText()
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
    assert ("status", "Request status", "The request timed out.") in presented_messages(
        window
    )
    assert not window.waiting_label.isVisible()
    assert not window.stop_waiting_button.isVisible()
    assert window.input.hasFocus()
    plan["wait"] = False
    send(window, "New")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    gate.set()
    until(qt_app, lambda: plan["completed"] == 2)
    for _ in range(20):
        qt_app.processEvents()
        time.sleep(0.01)
    assert presented_messages(window).count(("hac", "Home AI Cluster", "Hello")) == 1
    window.close()


def test_stop_waiting_ends_only_the_current_client_wait(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server, timeout=1)
    _, received, plan, _ = server
    assert not window.stop_waiting_button.isVisible()
    plan["wait"] = True
    send(window, "Slow")
    until(qt_app, lambda: len(received) == 1)
    assert not window.send_button.isEnabled()
    assert window.stop_waiting_button.isVisible()
    assert window.waiting_label.isVisible()
    reply = window._reply
    assert reply is not None

    window.stop_waiting_button.click()

    assert reply.error() == QNetworkReply.NetworkError.OperationCanceledError
    assert window.send_button.isEnabled()
    assert not window.stop_waiting_button.isVisible()
    assert not window.waiting_label.isVisible()
    assert not window._timer.isActive()
    assert window.input.hasFocus()
    assert len(received) == 1
    assert presented_messages(window) == [
        ("user", "You", "Slow"),
        ("status", "Request status", "Stopped waiting for the response."),
    ]
    window.close()


def test_stopped_wait_late_reply_cannot_overwrite_newer_request(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, gate = server
    plan["post_waits"] = [True, False]
    plan["post_bodies"] = [
        result_body(content="Late first response"),
        result_body(content="Second response"),
    ]
    send(window, "First")
    until(qt_app, lambda: len(received) == 1)
    window.stop_waiting_button.click()
    send(window, "Second")
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    assert presented_messages(window) == [
        ("user", "You", "First"),
        ("status", "Request status", "Stopped waiting for the response."),
        ("user", "You", "Second"),
        ("hac", "Home AI Cluster", "Second response"),
    ]

    gate.set()
    until(qt_app, lambda: plan["completed"] == 2)
    for _ in range(5):
        qt_app.processEvents()
    assert window.send_button.isEnabled()
    assert not window.stop_waiting_button.isVisible()
    assert presented_messages(window) == [
        ("user", "You", "First"),
        ("status", "Request status", "Stopped waiting for the response."),
        ("user", "You", "Second"),
        ("hac", "Home AI Cluster", "Second response"),
    ]
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


def test_successful_context_survives_stop_waiting_and_excludes_abandoned_turn(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, gate = server
    message_a = "context-A-4f1a"
    response_a = "response-A-9c73"
    message_b = "abandoned-B-2d86"
    message_c = "context-C-7be5"
    response_c = "response-C-1a42"
    plan["post_waits"] = [False, True, False]
    plan["post_bodies"] = [
        result_body(content=response_a),
        result_body(content="late response for B"),
        result_body(content=response_c),
    ]

    send(window, message_a)
    until(qt_app, lambda: len(received) == 1 and window.send_button.isEnabled())
    assert window._successful_messages == [
        {"role": "user", "content": message_a},
        {"role": "assistant", "content": response_a},
    ]

    send(window, message_b)
    until(qt_app, lambda: len(received) == 2 and window._reply is not None)
    window.stop_waiting_button.click()
    assert window.send_button.isEnabled()
    assert (
        "status",
        "Request status",
        "Stopped waiting for the response.",
    ) in presented_messages(window)

    send(window, message_c)
    until(qt_app, lambda: len(received) == 3 and window.send_button.isEnabled())
    assert received[2][1]["messages"] == [
        {"role": "user", "content": message_a},
        {"role": "assistant", "content": response_a},
        {"role": "user", "content": message_c},
    ]
    assert window._successful_messages == [
        {"role": "user", "content": message_a},
        {"role": "assistant", "content": response_a},
        {"role": "user", "content": message_c},
        {"role": "assistant", "content": response_c},
    ]
    before_late_result = presented_messages(window)

    gate.set()
    until(qt_app, lambda: plan["completed"] == 3)
    for _ in range(5):
        qt_app.processEvents()
    assert len(received) == 3
    assert presented_messages(window) == before_late_result
    assert window._successful_messages == [
        {"role": "user", "content": message_a},
        {"role": "assistant", "content": response_a},
        {"role": "user", "content": message_c},
        {"role": "assistant", "content": response_c},
    ]
    assert window._reply is None
    assert window.send_button.isEnabled()
    window.close()


def test_timeout_then_new_conversation_discards_old_request_and_context(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, gate = server
    timed_out_message = "timed-out-4b28"
    old_response = "late timed-out response"
    draft = "preserved draft-91d6"
    fresh_message = "fresh-after-reset-6ca0"
    plan["post_waits"] = [True, False]
    plan["post_bodies"] = [
        result_body(content=old_response),
        result_body(content="fresh response"),
    ]

    send(window, timed_out_message)
    until(qt_app, lambda: len(received) == 1 and window._reply is not None)
    window._timed_out()
    assert window._reply is None
    assert window.send_button.isEnabled()
    assert window.new_conversation_button.isEnabled()
    assert (
        "status",
        "Request status",
        "The request timed out.",
    ) in presented_messages(window)

    window.input.setPlainText(draft)
    window.new_conversation_button.click()
    assert window._successful_messages == []
    assert presented_messages(window) == []
    assert window.input.toPlainText() == draft
    assert window.send_button.isEnabled()

    gate.set()
    until(qt_app, lambda: plan["completed"] == 1)
    for _ in range(5):
        qt_app.processEvents()
    assert presented_messages(window) == []
    assert window._successful_messages == []
    assert window.input.toPlainText() == draft
    assert window._reply is None
    assert window.send_button.isEnabled()

    send(window, fresh_message)
    until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
    assert received[1][1]["messages"] == [
        {"role": "user", "content": fresh_message},
    ]
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
    assert ("status", "Request status", expected) in presented_messages(window)
    assert not window.waiting_label.isVisible()
    assert window.input.hasFocus()
    assert len(received) == 1  # A redirect target was not requested.
    assert all(
        "private details" not in body for _, _, body in presented_messages(window)
    )
    if status == 500:
        plan.update(status=200, body=result_body(content="Recovered"))
        send(window, "Try again")
        until(qt_app, lambda: len(received) == 2 and window.send_button.isEnabled())
        assert ("hac", "Home AI Cluster", "Recovered") in presented_messages(window)
    window.close()


def test_success_returns_focus_and_scrolls_to_newest_content(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    plan["body"] = result_body(
        content="\n".join(f"Long response {item}" for item in range(100))
    )
    window.conversation.verticalScrollBar().setValue(0)
    send(window, "Newest")
    until(qt_app, lambda: window.send_button.isEnabled())
    scrollbar = window.conversation.verticalScrollBar()
    assert scrollbar.value() == scrollbar.maximum()
    assert not window.waiting_label.isVisible()
    assert window.input.hasFocus()
    window.close()


def test_user_message_bubbles_follow_short_and_medium_content(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    messages = ("Hello!", "What is democracy?")
    plan["post_bodies"] = [result_body(content="First"), result_body(content="Second")]
    window.resize(1600, 900)

    for message in messages:
        send(window, message)
        until(qt_app, lambda: window.send_button.isEnabled())

    viewport = window.conversation.viewport()
    column = window._conversation_column
    user_frames = [
        frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-user"
    ]
    assert len(user_frames) == len(messages)
    for frame, message in zip(user_frames, messages, strict=True):
        body = frame.findChild(QLabel, "chat-message-body")
        sender = frame.findChild(QLabel, "chat-message-sender")
        assert body is not None and body.text() == message
        assert sender is not None and sender.text() == "You"
        assert frame.width() < 300
        frame_right = frame.mapTo(viewport, frame.rect().topRight()).x()
        column_right = column.mapTo(viewport, column.rect().topRight()).x()
        assert abs(frame_right - column_right) <= 1
    window.close()


def test_long_and_multiline_user_bubbles_wrap_and_preserve_content(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    short_message = "Hello!"
    long_message = "A complete user message should wrap naturally. " * 40
    multiline_message = "First line\nSecond line\nThird line"
    plan["post_bodies"] = [result_body(content="Done")] * 3

    for message in (short_message, long_message, multiline_message):
        send(window, message)
        until(qt_app, lambda: window.send_button.isEnabled())

    user_frames = [
        frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-user"
    ]
    short_frame, long_frame, multiline_frame = user_frames
    long_body = long_frame.findChild(QLabel, "chat-message-body")
    multiline_body = multiline_frame.findChild(QLabel, "chat-message-body")
    assert long_body is not None and long_body.text() == long_message
    assert multiline_body is not None and multiline_body.text() == multiline_message
    assert short_frame.width() < long_frame.width() <= 600
    assert long_body.height() > long_body.fontMetrics().height()
    assert multiline_body.height() >= 3 * multiline_body.fontMetrics().height()
    window.close()


def test_user_bubbles_reflow_inside_the_conversation_column(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    message = "A user message that should reflow as the window changes size. " * 30
    window._append_conversation("You", message, "user")
    frame = next(
        frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-user"
    )

    for width, height in ((430, 500), (600, 500), (1100, 800), (430, 500)):
        window.resize(width, height)
        qt_app.processEvents()
        column = window._conversation_column
        frame_right = frame.mapTo(column, frame.rect().topRight()).x()
        assert frame.width() <= 600
        assert frame_right < column.width()
        assert window.conversation.horizontalScrollBar().maximum() == 0
    window.close()


def test_conversation_is_centered_and_bounded_at_wide_widths(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    long_message = (
        "A comfortably wide message should use the available frame width. " * 30
    )
    plan["body"] = result_body(content=long_message)
    window.resize(1600, 900)
    send(window, long_message)
    until(qt_app, lambda: window.send_button.isEnabled())
    window._append_conversation("Request status", long_message, "status")
    qt_app.processEvents()

    viewport = window.conversation.viewport()
    column = window._conversation_column
    column_left = column.mapTo(viewport, column.rect().topLeft()).x()
    column_right = column.mapTo(viewport, column.rect().topRight()).x()
    assert column.width() <= 900
    assert abs(column_left - (viewport.width() - column.width()) // 2) <= 2

    frames = {
        frame.objectName().removeprefix("chat-message-"): frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName()
        in {"chat-message-user", "chat-message-hac", "chat-message-status"}
    }
    user_left = frames["user"].mapTo(viewport, frames["user"].rect().topLeft()).x()
    hac_left = frames["hac"].mapTo(viewport, frames["hac"].rect().topLeft()).x()
    assert user_left + frames["user"].width() <= column_right + 1
    assert user_left > hac_left
    assert abs(hac_left - column_left) <= 1
    status_left = (
        frames["status"].mapTo(viewport, frames["status"].rect().topLeft()).x()
    )
    assert abs(status_left - column_left) <= 1
    assert frames["user"].width() <= 600
    assert frames["hac"].width() <= 720
    assert frames["status"].width() <= 480
    assert frames["user"].width() > 480
    assert frames["hac"].width() > 480
    window.close()


def test_conversation_column_reflows_without_horizontal_overflow(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    plan["body"] = result_body(content="A response that wraps naturally. " * 20)
    send(window, "A request that wraps naturally. " * 20)
    until(qt_app, lambda: window.send_button.isEnabled())

    for width, height in ((430, 500), (600, 500), (1100, 800), (430, 500)):
        window.resize(width, height)
        for _ in range(10):
            qt_app.processEvents()

        viewport = window.conversation.viewport()
        assert window._conversation_column.width() <= min(900, viewport.width())
        assert window.conversation.horizontalScrollBar().maximum() == 0
        for frame in window.conversation.findChildren(QFrame):
            if frame.objectName() in {
                "chat-message-user",
                "chat-message-hac",
                "chat-message-status",
            }:
                kind = frame.objectName().removeprefix("chat-message-")
                assert frame.width() <= {"user": 600, "hac": 720, "status": 480}[kind]
                assert frame.geometry().right() < window._conversation_column.width()
    window.close()


def test_chat_window_re_evaluates_overflow_presentation_at_real_response_widths(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, received, plan, _ = server
    sizes = ((430, 500), (600, 500), (1100, 800), (1600, 900), (430, 500))
    calibration = desktop.ChatWindow()
    calibration.show()
    qt_app.processEvents()
    calibration.resize(*sizes[0])
    qt_app.processEvents()
    calibration._append_conversation("Home AI Cluster", "Probe", "hac")
    probe_frame = next(
        frame
        for frame in calibration.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-hac"
    )
    probe_body = response_body(probe_frame)
    probe_viewports = []
    for width, height in sizes[:4]:
        calibration.resize(width, height)
        qt_app.processEvents()
        probe_viewports.append(probe_body.viewport().width())
    probe_font = probe_body.document().defaultFont()
    probe_text_option = probe_body.document().defaultTextOption()

    def markdown_width(count, text_width):
        candidate = desktop.ResourceBlockingDocument()
        candidate.setDocumentMargin(0)
        candidate.setDefaultFont(probe_font)
        candidate.setDefaultTextOption(probe_text_option)
        candidate.setMarkdown(
            "```text\n" + "M" * count + "\n```",
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
            | QTextDocument.MarkdownFeature.MarkdownNoHTML,
        )
        candidate.setTextWidth(text_width)
        candidate.size()
        return candidate.idealWidth()

    narrow_width = probe_viewports[0]
    wider_width = next(
        width for width in probe_viewports[1:] if width > narrow_width + 0.5
    )
    target_width = (narrow_width + wider_width) / 2
    counts = [
        count
        for count in range(1, 201)
        if narrow_width + 0.5 < markdown_width(count, 10000) <= wider_width + 0.5
    ]
    assert counts
    code_count = min(
        counts, key=lambda count: abs(markdown_width(count, 10000) - target_width)
    )
    source = "Before code:\n\n```text\n" + "M" * code_count + "\n```\n\nFINAL LINE"
    calibration.close()
    plan["body"] = result_body(content=source)
    send(window, "Show responsive table")
    until(qt_app, lambda: window.send_button.isEnabled())
    frame = next(
        frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-hac"
    )
    body = response_body(frame)
    presentations = []
    candidate_widths = []
    viewport_widths = []

    for width, height in sizes:
        window.resize(width, height)
        for _ in range(20):
            qt_app.processEvents()
        candidate = desktop.ResourceBlockingDocument()
        candidate.setDocumentMargin(0)
        candidate.setDefaultFont(body.document().defaultFont())
        candidate.setDefaultTextOption(body.document().defaultTextOption())
        candidate.setMarkdown(
            source,
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub
            | QTextDocument.MarkdownFeature.MarkdownNoHTML,
        )
        candidate.setTextWidth(body.viewport().width())
        candidate_widths.append(candidate.size().width())
        viewport_widths.append(body.viewport().width())
        presentations.append(body._showing_plain_text)
        assert body.viewport().width() > 0
        assert body.horizontalScrollBar().maximum() == 0
        assert window.conversation.horizontalScrollBar().maximum() == 0
        assert frame.width() <= 720
        assert frame.geometry().right() < window._conversation_column.width()
        assert len(received) == 1

    assert presentations[0]
    assert candidate_widths[0] > viewport_widths[0] + 0.5
    for candidate_width, viewport_width, presentation in zip(
        candidate_widths, viewport_widths, presentations, strict=True
    ):
        assert presentation is (candidate_width > viewport_width + 0.5)
    assert any(not presentation for presentation in presentations[1:-1])
    assert presentations[4]
    assert candidate_widths[4] > viewport_widths[4] + 0.5
    assert body.toPlainText() == source
    scrollbar = window.conversation.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    qt_app.processEvents()
    assert body.mapTo(window.conversation.viewport(), body.rect().bottomLeft()).y() < (
        window.conversation.viewport().height()
    )
    window.close()


def test_long_response_remains_fully_allocated_and_scrollable_after_resizing(
    monkeypatch, qt_app, server
):
    window = window_for(monkeypatch, qt_app, server)
    _, _, plan, _ = server
    final_line = "FINAL LINE OF THE RESPONSE"
    response = (
        "\n\n".join(
            f"Paragraph {number}: "
            + "A complete Chat response should stay readable after resizing. " * 6
            for number in range(12)
        )
        + f"\n{final_line}"
    )
    plan["body"] = result_body(content=response)
    send(window, "Show the full response")
    until(qt_app, lambda: window.send_button.isEnabled())

    frame = next(
        frame
        for frame in window.conversation.findChildren(QFrame)
        if frame.objectName() == "chat-message-hac"
    )
    body = response_body(frame)
    assert final_line in body.toPlainText()

    for width, height in (
        (600, 500),
        (430, 500),
        (1100, 800),
        (1600, 900),
        (430, 500),
    ):
        window.resize(width, height)
        for _ in range(20):
            qt_app.processEvents()

        scrollbar = window.conversation.verticalScrollBar()
        assert frame.width() <= 720
        assert body.height() >= body.heightForWidth(body.width())
        assert body.mapTo(frame, body.rect().bottomLeft()).y() < frame.height()
        assert scrollbar.maximum() > 0
        scrollbar.setValue(scrollbar.maximum())
        qt_app.processEvents()
        last_line_bottom = body.mapTo(
            window.conversation.viewport(), QPoint(0, body.height() - 1)
        ).y()
        assert 0 <= last_line_bottom < window.conversation.viewport().height()
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
        assert ("hac", "Home AI Cluster", "Hello") in presented_messages(window)
        window.close()
    finally:
        QNetworkProxy.setApplicationProxy(QNetworkProxy())


def test_connection_failure_is_bounded(monkeypatch, qt_app, server):
    window = window_for(monkeypatch, qt_app, server, timeout=1)
    monkeypatch.setattr(desktop, "CHAT_URL", "http://127.0.0.1:1/v1/chat")
    send(window, "Unavailable")
    until(qt_app, lambda: window.send_button.isEnabled(), seconds=3)
    messages = presented_messages(window)
    assert any(
        message == body
        for _, _, body in messages
        for message in ("Home AI Cluster is unavailable.", "The request timed out.")
    )
    assert all(
        "Traceback" not in body and "127.0.0.1:1" not in body for _, _, body in messages
    )
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
    assert ("hac", "Home AI Cluster", "Hello") in presented_messages(window)
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
    assert ("hac", "Home AI Cluster", "Hello") in presented_messages(window)
    window.close()
