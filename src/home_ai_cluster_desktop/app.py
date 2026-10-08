"""One-window client for the ordinary native Home AI Cluster Chat route."""

import argparse
import json
import sys

from PySide6.QtCore import QEvent, Qt, QTimer, QUrl
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CHAT_URL = "http://127.0.0.1:25042/v1/chat"


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

        self.conversation = QPlainTextEdit()
        self.conversation.setReadOnly(True)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Message")
        self.input.setFixedHeight(100)
        self.input.installEventFilter(self)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)
        self.waiting_label = QLabel("Waiting…")
        self.waiting_label.setVisible(False)

        layout = QVBoxLayout()
        layout.addWidget(self.conversation)
        layout.addWidget(self.input)
        layout.addWidget(self.waiting_label)
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

    def _append_conversation(self, message: str) -> None:
        self.conversation.appendPlainText(message)
        scrollbar = self.conversation.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _set_awaiting(self, awaiting: bool) -> None:
        self.send_button.setEnabled(not awaiting)
        self.waiting_label.setVisible(awaiting)

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
        self._append_conversation(f"You: {message}")
        self.input.clear()
        reply = self._network.post(request, payload)
        self._reply = reply
        reply.finished.connect(self._finished)
        self._timer.start()
        self._set_awaiting(True)

    def _timed_out(self) -> None:
        if self._reply is None:
            return
        # The reply may finish later. Its completion must not affect this window.
        self._reply = None
        self._append_conversation("The request timed out.")
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
                message = f"Home AI Cluster: {content}"
        self._append_conversation(message)
        self._complete_interaction()
        reply.deleteLater()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = ChatWindow(args.timeout_seconds)
    window.show()
    return app.exec()
