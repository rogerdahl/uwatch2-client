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

import blessed
import hjson
import pygatt
import uuid

UWATCH2_MAC = "fd:d1:c7:18:70:2d"

COMMAND_UUID = uuid.UUID("0000fee2-0000-1000-8000-00805f9b34fb")
DATA_UUID = uuid.UUID("0000fee6-0000-1000-8000-00805f9b34fb")
ASYNC_RESPONSE_UUID = uuid.UUID("0000fee3-0000-1000-8000-00805f9b34fb")

CONNECT_TIMEOUT_SEC = 60
COMMANDS_PATH = "./commands.hjson"

# 0x01020304 = 16909060
HEX_01_02_03_04 = 0x1020304


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

    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=logging_level, format="%(levelname)-8s %(message)s",
    )
    logging.getLogger("pygatt.backends.gatttool.gatttool").setLevel(logging_level)
    logging.getLogger("pygatt.device").setLevel(logging_level)

    uwatch2 = Uwatch2()
    uwatch2.run(*args.command)


class Uwatch2(object):
    def __init__(self):
        self.commands_path = COMMANDS_PATH
        self.cmd_dict = hjson.loads(pathlib.Path(self.commands_path).read_text())
        self.adapter = pygatt.GATTToolBackend()
        self.device = None
        self.term = blessed.Terminal()
        self.input_str = ""
        self.at_input = False
        self.is_connected = False
        self.status_str = None
        self.last_cmd_key = None

    def run(self, *command_tup):
        try:
            self.adapter.start()
            self.start()
            if not command_tup:
                self.interactive()
            else:
                self.query(*command_tup)
        except KeyboardInterrupt:
            pass
        finally:
            self.adapter.stop()

    def start(self):
        log.info("Starting...")
        self.connect()
        self.device.register_disconnect_callback(
            functools.partial(disconnect_callback, self)
        )
        self.device.bond(permanent=False)
        self.subscribe_all()

    def connect(self):
        log.info("Connecting...")
        self.device = self.adapter.connect(
            UWATCH2_MAC,
            timeout=CONNECT_TIMEOUT_SEC
            # , auto_reconnect=True
        )
        self.is_connected = True
        log.info("Connected")

    def reconnect(self):
        self.start()
        return

        log.info("Reconnecting...")

        log.debug(f"my device = {self.device}")
        log.debug(f"_connected_device = {self.adapter._connected_device}")

        self.adapter.reconnect(self.device, timeout=CONNECT_TIMEOUT_SEC)
        self.is_connected = True
        self.status_str = None
        log.info("Reconnected")

        # reconnect() includes resubscribe_all()
        # log.info("Resubscribing...")
        # self.device.resubscribe_all()
        # log.info("Resubscribed")

    def interactive(self):
        while True:
            try:
                cmd_str = self.input_prompt()
                cmd_key, *arg_tup = cmd_str.split(" ")
                if cmd_key == "exit":
                    return
                elif cmd_key in ("list", "l"):
                    self.print_commands()
                else:
                    self.query(cmd_key, *arg_tup)
            except ClientError as e:
                log.error(f"Error: {e}")
            except Exception as e:
                log.error(f"Exception: {repr(e)}")

    def query(self, cmd_key, *arg_tup):
        """Send a query."""
        try:
            cmd_dict = self.cmd_dict[cmd_key]
        except LookupError:
            raise ClientError(f"Invalid command key: {cmd_key}")
        else:
            log.info(
                f'Running command: {cmd_key} ({cmd_dict["cmd_name"]}) '
                f"{self.format_args(*arg_tup)}"
            )

        cmd_key_byte = self.get_bytes(cmd_key)
        arg_pack = self.get_arg_pack(cmd_key)
        if arg_pack:
            try:
                int_tup = map(int, arg_tup)
            except ValueError:
                raise ClientError(f"Arguments must be decimal numbers: {arg_tup}")
            try:
                arg_bytes = struct.pack(arg_pack, *int_tup)
            except Exception as e:
                raise ClientError(
                    f"Arguments do not match required: {int_tup}: {str(e)}"
                )
        else:
            if arg_tup:
                raise ClientError(
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

        if not self.is_connected:
            self.reconnect()

        self.write_command(COMMAND_UUID, pkg_bytes)
        self.read_command(COMMAND_UUID)

    def send_message(self, s):
        pass

    def read_all(self):
        for characteristic_uuid in self.device.discover_characteristics().keys():
            log.debug(f"Read {characteristic_uuid}:")
            try:
                b = self.device.char_read(characteristic_uuid)
                log.debug(f"  {self.get_hex_str(b)}")
            except pygatt.exceptions.NotificationTimeout:
                log.debug("   timeout")

    def subscribe_all(self):
        for characteristic_uuid in self.device.discover_characteristics().keys():
            log.debug(f"Subscribe {characteristic_uuid}:")
            try:
                result = self.device.subscribe(
                    characteristic_uuid,
                    callback=functools.partial(
                        data_callback, self, characteristic_uuid
                    ),
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
            raise ClientError(f"Invalid hex bytes: {hex_str}")

    def read_command(self, characteristic_uuid):
        res = self.device.char_read(characteristic_uuid)
        log.debug(f"<- {self.get_hex_str(res)}")

    def write_command(self, characteristic_uuid, b):
        """Write to characteristic"""
        log.debug(f"-> {self.get_hex_str(b)}")
        result = self.device.char_write(characteristic_uuid, b)
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

    def input_prompt(self):
        self.at_input = True
        self.restore_input_prompt()
        with self.term.cbreak():
            while True:
                c = self.term.inkey()
                print(f"{c}", end="", flush=True)
                if c == "\n":
                    break
                elif self.input_str and ord(c) == 127:  # self.term.KEY_BACKSPACE:
                    self.input_str = self.input_str[:-1]
                    print(self.term.move_left + self.term.clear_eol, end="", flush=True)
                else:
                    self.input_str += c
        input_str = self.input_str
        self.input_str = ""
        self.at_input = False
        self.status_str = None
        return input_str

    def clear_input_prompt(self):
        if self.at_input:
            print("\r" + self.term.clear_eol, end="", flush=True)

    def restore_input_prompt(self):
        log.info("")
        log.info("Send command:  <command (2-digit hex)> [argument (decimal), ...]")
        log.info("List commands: list, l")
        log.info("Exit:          exit, x")
        if self.status_str:
            log.info("")
            log.info(self.status_str)
        if self.at_input:
            sys.stdout.flush()
            print(f"\n> {self.input_str}", end="", flush=True)


def data_callback(uwatch2_obj, characteristic_uuid, handle, value):
    """Called when a notification is received from one of the subscribed interfaces.

    handle -- integer, characteristic read handle the data was received on
    value -- bytearray, the data returned in the notification
    """
    uwatch2_obj.clear_input_prompt()

    payload_bytes = Uwatch2.strip_header(value)
    log.info(
        f'<- (async) characteristic_uuid="{characteristic_uuid}" handle="{hex(handle)}" '
        f'value="{Uwatch2.get_hex_str(value)}" '
    )

    cmd_key = Uwatch2.get_hex_str(payload_bytes[0:1])
    value_bytes = payload_bytes[1:]

    log.debug(f"     payload_bytes: {Uwatch2.get_hex_str(payload_bytes)}")
    log.debug(f"     cmd_key: {cmd_key}")
    log.debug(f"     value_bytes: {Uwatch2.get_hex_str(value_bytes)}")

    if characteristic_uuid == ASYNC_RESPONSE_UUID:
        response_unpack = uwatch2_obj.get_response_unpack(cmd_key)
        if response_unpack:
            # response_tup = struct.unpack(response_unpack, bytes(reversed(value_bytes)))
            response_tup = struct.unpack(response_unpack, value_bytes)
            parsed_str = " ".join(shlex.quote(str(s)) for s in response_tup)
        else:
            parsed_str = f"<parsing not implemented>"
        uwatch2_obj.status_str = (
            f"Command {cmd_key} returned: {parsed_str} "
            f"(raw bytes: {Uwatch2.get_hex_str(value_bytes)})"
        )
        log.debug(f"     {uwatch2_obj.status_str}")

    uwatch2_obj.restore_input_prompt()


def disconnect_callback(uwatch2_obj, event_dict):
    uwatch2_obj.is_connected = False
    uwatch2_obj.clear_input_prompt()
    disconnect_str = "Disconnected"
    log.debug(disconnect_str)
    debug_pprint(event_dict)
    uwatch2_obj.status_str = disconnect_str
    uwatch2_obj.restore_input_prompt()


def debug_pprint(o):
    for line in pprint.pformat(o).splitlines():
        log.debug(line)


class ClientError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
