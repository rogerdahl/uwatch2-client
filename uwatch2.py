#!/usr/bin/env python

"""Read and write settings on a uwatch2 watch.

Based on: https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9
"""
import argparse
import binascii
import contextlib
import functools
import io
import logging
import pathlib
import pprint
import re
import shlex
import struct
import sys
import uuid

import blessed
import hjson
import pygatt

UWATCH2_MAC = "fd:d1:c7:18:70:2d"

# 0x01020304 = 16909060
HEX_01_02_03_04 = 0x1020304


log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debug level logging")
    ex_group = parser.add_mutually_exclusive_group()
    ex_group.add_argument(
        "--mac", metavar="11:22:33:44:55:66", help="Connect by MAC address"
    )
    ex_group.add_argument("--name", metavar="mywatch", help="Connect by watch name")
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

    try:
        uwatch2 = Uwatch2(mac_addr=args.mac, name=args.name, debug=args.debug)
        if args.command:
            uwatch2.command(*args.command)
        else:
            uwatch2.interactive()
    except KeyboardInterrupt:
        if args.debug:
            raise
    except ClientError as e:
        log.error(f"Error: {e}")


class Uwatch2(object):
    COMMAND_UUID = uuid.UUID("0000fee2-0000-1000-8000-00805f9b34fb")
    DATA_UUID = uuid.UUID("0000fee6-0000-1000-8000-00805f9b34fb")
    ASYNC_RESPONSE_UUID = uuid.UUID("0000fee3-0000-1000-8000-00805f9b34fb")
    ACCELERATION_UUID = uuid.UUID("0000fcc1-0000-1000-8000-00805f9b34fb")

    DEFAULT_WATCH_NAME = "Uwatch2"
    DEFAULT_AUTO_RECONNECT = True
    DEFAULT_CONNECT_TIMEOUT_SEC = 60

    COMMANDS_PATH = "./commands.hjson"

    def __init__(
        self,
        mac_addr=None,
        name=None,
        auto_reconnect=None,
        connect_timeout_sec=None,
        debug=False,
    ):
        self._mac_addr = mac_addr
        self._name = name or self.DEFAULT_WATCH_NAME
        self._auto_reconnect = auto_reconnect or self.DEFAULT_AUTO_RECONNECT
        self._connect_timeout_sec = (
            connect_timeout_sec or self.DEFAULT_CONNECT_TIMEOUT_SEC
        )
        self._debug = debug

        self._term = blessed.Terminal()
        self._cmd_dict = hjson.loads(pathlib.Path(self.COMMANDS_PATH).read_text())
        self._raw_cmd_dict = self._cmd_dict['raw_commands']
        self._wrap_cmd_dict = self._cmd_dict['wrap_commands']
        self._adapter = pygatt.GATTToolBackend()
        self._device = None

        self._input_str = ""
        self._waiting_at_input_prompt = False
        self._is_connected = False
        self._status_str = None
        self._last_cmd_key = None

    def command(self, *command_tup):
        """Issue a single command to the watch, then exit."""
        with self._run():
            self._dispatch_cmd(" ".join(command_tup))

    def interactive(self):
        with self._run():
            self._interactive()

    @contextlib.contextmanager
    def _run(self):
        logging_level = logging.DEBUG if self._debug else logging.WARNING
        logging.getLogger("pygatt.backends.gatttool.gatttool").setLevel(logging_level)
        logging.getLogger("pygatt.device").setLevel(logging_level)
        try:
            self._adapter.start()
            self._start()
            yield
        finally:
            self._adapter.stop()

    def _start(self):
        log.info("Starting...")

        if self._mac_addr is None:
            self._mac_addr = self._find_mac_addr()

        self._connect()
        self._device.register_disconnect_callback(
            functools.partial(disconnect_callback, self)
        )
        self._device.bond(permanent=True)
        # self._subscribe_all()
        self._subscribe(self.ASYNC_RESPONSE_UUID)
        self._subscribe(self.ACCELERATION_UUID)

    def _find_mac_addr(self):
        log.info("Searching for BLE devices...")

        discovered_list = self._adapter.scan(10, run_as_root=True)
        if not discovered_list:
            raise ClientError("No MAC address discovered or provided")

        log.info("Discovered BLE devices:")
        mac_addr = None
        for disc_dict in discovered_list:
            log.info(f'  {disc_dict["name"]}: {disc_dict["address"]}')
            if mac_addr is None and self._name in disc_dict["name"]:
                mac_addr = disc_dict["address"]

        if mac_addr is None:
            raise ClientError(f"No devices found containing name: {self._name}")
        log.info(
            f'Using MAC address for first device that contains name "{self._name}": '
            f'"{mac_addr}"'
        )
        log.info(f"Tip: Connect faster next time with {sys.argv[0]} --mac {mac_addr}")
        return mac_addr

    def _connect(self):
        log.info(f"Connecting to MAC {self._mac_addr}...")
        self._device = self._adapter.connect(
            self._mac_addr,
            timeout=self._connect_timeout_sec,
            auto_reconnect=self._auto_reconnect,
        )
        self._is_connected = True
        self.set_status("Connected")

    def _reconnect(self):
        if self._auto_reconnect:
            self.set_status("Automatic reconnect")
            self._is_connected = True
            return

        log.info("Reconnecting...")

        # log.debug(f"my device = {self._device}")
        # log.debug(f"_connected_device = {self._adapter._connected_device}")

        self._adapter.reconnect(self._device, timeout=self._connect_timeout_sec)
        self._is_connected = True
        self.set_status("Reconnected")

        # reconnect() includes resubscribe_all()
        # log.info("Resubscribing...")
        # self._device.resubscribe_all()
        # log.info("Resubscribed")

    def _interactive(self):
        while True:
            try:
                cmd_str = self._input_prompt()
                self._dispatch_cmd(cmd_str)
            except ClientError as e:
                self.set_status(f"Error: {e}")

    def _dispatch_cmd(self, cmd_str):
        """Split command into command and arguments, then call the appropriate
        command method.
        """
        cmd_key, *arg_tup = cmd_str.split(" ")
        if cmd_key == "exit":
            return
        elif cmd_key in ("list", "l"):
            self._print_commands()
        elif cmd_key == "msg":
            self.send_message(" ".join(arg_tup))
        else:
            self._send_raw_cmd(cmd_key, *arg_tup)

    def send_message(self, msg_str):
        if msg_str == "":
            msg_str = (
                "Got blank message. Sending test: ABC xyz 0123456789 !@#$%^&*() "
                "ฉัน 䦹䦺 a ä æ ⱥ à â ã"
            )
        msg_bytes = msg_str.encode("utf-8")
        log.info(f"Sending message: {msg_bytes}")
        self.send_packet(bytes([0x41, len(msg_bytes)]) + msg_bytes)

    def _send_raw_cmd(self, cmd_key, *arg_tup):
        """Send a query."""
        try:
            cmd_dict = self._raw_cmd_dict[cmd_key]
        except LookupError:
            raise ClientError(f"Invalid command key: {cmd_key}")

        arg_pack = self._get_arg_pack(cmd_key)
        if arg_pack:
            try:
                int_tup = list(map(int, arg_tup))
            except ValueError:
                raise ClientError(f"Arguments must be decimal numbers: {arg_tup}")
            try:
                arg_bytes = struct.pack(arg_pack, *int_tup)
            except Exception as e:
                raise ClientError(
                    f"Arguments do not match required format: "
                    f'{" ".join(str(int_tup))}: {str(e)}'
                )
        else:
            if arg_tup:
                raise ClientError(
                    "Command does not take parameters or is not implemented"
                )
            arg_bytes = b""

        log.info(
            f'Running command: {cmd_key} ({cmd_dict["cmd_desc"]}) '
            f"{self._format_args(*arg_tup)}"
        )

        self.send_packet(self._get_bytes(cmd_key) + arg_bytes)
        self._read_command(self.COMMAND_UUID)

    def send_packet(self, payload_bytes):
        header_bytes = self._gen_header(payload_bytes)
        pkg_bytes = header_bytes + payload_bytes

        log.info(f"Sending packet: {self._get_hex_str(pkg_bytes)}")
        log.debug(f"  Header:  {self._get_hex_str(header_bytes)}")
        log.debug(f"  Payload: {self._get_hex_str(payload_bytes)}")

        if not self._is_connected:
            self._reconnect()

        # self._write_command(self.COMMAND_UUID, pkg_bytes)
        buf = io.BytesIO(pkg_bytes)
        while True:
            # ATT write requests and notifications contain max 20 data bytes
            chunk = buf.read(20)
            if not chunk:
                return
            log.debug(f"  Writing chunk: {self._get_hex_str(chunk)}")
            self._write_command(self.COMMAND_UUID, chunk)

    def _read_all(self):
        for char_uuid in self._device.discover_characteristics().keys():
            log.debug(f"Read {char_uuid}:")
            try:
                b = self._device.char_read(char_uuid)
                log.debug(f"  {self._get_hex_str(b)}")
            except pygatt.exceptions.NotificationTimeout:
                log.debug("   timeout")

    def _subscribe_all(self):
        """Subscribe to all characteristics (for reverse engineering / discovery)"""
        for char_uuid in self._device.discover_characteristics().keys():
            self._subscribe(char_uuid)

    def _subscribe(self, char_uuid):
        """Subscribe and register a unique callback."""
        log.debug(f"Subscribe {char_uuid}:")
        result = self._device.subscribe(
            char_uuid,
            callback=functools.partial(data_callback, self, self.ASYNC_RESPONSE_UUID),
            indication=False,
            wait_for_response=False,
        )
        log.debug(f"  result={result}")

    def _get_hex_str(self, b):
        hex_str = binascii.hexlify(b).decode("utf-8")
        hex_str = re.sub(r"(..)", r"\1 ", hex_str)
        return hex_str.strip()

    def _get_bytes(self, hex_str):
        try:
            return binascii.unhexlify(hex_str.replace(" ", ""))
        except ValueError:
            raise ClientError(f"Invalid hex bytes: {hex_str}")

    def _gen_header(self, payload_bytes):
        """Generate packet header."""
        return self._get_bytes("fe ea 10") + struct.pack("b", len(payload_bytes) + 4)

    def _read_command(self, char_uuid):
        res = self._device.char_read(char_uuid)
        log.debug(f"<- {self._get_hex_str(res)}")

    def _write_command(self, char_uuid, pkg_bytes):
        """Write to characteristic"""
        log.debug(f"-> {self._get_hex_str(pkg_bytes)}")
        result = self._device.char_write(char_uuid, pkg_bytes)
        if result is not None:
            log.debug(f"-> result: {result}")

    @staticmethod
    def _strip_header(b):
        """Strip the header from a packet.
        """
        return b[4:]

    def _print_commands(self):
        log.info("Commands:")
        def p(cmd_dict):
            for cmd_key, param_dict in cmd_dict.items():
                # Only list non-implemented in debug mode
                if not self._debug and not param_dict.get("tested_and_working", False):
                    continue
                log.info(
                    f'{"*" if param_dict.get("tested_and_working", True) else " "} '
                    f'{cmd_key:<3} '
                    f'{param_dict["arg_desc"] or "":<40} '
                    f'{param_dict["cmd_desc"]}'
                )
        p(self._raw_cmd_dict)
        p(self._wrap_cmd_dict)

    def _get_response_unpack(self, cmd_key):
        return self._raw_cmd_dict.get(cmd_key, {}).get("response_unpack", None)

    def _get_arg_pack(self, cmd_key):
        return self._raw_cmd_dict.get(cmd_key, {}).get("arg_pack", None)

    def _format_args(self, *arg_tup):
        return " ".join(shlex.quote(str(s)) for s in arg_tup)

    def _input_prompt(self):
        self._waiting_at_input_prompt = True
        self._restore_input_prompt()
        with self._term.cbreak():
            while True:
                c = self._term.inkey()
                # Checking for length == 1 filters out control characters
                if len(c) != 1:
                    continue
                print(f"{c}", end="", flush=True)
                if c == "\n":
                    break
                elif self._input_str and ord(c) == 127:  # 127 == backspace
                    self._input_str = self._input_str[:-1]
                    print(
                        self._term.move_left + self._term.clear_eol, end="", flush=True
                    )
                else:
                    self._input_str += c
        input_str = self._input_str
        self._input_str = ""
        self._waiting_at_input_prompt = False
        return input_str

    def _clear_input_prompt(self):
        if self._waiting_at_input_prompt:
            print("\r" + self._term.clear_eol, end="", flush=True)

    def _restore_input_prompt(self):
        if not self._waiting_at_input_prompt:
            return
        log.info("")
        log.info("Time periods:")
        log.info("  - Buggy firmware cannot handle time periods that pass midnight. ")
        log.info("    E.g.: Cannot set Quick View enabled from 07:00 to 01:00.")
        log.info("")
        log.info(
                 "Send message:      msg <message> (blank message sends Unicode test string)"
        )
        log.info("Send raw command:  <command (2-digit hex)> [argument (decimal), ...]")
        log.info("List commands:     list, l")
        log.info("Exit:              exit, x")
        if self._status_str:
            log.info("")
            log.info(f"Status: {self._status_str}")
        if self._waiting_at_input_prompt:
            sys.stdout.flush()
            print(f"\n> {self._input_str}", end="", flush=True)

    def set_status(self, status_str):
        self._status_str = status_str
        log.info(status_str)


