"""One-window client for ordinary Chat and native capability presentation."""

import argparse
import json
import sys

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtGui import QPalette
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

CHAT_URL = "http://127.0.0.1:25042/v1/chat"
CAPABILITIES_URL = "http://127.0.0.1:25042/diagnostics/caller-routable-capabilities"
CAPABILITY_WAIT_MS = 5000


def capability_names(result: object) -> list[str]:
    """Validate only the accepted native projection wire shape."""
    if not isinstance(result, dict) or set(result) != {"capabilities"}:
        raise ValueError("invalid capability projection")
    names = result["capabilities"]
    if (
        not isinstance(names, list)
        or any(not isinstance(name, str) for name in names)
        or len(names) != len(set(names))
    ):
        raise ValueError("invalid capability names")
    return names


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate JSON field")
    return result


def chat_content(result: object) -> str:
    """Read only the wire shape needed for a native Chat success."""
    if not isinstance(result, dict):
        raise ValueError("invalid native result")
    content = result.get("content")
    if not isinstance(content, str):
        raise ValueError("invalid Chat content")
    for field in ("adapter", "node_id"):
        value = result.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError("invalid native result")
    model = result.get("model")  # Optional in ClusterResult; absent defaults to null.
    if model is not None and not isinstance(model, str):
        raise ValueError("invalid native result")
    return content


def timeout_seconds(value: str) -> int:
    try:
        seconds = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be an integer") from exc
    if not 1 <= seconds <= 3600:
        raise argparse.ArgumentTypeError("timeout must be between 1 and 3600")
    return seconds


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Home AI Cluster Desktop Chat")
    parser.add_argument("--timeout-seconds", type=timeout_seconds, default=120)
    return parser.parse_args(argv)


