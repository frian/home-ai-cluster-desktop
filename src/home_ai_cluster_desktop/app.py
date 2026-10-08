"""One-window client for the ordinary native Home AI Cluster Chat route."""

import argparse
import json
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtNetwork import (
    QNetworkAccessManager,
    QNetworkProxy,
    QNetworkReply,
    QNetworkRequest,
)
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CHAT_URL = "http://127.0.0.1:25042/v1/chat"


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
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)

        layout = QVBoxLayout()
        layout.addWidget(self.conversation)
        layout.addWidget(self.input)
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
        reply = self._network.post(request, payload)
        self._reply = reply
        reply.finished.connect(self._finished)
        self._timer.start()
        self.send_button.setEnabled(False)
        self.input.clear()
        self.conversation.appendPlainText(f"You: {message}")

    def _timed_out(self) -> None:
        if self._reply is None:
            return
        # The reply may finish later. Its completion must not affect this window.
        self._reply = None
        self.send_button.setEnabled(True)
        self.conversation.appendPlainText("The request timed out.")

    def _finished(self) -> None:
        reply = self.sender()
        if not isinstance(reply, QNetworkReply):
            return
        if reply is not self._reply:
            reply.deleteLater()
            return
        self._reply = None
        self._timer.stop()
        self.send_button.setEnabled(True)
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
                result = json.loads(bytes(reply.readAll()))
                content = result["content"]
                if not isinstance(content, str):
                    raise ValueError("invalid Chat content")
            except (ValueError, TypeError, KeyError):
                message = "Home AI Cluster returned an invalid response."
            else:
                message = f"Home AI Cluster: {content}"
        self.conversation.appendPlainText(message)
        reply.deleteLater()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = ChatWindow(args.timeout_seconds)
    window.show()
    return app.exec()
