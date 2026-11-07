
import ipaddress
import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def is_local(address):
        if not isinstance(address, tuple) or not address:
            return False

        host = address[0]

        try:
            return ipaddress.ip_address(host).is_loopback
        except (ValueError, TypeError):
            return False

    def guarded_connect(self, address):
        if not is_local(address):
            raise AssertionError(
                f"Запрещено внешнее сетевое соединение: {address}"
            )

        return original_connect(self, address)

    def guarded_connect_ex(self, address):
        if not is_local(address):
            raise AssertionError(
                f"Запрещено внешнее сетевое соединение: {address}"
            )

        return original_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
