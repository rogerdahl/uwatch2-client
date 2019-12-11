#!/usr/bin/env python

"""Read and write settings on a uwatch2 watch.

Based on: https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9
"""
import argparse
import binascii
import functools
import logging
import pathlib
import pprint
import re
import shlex
import struct
import sys

import hjson
import pygatt

UWATCH2_MAC = "fd:d1:c7:18:70:2d"

COMMAND_UUID = "0000fee2-0000-1000-8000-00805f9b34fb"
DATA_UUID = "0000fee6-0000-1000-8000-00805f9b34fb"

CONNECT_TIMEOUT_SEC = 60
COMMANDS_PATH = "./commands.hjson"

log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debug level logging")
    parser.add_argument(
        "command",
        nargs="*",
        help="Run single command without entering interactive mode",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )
    logging.getLogger("pygatt.backends.gatttool.gatttool").setLevel(logging.ERROR)
    logging.getLogger("pygatt.device").setLevel(logging.ERROR)

    uwatch2 = Uwatch2()
    uwatch2.run(*args.command)


class Uwatch2(object):
    def __init__(self):
        self.commands_path = COMMANDS_PATH
        self.cmd_dict = hjson.loads(pathlib.Path(self.commands_path).read_text())
        # self.print_commands()
        self.adapter = pygatt.GATTToolBackend()
        self.device = None

    def run(self, *command_tup):
        try:
            log.info("Starting...")
            self.adapter.start()
            self.device = self.adapter.connect(UWATCH2_MAC, timeout=CONNECT_TIMEOUT_SEC)
            self.device.register_disconnect_callback(disconnect_callback)
            self.device.bond(permanent=False)
            self.subscribe_all()
            # self.read_all()
            if not command_tup:
                self.interactive()
            else:
                self.query(*command_tup)
        finally:
            self.adapter.stop()

    def interactive(self):
        while True:
            try:
                log.info("")
                log.info(
                    "Send command:  <command (2-digit hex)> [argument (decimal), ...]"
                )
                log.info("List commands: help")
                log.info("Exit:          exit")
                cmd_str = input("> ")
                cmd_key, *arg_tup = cmd_str.split(" ")

                if cmd_key == "exit":
                    return
                elif cmd_key == "list":
                    self.print_commands()
                else:
                    self.query(cmd_key, *arg_tup)
            except Exception as e:
                log.error(f"Error: {repr(e)}")

    def query(self, cmd_key, *arg_tup):
        """Send a query."""
        try:
            cmd_dict = self.cmd_dict[cmd_key]
        except LookupError:
            raise ValueError(f'Invalid command key: {cmd_key}')
        else:
            log.info('')
            log.info(
                f'Running command: {cmd_key} ({cmd_dict["cmd_name"]}) '
                f'{self.format_args(*arg_tup)}'
            )
            log.info('')

        cmd_key_byte = self.get_bytes(cmd_key)
        arg_pack = self.get_arg_pack(cmd_key)
        if arg_pack:
            try:
                int_tup = map(int, arg_tup)
            except ValueError:
                raise ValueError(f"Arguments must be decimal numbers: {arg_tup}")
            try:
                arg_bytes = struct.pack(arg_pack, *int_tup)
            except Exception as e:
                raise ValueError(
                    f"Arguments do not match required: {int_tup}: {str(e)}"
                )
        else:
            if arg_tup:
                raise ValueError(
                    "Command does not take parameters or is not implemented"
                )
            arg_bytes = b""

        payload_bytes = cmd_key_byte + arg_bytes
        header_bytes = self.gen_header(payload_bytes)
        pkg_bytes = header_bytes + payload_bytes

        log.debug(f"cmd_key_byte: {self.get_hex_str(cmd_key_byte)}")
        log.debug(f"arg_bytes: {self.get_hex_str(arg_bytes)}")
        log.debug(f"payload_bytes: {self.get_hex_str(payload_bytes)}")
        log.debug(f"header_bytes: {self.get_hex_str(header_bytes)}")
        log.debug(f"pkg_bytes: {self.get_hex_str(pkg_bytes)}")

        self.write_command(COMMAND_UUID, pkg_bytes)
        self.read_command(COMMAND_UUID)

    def send_message(self, s):
        pass

    def read_all(self):
        for uuid in self.device.discover_characteristics().keys():
            log.debug(f"Read {uuid}:")
            try:
                b = self.device.char_read(uuid)
                log.debug(f"  {self.get_hex_str(b)}")
            except pygatt.exceptions.NotificationTimeout:
                log.debug("   timeout")

    def subscribe_all(self):
        for uuid in self.device.discover_characteristics().keys():
            log.debug(f"Subscribe {uuid}:")
            try:
                result = self.device.subscribe(
                    uuid,
                    callback=functools.partial(data_callback, self, uuid),
                    indication=False,
                    wait_for_response=False,
                )
                log.debug(f"  result={result}")
            except pygatt.exceptions.NotificationTimeout:
                log.debug("   timeout")

    @staticmethod
    def get_hex_str(b):
        hex_str = binascii.hexlify(b).decode("utf-8")
        hex_str = re.sub(r"(..)", r"\1 ", hex_str)
        return hex_str.strip()

    @staticmethod
    def get_bytes(hex_str):
        try:
            return binascii.unhexlify(hex_str.replace(" ", ""))
        except ValueError:
            raise Exception(f"Invalid hex bytes: {hex_str}")

    def write_command(self, uuid, b):
        """Write to the command interface at """
        log.debug(f"-> {self.get_hex_str(b)}")
        result = self.device.char_write(uuid, b)
        if result is not None:
            log.debug(f"-> result: {result}")

    def gen_header(self, payload_bytes):
        """Generate packet header.

        0xfe - start byte
        0xea - some kind of protocol version
        0x10 - some kind of protocol version
        byte - payload length in bytes + 4
        """
        return self.get_bytes("fe ea 10") + struct.pack("b", len(payload_bytes) + 4)

    @staticmethod
    def strip_header(b):
        """Strip the header from a packet.
        """
        return b[4:]

    def read_command(self, uuid):
        res = self.device.char_read(uuid)
        log.debug(f"<- {self.get_hex_str(res)}")

    def print_commands(self):
        log.info("Commands:")
        for cmd_key, param_dict in self.cmd_dict.items():
            log.info(
                f'{"* " if param_dict["tested_and_working"] else "  "}'
                f"{cmd_key} "
                f'{param_dict["arg_name"] or "":<20}{param_dict["cmd_name"]}'
            )

    def get_response_unpack(self, cmd_key):
        return self.cmd_dict.get(cmd_key, {}).get("response_unpack", None)

    def get_arg_pack(self, cmd_key):
        return self.cmd_dict.get(cmd_key, {}).get("arg_pack", None)

    def format_args(self, *arg_tup):
        return " ".join(shlex.quote(str(s)) for s in arg_tup)


