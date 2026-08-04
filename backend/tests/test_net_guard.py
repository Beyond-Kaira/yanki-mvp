"""Shared network guard resolution behavior."""

import socket

from app.net_guard import is_public_host


def test_resolution_failure_is_rejected(monkeypatch) -> None:
    def fail_resolution(*args, **kwargs):
        raise socket.gaierror("no DNS answer")

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)

    assert is_public_host("does-not-resolve.example") is False


def test_any_private_dns_answer_rejects_host(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
        ],
    )

    assert is_public_host("mixed.example") is False
