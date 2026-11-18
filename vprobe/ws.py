"""A minimal RFC 6455 WebSocket client on the Python standard library.

The probe has no third-party dependencies, so the socket layer is written out
here instead of imported. It supports what the public market-data endpoints of
Binance, Bybit, OKX and Hyperliquid need: TLS with certificate verification and
SNI, the HTTP Upgrade handshake with Sec-WebSocket-Accept verification, masked
client frames, 16-bit and 64-bit lengths, continuation frames, ping/pong/close
control frames, and a receive timeout so a caller can keep its own clock.

It is not a general-purpose library: no extensions, no compression, one socket
per instance. That is deliberate. The less code between the wire and the
timestamp, the more the timestamp means.

Only wss:// is accepted, so a public feed is never read over a plain socket by
accident.
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
import time
from urllib.parse import urlsplit

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONT, OP_TEXT, OP_BINARY, OP_CLOSE, OP_PING, OP_PONG = 0x0, 0x1, 0x2, 0x8, 0x9, 0xA

DEFAULT_TIMEOUT = 10.0
MAX_PAYLOAD = 16 * 1024 * 1024


class WebSocketError(Exception):
    """The connection is unusable: bad handshake, protocol error, closed."""


class WebSocketTimeout(WebSocketError):
    """No complete frame arrived inside the timeout. The socket may be fine."""


def _apply_mask(data: bytes, key: bytes) -> bytes:
    n = len(data)
    if n == 0:
        return b""
    k = (key * (n // 4 + 1))[:n]
    return bytes(a ^ b for a, b in zip(data, k))


def build_frame(opcode: int, payload: bytes, fin: bool = True, mask: bool = True,
                mask_key: bytes | None = None) -> bytes:
    """Encode one frame. Clients must mask; servers must not."""
    head = bytearray()
    head.append((0x80 if fin else 0x00) | (opcode & 0x0F))
    n = len(payload)
    flag = 0x80 if mask else 0x00
    if n < 126:
        head.append(flag | n)
    elif n < 65536:
        head.append(flag | 126)
        head += struct.pack("!H", n)
    else:
        head.append(flag | 127)
        head += struct.pack("!Q", n)
    if mask:
        key = mask_key if mask_key is not None else os.urandom(4)
        head += key
        payload = _apply_mask(payload, key)
    return bytes(head) + payload


class Frame:
    __slots__ = ("fin", "opcode", "payload")

    def __init__(self, fin: bool, opcode: int, payload: bytes) -> None:
        self.fin = fin
        self.opcode = opcode
        self.payload = payload


def parse_frame(buf: bytes) -> tuple[Frame | None, int]:
    """Parse the first frame in ``buf`` as ``(frame, consumed)``.

    ``frame`` is None when more bytes are needed, and ``consumed`` is then 0.
    """
    if len(buf) < 2:
        return None, 0
    b0, b1 = buf[0], buf[1]
    fin = bool(b0 & 0x80)
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    ln = b1 & 0x7F
    pos = 2
    if ln == 126:
        if len(buf) < pos + 2:
            return None, 0
        ln = struct.unpack("!H", buf[pos:pos + 2])[0]
        pos += 2
    elif ln == 127:
        if len(buf) < pos + 8:
            return None, 0
        ln = struct.unpack("!Q", buf[pos:pos + 8])[0]
        pos += 8
    if ln > MAX_PAYLOAD:
        raise WebSocketError(f"frame too large: {ln} bytes")
    key = b""
    if masked:
        if len(buf) < pos + 4:
            return None, 0
        key = buf[pos:pos + 4]
        pos += 4
    if len(buf) < pos + ln:
        return None, 0
    payload = buf[pos:pos + ln]
    if masked:
        payload = _apply_mask(payload, key)
    return Frame(fin, opcode, payload), pos + ln


class WebSocket:
    """One client connection. Use as a context manager."""

    def __init__(self, url: str, connect_timeout: float = DEFAULT_TIMEOUT,
                 recv_timeout: float = DEFAULT_TIMEOUT,
                 headers: list[tuple[str, str]] | None = None,
                 ssl_context: ssl.SSLContext | None = None) -> None:
        parts = urlsplit(url)
        if parts.scheme != "wss":
            raise WebSocketError("only wss:// is supported")
        if not parts.hostname:
            raise WebSocketError(f"no host in url: {url}")
        self.url = url
        self.host = parts.hostname
        self.port = parts.port or 443
        self.path = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout
        self.headers = headers or []
        self.ssl_context = ssl_context
        self._sock: socket.socket | None = None
        self._buf = bytearray()
        self._frag: list[bytes] = []
        self._frag_opcode: int | None = None
        self.sent_frames = 0
        self.recv_frames = 0

    # ------------------------------------------------------------------ connect
    def connect(self) -> "WebSocket":
        ctx = self.ssl_context or ssl.create_default_context()
        raw = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        raw.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = ctx.wrap_socket(raw, server_hostname=self.host)
        key = base64.b64encode(os.urandom(16)).decode()
        lines = [
            f"GET {self.path} HTTP/1.1",
            f"Host: {self.host}" + ("" if self.port == 443 else f":{self.port}"),
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        lines += [f"{k}: {v}" for k, v in self.headers]
        req = ("\r\n".join(lines) + "\r\n\r\n").encode()
        self._sock.sendall(req)
        head = self._read_until_headers()
        status = head.split("\r\n", 1)[0]
        if "101" not in status:
            raise WebSocketError(f"handshake refused: {status}")
        accept = None
        for line in head.split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip().lower() == "sec-websocket-accept":
                    accept = v.strip()
        expected = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        if accept != expected:
            raise WebSocketError("handshake failed: bad Sec-WebSocket-Accept")
        return self

    def _read_until_headers(self) -> str:
        assert self._sock is not None
        while b"\r\n\r\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise WebSocketError("connection closed during handshake")
            self._buf += chunk
        idx = self._buf.index(b"\r\n\r\n") + 4
        head = bytes(self._buf[:idx]).decode("utf-8", "replace")
        del self._buf[:idx]
        return head

    # ------------------------------------------------------------------ send
    def send(self, payload: bytes, opcode: int = OP_TEXT) -> None:
        if self._sock is None:
            raise WebSocketError("not connected")
        self._sock.sendall(build_frame(opcode, payload))
        self.sent_frames += 1

    def send_text(self, text: str) -> None:
        self.send(text.encode(), OP_TEXT)

    def send_json(self, obj) -> None:
        import json
        self.send_text(json.dumps(obj, separators=(",", ":")))

    def ping(self, data: bytes = b"") -> None:
        self.send(data, OP_PING)

    def pong(self, data: bytes = b"") -> None:
        self.send(data, OP_PONG)

    # ------------------------------------------------------------------ receive
    def recv(self, timeout: float | None = None) -> tuple[int, bytes] | None:
        """Return ``(opcode, payload)`` of the next data message, or None.

        Control frames are handled inside: a server ping is answered with a
        pong, a pong is dropped, a close raises ``WebSocketError``.
        """
        if self._sock is None:
            raise WebSocketError("not connected")
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            frame, used = parse_frame(bytes(self._buf))
            if frame is not None:
                del self._buf[:used]
                self.recv_frames += 1
                if frame.opcode == OP_CLOSE:
                    code = struct.unpack("!H", frame.payload[:2])[0] if len(frame.payload) >= 2 else 1005
                    raise WebSocketError(f"closed by peer (code {code})")
                if frame.opcode == OP_PING:
                    self.pong(frame.payload)
                    continue
                if frame.opcode == OP_PONG:
                    continue
                if frame.opcode in (OP_TEXT, OP_BINARY):
                    if frame.fin:
                        return frame.opcode, frame.payload
                    self._frag = [frame.payload]
                    self._frag_opcode = frame.opcode
                    continue
                if frame.opcode == OP_CONT:
                    self._frag.append(frame.payload)
                    if frame.fin:
                        data = b"".join(self._frag)
                        op = self._frag_opcode or OP_TEXT
                        self._frag, self._frag_opcode = [], None
                        return op, data
                    continue
                raise WebSocketError(f"unexpected opcode {frame.opcode}")
            wait = self.recv_timeout if deadline is None else max(0.0, deadline - time.monotonic())
            if deadline is not None and wait == 0.0:
                return None
            self._sock.settimeout(wait)
            try:
                chunk = self._sock.recv(65536)
            except socket.timeout:
                return None
            except ssl.SSLError as exc:
                raise WebSocketError(f"tls error: {exc}") from exc
            except OSError as exc:
                raise WebSocketError(f"socket error: {exc}") from exc
            if not chunk:
                raise WebSocketError("connection closed by peer")
            self._buf += chunk

    def recv_text(self, timeout: float | None = None) -> str | None:
        got = self.recv(timeout)
        if got is None:
            return None
        opcode, payload = got
        if opcode != OP_TEXT:
            raise WebSocketError("expected text frame")
        return payload.decode("utf-8", "replace")

    # ------------------------------------------------------------------ close
    def close(self, code: int = 1000) -> None:
        if self._sock is None:
            return
        try:
            self.send(struct.pack("!H", code), OP_CLOSE)
        except Exception:
            pass
        try:
            self._sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass
        self._sock = None

    def __enter__(self) -> "WebSocket":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()