def data_callback(uwatch2_obj, uuid, handle, value):
    """Called when a notification is received from one of the subscribed interfaces.

    handle -- integer, characteristic read handle the data was received on
    value -- bytearray, the data returned in the notification
    """
    payload_bytes = Uwatch2.strip_header(value)
    log.debug(
        f'Received data: uuid="{uuid}" handle="{hex(handle)}" value="{Uwatch2.get_hex_str(value)}" '
    )

    cmd_key = Uwatch2.get_hex_str(payload_bytes[0:1])
    value_bytes = payload_bytes[1:]

    log.info(f"Response: payload_bytes: {Uwatch2.get_hex_str(payload_bytes)}")
    log.info(f"Response: cmd_key: {cmd_key}")
    log.info(f"Response: value_bytes: {Uwatch2.get_hex_str(value_bytes)}")

    response_unpack = uwatch2_obj.get_response_unpack(cmd_key)
    if response_unpack:
        response_tup = struct.unpack(response_unpack, bytes(reversed(value_bytes)))
        log.info('')
        log.info(
            f'Parsed response: {" ".join(shlex.quote(str(s)) for s in response_tup)}'
        )
        log.info('')
    else:
        log.info("Parsing not implemented for response")

    # Since notifications often come while waiting at the input prompt, write a new
    # prompt.
    log.info("> ")


def disconnect_callback(d):
    log.info(f"Disconnected")
    log.debug(pprint.pformat(d))
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