def data_callback(uwatch2_obj, char_uuid, handle, value):
    """Called when a notification is received from one of the subscribed interfaces.

    handle -- integer, characteristic read handle the data was received on
    value -- bytearray, the data returned in the notification
    """
    payload_bytes = uwatch2_obj._strip_header(value)
    cmd_key = uwatch2_obj._get_hex_str(payload_bytes[0:1])
    value_bytes = payload_bytes[1:]

    if char_uuid == uwatch2_obj.ASYNC_RESPONSE_UUID and handle == 0x39:
        response_unpack = uwatch2_obj._get_response_unpack(cmd_key)
        if response_unpack:
            try:
                # response_tup = struct.unpack(response_unpack, bytes(reversed(value_bytes)))
                response_tup = struct.unpack(response_unpack, value_bytes)
            except struct.error as e:
                parsed_str = f"Unable to parse value bytes. Error: {str(e)}"
            else:
                parsed_str = " ".join(shlex.quote(str(s)) for s in response_tup)
        else:
            parsed_str = f"<parsing not implemented>"
        uwatch2_obj.set_status(
            f"Command {cmd_key} returned: {parsed_str} "
            f"(raw bytes: {uwatch2_obj._get_hex_str(value_bytes)})"
        )

    if log.isEnabledFor(logging.DEBUG):
        uwatch2_obj._clear_input_prompt()

        log.debug(
            f'<- (async) char_uuid="{char_uuid}" handle="{hex(handle)}" '
            f'value="{uwatch2_obj._get_hex_str(value)}" '
        )
        log.debug(f"   payload_bytes: {uwatch2_obj._get_hex_str(payload_bytes)}")
        log.debug(f"   cmd_key: {cmd_key}")
        log.debug(f"   value_bytes: {uwatch2_obj._get_hex_str(value_bytes)}")

        uwatch2_obj._restore_input_prompt()


def disconnect_callback(uwatch2_obj, event_dict):
    uwatch2_obj._is_connected = False
    uwatch2_obj._clear_input_prompt()
    uwatch2_obj.set_status("Disconnected")
    debug_pprint(event_dict)
    uwatch2_obj._restore_input_prompt()


def debug_pprint(o):
    for line in pprint.pformat(o).splitlines():
        log.debug(line)


class ClientError(Exception):
    pass


if __name__ == "__main__":
    sys.exit(main())
