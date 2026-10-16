"""Prevent external provider access during installed-server startup checks."""
import socket
_connect = socket.socket.connect
_connect_ex = socket.socket.connect_ex

def connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise OSError('Network disabled for baseline startup verification')
    return _connect(self, address)

def connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        raise OSError('Network disabled for baseline startup verification')
    return _connect_ex(self, address)

def no_dns(*args, **kwargs):
    raise OSError('DNS disabled for baseline startup verification')

socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = no_dns
