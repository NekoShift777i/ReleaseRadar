
import socket

import pytest


def test_external_connection_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        with pytest.raises(
            AssertionError,
            match="Запрещено внешнее сетевое соединение",
        ):
            connection.connect(("192.0.2.1", 443))