class ChatWindow(QMainWindow):
    def __init__(self, timeout: int = 120) -> None:
        super().__init__()
        self.setWindowTitle("Home AI Cluster Chat")
        self.resize(600, 500)

        self.conversation = QScrollArea()
        self.conversation.setWidgetResizable(True)
        self.conversation.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._conversation_contents = QWidget()
        self._conversation_layout = QVBoxLayout(self._conversation_contents)
        self._conversation_layout.setContentsMargins(8, 8, 8, 8)
        self._conversation_layout.setSpacing(12)
        self._conversation_layout.addStretch()
        self.conversation.setWidget(self._conversation_contents)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Message")
        self.input.setFixedHeight(100)
        self.input.installEventFilter(self)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        self.stop_waiting_button = QPushButton("Stop waiting")
        self.stop_waiting_button.clicked.connect(self.stop_waiting)
        self.stop_waiting_button.setVisible(False)
        self.waiting_label = QLabel("Waiting…")
        self.waiting_label.setVisible(False)
        self.capabilities_label = QLabel("Available capabilities")
        self.capabilities_value = QLabel("Capabilities unavailable")
        self.capabilities_value.setTextFormat(Qt.TextFormat.PlainText)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_capabilities)
        capability_row = QHBoxLayout()
        capability_row.addWidget(self.capabilities_label)
        capability_row.addWidget(self.capabilities_value, 1)
        capability_row.addWidget(self.refresh_button)

        layout = QVBoxLayout()
        layout.addLayout(capability_row)
        layout.addWidget(self.conversation)
        layout.addWidget(self.input)
        layout.addWidget(self.waiting_label)
        layout.addWidget(self.stop_waiting_button)
        layout.addWidget(self.send_button)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._network = QNetworkAccessManager(self)
        self._network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self._reply: QNetworkReply | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(timeout * 1000)
        self._timer.timeout.connect(self._timed_out)
        self._capability_reply: QNetworkReply | None = None
        self._capability_timer = QTimer(self)
        self._capability_timer.setSingleShot(True)
        self._capability_timer.setInterval(CAPABILITY_WAIT_MS)
        self._capability_timer.timeout.connect(self._capability_timed_out)
        self._startup_observed = False

    def showEvent(self, event):
        super().showEvent(event)
        if not self._startup_observed:
            self._startup_observed = True
            self.refresh_capabilities()

    def refresh_capabilities(self) -> None:
        if self._capability_reply is not None:
            return
        request = QNetworkRequest(QUrl(CAPABILITIES_URL))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        reply = self._network.get(request)
        self._capability_reply = reply
        reply.finished.connect(self._capability_finished)
        self._capability_timer.start()
        self.refresh_button.setEnabled(False)

    def _capability_timed_out(self) -> None:
        if self._capability_reply is None:
            return
        reply = self._capability_reply
        self._capability_reply = None
        self.capabilities_value.setText("Capabilities unavailable")
        self.refresh_button.setEnabled(True)
        reply.abort()

    def _capability_finished(self) -> None:
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return
        if reply is not self._capability_reply:
            reply.deleteLater()
            return
        self._capability_reply = None
        self._capability_timer.stop()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status == 200 and reply.error() == QNetworkReply.NetworkError.NoError:
            try:
                names = capability_names(
                    json.loads(
                        bytes(reply.readAll()), object_pairs_hook=_unique_json_object
                    )
                )
            except (ValueError, TypeError):
                presentation = "Capabilities unavailable"
            else:
                presentation = ", ".join(sorted(names)) if names else "None"
        else:
            presentation = "Capabilities unavailable"
        self.capabilities_value.setText(presentation)
        self.refresh_button.setEnabled(True)
        reply.deleteLater()

    def eventFilter(self, watched, event):
        if (
            watched is self.input
            and event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.send()
            return True
        return super().eventFilter(watched, event)

    def _append_conversation(self, sender: str, message: str, kind: str) -> None:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setObjectName(f"chat-message-{kind}")
        frame.setMaximumWidth(480)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        palette = frame.palette()
        if kind == "user":
            palette.setColor(
                QPalette.ColorRole.Window,
                palette.color(
                    QPalette.ColorGroup.Active, QPalette.ColorRole.AlternateBase
                ),
            )
        elif kind == "status":
            palette.setColor(
                QPalette.ColorRole.Window,
                palette.color(QPalette.ColorGroup.Active, QPalette.ColorRole.Midlight),
            )
        frame.setPalette(palette)
        frame.setAutoFillBackground(kind != "hac")

        message_layout = QVBoxLayout(frame)
        message_layout.setContentsMargins(10, 8, 10, 8)
        message_layout.setSpacing(4)
        sender_label = QLabel(sender)
        sender_label.setObjectName("chat-message-sender")
        sender_label.setTextFormat(Qt.TextFormat.PlainText)
        body_label = QLabel(message)
        body_label.setObjectName("chat-message-body")
        body_label.setTextFormat(Qt.TextFormat.PlainText)
        body_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body_label.setWordWrap(True)
        body_policy = QSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        body_policy.setHeightForWidth(True)
        body_label.setSizePolicy(body_policy)
        message_layout.addWidget(sender_label)
        message_layout.addWidget(body_label)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        if kind == "user":
            row_layout.addStretch()
            row_layout.addWidget(frame, 3)
        else:
            row_layout.addWidget(frame, 3)
            row_layout.addStretch()
        self._conversation_layout.insertWidget(
            self._conversation_layout.count() - 1, row
        )
        self._conversation_layout.activate()
        scrollbar = self.conversation.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_awaiting(self, awaiting: bool) -> None:
        self.send_button.setEnabled(not awaiting)
        self.waiting_label.setVisible(awaiting)
        self.stop_waiting_button.setVisible(awaiting)

    def _complete_interaction(self) -> None:
        self._set_awaiting(False)
        self.input.setFocus()

    def send(self) -> None:
        if self._reply is not None:
            return
        message = self.input.toPlainText()
        if not message.strip():
            return

        request = QNetworkRequest(QUrl(CHAT_URL))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json"
        )
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        payload = json.dumps(
            {"messages": [{"role": "user", "content": message}], "capability": "chat"}
        ).encode("utf-8")
        self._append_conversation("You", message, "user")
        self.input.clear()
        reply = self._network.post(request, payload)
        self._reply = reply
        reply.finished.connect(self._finished)
        self._timer.start()
        self._set_awaiting(True)

    def stop_waiting(self) -> None:
        if self._reply is None:
            return
        # Ending this client wait does not establish any HAC-side cancellation.
        reply = self._reply
        self._reply = None
        self._timer.stop()
        reply.abort()
        self._append_conversation(
            "Request status", "Stopped waiting for the response.", "status"
        )
        self._complete_interaction()

    def _timed_out(self) -> None:
        if self._reply is None:
            return
        # The reply may finish later. Its completion must not affect this window.
        self._reply = None
        self._append_conversation("Request status", "The request timed out.", "status")
        self._complete_interaction()

    def _finished(self) -> None:
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        self._timer.stop()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is None:
            message = "Home AI Cluster is unavailable."
        elif (
            not 200 <= status < 300
            or reply.error() != QNetworkReply.NetworkError.NoError
        ):
            message = "Home AI Cluster could not complete the request."
        else:
            try:
                content = chat_content(json.loads(bytes(reply.readAll())))
            except (ValueError, TypeError, KeyError):
                message = "Home AI Cluster returned an invalid response."
            else:
                self._append_conversation("Home AI Cluster", content, "hac")
                self._complete_interaction()
                reply.deleteLater()
                return
        self._append_conversation("Request status", message, "status")
        self._complete_interaction()
        reply.deleteLater()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = ChatWindow(args.timeout_seconds)
    window.show()
    return app.exec()
