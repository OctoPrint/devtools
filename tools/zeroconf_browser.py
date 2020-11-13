import socket
import sys

import click
from zeroconf import (
    DNSAddress,
    DNSHinfo,
    DNSPointer,
    DNSService,
    DNSText,
    ServiceBrowser,
    Zeroconf,
)


class MyListener(object):
    TO_TEXT = {
        DNSAddress: lambda x: str(socket.inet_ntoa(x.address)),
        DNSHinfo: lambda x: x.cpu + " " + x.os,
        DNSPointer: lambda x: x.alias,
        DNSService: lambda x: "{}:{}".format(x.server, x.port),
        DNSText: lambda x: repr(x.text),
    }

    def __init__(self, fetch=False):
        self.fetch = fetch

    def remove_service(self, zeroconf, type, name):
        print("REMOVED: {}\n".format(name))

    def add_service(self, zeroconf, type, name):
        cached = zeroconf.cache.entries_with_name(name)
        print("ADDED: {}".format(name))
        for entry in cached:
            print("\t{}".format(self.to_console(entry)))

        if self.fetch:
            info = zeroconf.get_service_info(type, name)
            print("\tInfo:")
            addresses = ["{}:{}".format(socket.inet_ntoa(a), info.port) for a in info.addresses]
            for a in addresses:
                print("\t\tAddress: {}".format(a))
            print("\t\t{}".format(info))

        print("")
    
    def update_service(self, zeroconf, type, name):
        pass

    def to_console(self, entry):
        line = entry.get_type(entry.type).upper()
        for t, f in self.TO_TEXT.items():
            if isinstance(entry, t):
                line += ": " + f(entry)
                break
        else:
            line += ": " + repr(entry)
        return line


@click.command()
@click.option("--fetch", is_flag=True, help="If set, an additional query for further information will be sent for found services.")
@click.argument("service", default="_octoprint._tcp.local.")
def main(service, fetch=False):
    if not service.endswith("."):
        service += "."
    if not service.endswith("local."):
        service += "local."

    zeroconf = Zeroconf()
    listener = MyListener(fetch=fetch)
    browser = ServiceBrowser(zeroconf, service, listener)
    try:
        input("Press enter to exit...\n\n")
    finally:
        zeroconf.close()


if __name__ == "__main__":
    main()
