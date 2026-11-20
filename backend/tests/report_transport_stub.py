"""Stub for the outbound report transport (#557) — no real report server in tests.

``report_client`` sends through ``httpx.AsyncClient(transport=report_client._transport())``.
Tests replace ``_transport`` with an ``httpx.MockTransport`` whose handler is a
``TransportRecorder``: it records every request (URL + decoded multipart parts in the
shape ``[(name, (None, text))]`` / ``[(name, (filename, bytes, content_type))]``) and
answers with the next outcome — an ``httpx.Response``, an exception to raise, or an
``async`` callable ``(request) -> Response`` (for slow servers).
"""
from __future__ import annotations

import inspect
import re

import httpx


def parse_multipart(content_type: str, body: bytes) -> list[tuple[str, tuple]]:
    m = re.search(r'boundary="?([^";]+)"?', content_type)
    assert m, content_type
    boundary = b"--" + m.group(1).encode()
    parts = []
    for chunk in body.split(boundary)[1:]:
        if chunk.startswith(b"--"):
            break
        chunk = chunk[2:] if chunk.startswith(b"\r\n") else chunk
        head, _, data = chunk.partition(b"\r\n\r\n")
        if data.endswith(b"\r\n"):
            data = data[:-2]
        headers = {}
        for line in head.decode("utf-8").split("\r\n"):
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        disp = headers["content-disposition"]
        name = re.search(r'name="([^"]*)"', disp).group(1)
        fn = re.search(r'filename="([^"]*)"', disp)
        if fn is None:
            parts.append((name, (None, data.decode("utf-8"))))
        else:
            parts.append((name, (fn.group(1), data, headers.get("content-type"))))
    return parts


class TransportRecorder:
    def __init__(self, *outcomes):
        self.calls: list[dict] = []
        self._outcomes = list(outcomes)

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        self.calls.append({
            "url": str(request.url),
            "kwargs": {"files": parse_multipart(request.headers["content-type"], body)},
            "request": request,
        })
        out = self._outcomes.pop(0) if len(self._outcomes) > 1 else self._outcomes[0]
        if isinstance(out, BaseException):
            raise out
        if callable(out) and not isinstance(out, httpx.Response):
            out = out(request)
            if inspect.isawaitable(out):
                out = await out
        return out

    def fields(self, i=0):
        return {name: part[1] for name, part in self.calls[i]["kwargs"]["files"]
                if part[0] is None}

    def attachment(self, i=0):
        found = [part for name, part in self.calls[i]["kwargs"]["files"] if name == "attachment"]
        return found[0] if found else None


def install(monkeypatch, *outcomes) -> TransportRecorder:
    from app.services import report_client

    rec = TransportRecorder(*outcomes)
    monkeypatch.setattr(report_client, "_transport", lambda: httpx.MockTransport(rec))
    return rec
