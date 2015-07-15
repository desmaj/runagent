import eventlet
eventlet.monkey_patch()

import sys

from runagent.server import HubServer


def make_address(addr_spec):
    host, port = addr_spec.split(':')
    return (host, int(port))


def main():
    args = sys.argv
    public_addr, control_addr = args[1:]
    HubServer(make_address(public_addr),
              make_address(control_addr))
