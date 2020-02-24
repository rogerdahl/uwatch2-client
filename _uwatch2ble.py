#!/usr/bin/env python

import binascii
import contextlib
import functools
import io
import logging
import multiprocessing
import os
import pprint
import shlex
import struct
import uuid

import pygatt

log = logging.getLogger(__name__)


class Uwatch2Ble(object):
    COMMAND_UUID = uuid.UUID("0000fee2-0000-1000-8000-00805f9b34fb")
    DATA_UUID = uuid.UUID("0000fee6-0000-1000-8000-00805f9b34fb")
    ASYNC_RESPONSE_UUID = uuid.UUID("0000fee3-0000-1000-8000-00805f9b34fb")
    ACCELEROMETER_UUID = uuid.UUID("0000fcc1-0000-1000-8000-00805f9b34fb")

    DEFAULT_WATCH_NAME = "Uwatch2"
    DEFAULT_AUTO_RECONNECT = True
    DEFAULT_CONNECT_TIMEOUT_SEC = 60

    def __init__(
        self,
        mac_addr=None,
        auto_reconnect=None,
        connect_timeout_sec=None,
        squelch_pygatt=True,
        scan_as_root=False,
        scan_for_name="Uwatch2",
    ):
        """
        :param mac_addr: The Bluetooth MAC address of the watch If provided, it is
        always used. If not provided, the UWATCH2_MAC environment variable is used
        if it exists. If the environment variable does not exist, a Bluetooth scan
        is attempted.

        squelch_pygatt (bool): Set log level for pygatt to WARNING.
        """
        # We take the liberty of tweaking chatty log output from pygatt even though
        # libraries generally shouldn't touch the logging config.
        # logging_level = logging.DEBUG if debug else logging.WARNING
        # logging.getLogger("pygatt.backends.gatttool.gatttool").setLevel(logging_level)
        # logging.getLogger("pygatt.device").setLevel(logging_level)
        if squelch_pygatt:
            logging.getLogger("pygatt").setLevel(logging.WARNING)

        self._scan_as_root = scan_as_root
        self._mac_addr = mac_addr
        self._scan_for_name = scan_for_name or self.DEFAULT_WATCH_NAME
        self._auto_reconnect = auto_reconnect or self.DEFAULT_AUTO_RECONNECT
        self._connect_timeout_sec = (
            connect_timeout_sec or self.DEFAULT_CONNECT_TIMEOUT_SEC
        )

        self._adapter = pygatt.GATTToolBackend()
        self._device = None

        self._input_str = ""
        self._waiting_at_input_prompt = False
        self._is_connected = False
        self._status_str = None

        self._async_response_handle = None

        self._manager = multiprocessing.Manager()
        self._queue = self._manager.Queue()

        # # Some async command responses are returned by callbacks in multiple chunks.
        # # It looks like the only way to tie these together is to assume that they're
        # # always returned in single sequence (without
        # self._last_async_response_cmd_key = None
        # self._response_buf = {}
        self._acc_payload_bytes = bytearray()
        self._expected_payload_byte_count = None

    def __enter__(self):
        self._adapter.start()
        self._start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        def f_(func_name):
            log.debug(f'Calling "{func_name}" on adapter...')
            try:
                getattr(self._adapter, func_name)()
            except Exception as e:
                log.debug(f'Calling "{func_name}" on adapter raised {repr(e)}')
            else:
                log.debug(f'Calling "{func_name}" on adapter completed')

        f_("stop")
        f_("reset")
        f_("kill")

    def _start(self):
        log.info("Starting...")
        self._set_mac_addr()
        self._connect()
        self._device.register_disconnect_callback(
            functools.partial(disconnect_callback, self._queue)
        )
        self._device.bond(permanent=True)
        self._subscribe(self.ASYNC_RESPONSE_UUID)
        self._subscribe(self.ACCELEROMETER_UUID)
        self._async_response_handle = self._device.get_handle(self.ASYNC_RESPONSE_UUID)
        self._accelerometer_handle = self._device.get_handle(self.ACCELEROMETER_UUID)

    def _set_mac_addr(self):
        if self._mac_addr:
            log.info(f"Using MAC address provided by client: {self._mac_addr}")
            return
        self._mac_addr = os.environ.get("UWATCH2_MAC", None)
        if self._mac_addr:
            log.info(
                f"Using MAC address from UWATCH2_MAC environment variable: {self._mac_addr}"
            )
            return
        self._mac_addr = self._find_mac_addr()
        if self._mac_addr:
            log.info(
                f'Using MAC address for first device that contains name "{self._scan_for_name}": '
                f'"{self._mac_addr}"'
            )
            log.info(
                "Tip: Connect faster next time by providing the MAC address "
                "at instantiation time, or setting the UWATCH2_MAC environment variable."
            )
            return
        raise WatchError(
            "Unable to connect to the watch. Try providing the MAC address directly."
        )

    def _find_mac_addr(self):
        log.info("Searching for BLE devices...")

        try:
            discovered_list = self._adapter.scan(10, run_as_root=self._scan_as_root)
        except pygatt.exceptions.BLEError as e:
            raise WatchBleScanError(f"Search for watch via BLE scan failed. Error: {e}")
        finally:
            self._adapter.reset()

        if not discovered_list:
            raise WatchBleScanError("No devices were discovered during BLE scan")

        log.info("Discovered BLE devices:")
        mac_addr = None
        for disc_dict in discovered_list:
            log.info(f'  {disc_dict["name"]}: {disc_dict["address"]}')
            if mac_addr is None and self._scan_for_name in disc_dict["name"]:
                mac_addr = disc_dict["address"]

        if mac_addr is None:
            raise WatchError(f"No devices found containing name: {self._scan_for_name}")

        return mac_addr

    def _connect(self):
        log.info(f"Connecting to MAC {self._mac_addr}...")
        self._device = self._adapter.connect(
            self._mac_addr,
            timeout=self._connect_timeout_sec,
            auto_reconnect=self._auto_reconnect,
        )
        self._is_connected = True

    def _reconnect(self):
        if self._auto_reconnect:
            self._is_connected = True
            return

        log.info("Reconnecting...")
        # log.debug(f"my device = {self._device}")
        # log.debug(f"_connected_device = {self._adapter._connected_device}")
        self._adapter.reconnect(self._device, timeout=self._connect_timeout_sec)
        self._is_connected = True
        # reconnect() includes resubscribe_all()
        # log.info("Resubscribing...")
        # self._device.resubscribe_all()
        # log.info("Resubscribed")

    def _send_raw_cmd(self, cmd_key, pack_str, *arg_tup):
        """Send a query."""
        try:
            int_tup = list(map(int, arg_tup))
        except TypeError:
            raise WatchError(f"Arguments must be ints or decimal numbers: {arg_tup}")

        if pack_str:
            try:
                arg_bytes = struct.pack(pack_str, *int_tup)
            except Exception as e:
                raise WatchError(
                    f"Arguments do not match required format: "
                    f'{" ".join(str(int_tup))}: {str(e)}'
                )
        else:
            arg_bytes = bytes()

        self._send_packet(bytes([cmd_key]) + arg_bytes)

    def _get_raw_cmd(self, cmd_key, pack_str, unpack_str, *arg_tup):
        """Query with response"""
        self._send_raw_cmd(cmd_key, pack_str, *arg_tup)
        return self._get_response(cmd_key, unpack_str)

    def _send_packet(self, payload_bytes):
        header_bytes = self._gen_header(payload_bytes)
        pkg_bytes = header_bytes + payload_bytes

        log.debug(f"Sending packet: {self._get_hex_str(pkg_bytes)}")
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
            self._write_to_characteristic(self.COMMAND_UUID, chunk)

    def _read_all(self):
        for charcs_uuid in self._device.discover_characteristics().keys():
            log.debug(f"Read {charcs_uuid}:")
            try:
                b = self._device.char_read(charcs_uuid)
                log.debug(f"  {self._get_hex_str(b)}")
            except pygatt.exceptions.NotificationTimeout:
                log.debug("   timeout")

    def _subscribe_all(self):
        """Subscribe to all characteristics (for reverse engineering / discovery)"""
        for charcs_uuid in self._device.discover_characteristics().keys():
            self._subscribe(charcs_uuid)

    def _subscribe(self, charcs_uuid):
        """Subscribe and register a unique callback."""
        log.debug(f"Subscribe {charcs_uuid}:")
        result = self._device.subscribe(
            charcs_uuid,
            # callback=functools.partial(data_callback, self, self.ASYNC_RESPONSE_UUID),
            callback=functools.partial(data_callback, self._queue),
            indication=False,
            wait_for_response=False,
        )
        log.debug(f"  result={result}")

    #
    # pkg_bytes = header_bytes + payload_bytes
    # header_bytes = fe ea 10 N where N is number of payload bytes
    #

    def _get_hex_str(self, b):
        # noinspection PyArgumentList
        return binascii.hexlify(b, " ").decode("ascii")

    def _get_bytes(self, hex_str):
        try:
            return binascii.unhexlify(hex_str.replace(" ", ""))
        except ValueError:
            raise WatchError(f"Invalid hex bytes: {hex_str}")

    def _gen_header(self, payload_bytes):
        """Generate packet header."""
        return self._get_bytes("fe ea 10") + struct.pack("B", len(payload_bytes) + 4)

    def _get_response(self, cmd_key, unpack_str):
        """Get the response from a previously issued command of type {cmd_key}, and
        return it unpacked as according to the {unpack_str} struct format string.

        Callback methods outside of the class are called by pygatt to deliver
        notifications from characteristics for which we have subscribed. The callbacks
        add the notifications to a queue that we keep reading from until we either get
        the notification for which we are waiting or the watch is disconnected.
        """
        while True:
            msg_type, *msg_tup = self._queue.get()
            # log.debug(f"Read from queue: msg_type={msg_type} msg_tup={msg_tup}")
            if msg_type == "notification":
                recv_charcs_handle, recv_pkg_bytes = msg_tup
                if recv_charcs_handle == self._async_response_handle:
                    acc_payload_bytes = self._handle_async_response(
                        cmd_key, recv_pkg_bytes
                    )
                    if acc_payload_bytes:
                        return self.unpack_payload_bytes(acc_payload_bytes, unpack_str)

                    # return self._handle_async_response(cmd_key, unpack_str,
                    #                                    recv_pkg_bytes)
                elif recv_charcs_handle == self._accelerometer_handle:
                    self._handle_accelerometer(recv_pkg_bytes)
                else:
                    raise WatchError(
                        "Received unknown notification. Missing handler for a subscribed "
                        "characteristic?"
                    )

            elif msg_type == "disconnected":
                self._handle_disconnect(*msg_tup)
            else:
                raise WatchError("Unknown callback message type")

    #     # payload_bytes = self._get_payload(recv_pkg_bytes)
    #     payload_bytes = recv_pkg_bytes
    #     acc_payload_bytes += payload_bytes
    #
    #     log.debug(f"<- async command response:")
    #     log.debug(f"   payload_bytes:         {self._get_hex_str(payload_bytes)}")
    #     log.debug(f"   acc_payload_bytes:     {self._get_hex_str(acc_payload_bytes)}")
    #     log.debug(f"   len acc response bytes: {len(acc_payload_bytes)}")
    #     log.debug(f"   len req response bytes: {required_byte_count}")
    #
    #     if len(acc_payload_bytes) == required_byte_count:
    #         recv_cmd_key, recv_payload_bytes = self._parse_async_response(acc_payload_bytes)
    #
    #         log.debug(f"<- async command response:")
    #         log.debug(f"   cmd_key:          {self._hex(cmd_key)}")
    #         log.debug(f"   recv_cmd_key:     {self._hex(recv_cmd_key)}")
    #         log.debug(f"   payload_bytes:      {self._get_hex_str(recv_payload_bytes)}")
    #
    #         assert(recv_cmd_key == cmd_key)
    #
    #         response_tup = self.unpack_payload_bytes(recv_payload_bytes, unpack_str)
    #

    def _handle_async_response(self, expected_cmd_key, recv_pkg_bytes):
        # If there's no existing buffer for capturing response, this must be the start
        # of a new response and it must have a valid header.
        if self._expected_payload_byte_count is None:
            (
                cmd_key,
                self._expected_payload_byte_count,
                self._acc_payload_bytes,
            ) = self._parse_initial_async_response(recv_pkg_bytes)
            assert cmd_key == expected_cmd_key
        # If there's an existing buffer for {cmd_key}, we assume that this is additional
        # bytes for an existing response. We can't safely check that it's not a new
        # header since the 3 fixed header bytes could occur in regular data.
        else:
            self._acc_payload_bytes.extend(recv_pkg_bytes)

        log.debug(
            f"Received {len(recv_pkg_bytes)} bytes. "
            f"Now have {len(self._acc_payload_bytes)} bytes. "
            f"Expecting {self._expected_payload_byte_count} bytes"
        )

        # If we have all the expected bytes, return them, which also signals completed
        # processing for the response for the given cmd_key.
        if len(self._acc_payload_bytes) == self._expected_payload_byte_count:
            acc_payload_bytes = self._acc_payload_bytes
            log.debug(
                f"Received all {self._expected_payload_byte_count} expected bytes. "
                f"Returning: {self._get_hex_str(acc_payload_bytes)}"
            )
            self._expected_payload_byte_count = None
            return acc_payload_bytes
        elif len(self._acc_payload_bytes) > self._expected_payload_byte_count:
            raise WatchError("Received more bytes than expected")
        # # If there's no existing buffer for capturing responses for {cmd_key}, this
        # # must be the start of a new response and it must have a valid header.
        # if cmd_key not in self._response_buf:
        #     payload_bytes = self._strip_header(recv_pkg_bytes)
        #     cmd_key, payload_bytes = self._parse_async_response(payload_bytes)
        #
        #     buf_dict = {
        #         'payload_byte_count': self._parse_header(recv_pkg_bytes),
        #         'acc_payload_bytes': self._strip_header(recv_pkg_bytes),
        #     }
        #     self._response_buf[cmd_key] = buf_dict
        # # If there's an existing buffer for {cmd_key}, we assume that this is additional
        # # bytes for an existing response. We can't safely check that it's not a new
        # # header since the 3 fixed header bytes could occur in regular data.
        # else:
        #     buf_dict = self._response_buf[cmd_key]
        #     buf_dict['acc_payload_bytes'].extend(recv_pkg_bytes)
        # # If we have all the expected bytes, return them, which also signals completed
        # # processing for the response for the given cmd_key.
        # if len(buf_dict['acc_payload_bytes']) == buf_dict['payload_byte_count']:
        #     return self._response_buf.pop(cmd_key)['acc_payload_bytes']

    # def _handle_notification(self, cmd_key, unpack_str, recv_charcs_handle, recv_pkg_bytes):
    #
    # def _handle_async_response(self, cmd_key, recv_pkg_bytes):
    #     recv_cmd_key, recv_payload_bytes = self._parse_async_response(recv_pkg_bytes)
    #
    #     if log.isEnabledFor(logging.DEBUG):
    #         log.debug(f"<- async command response:")
    #         log.debug(f"   cmd_key:          {self._hex(cmd_key)}")
    #         log.debug(f"   payload_bytes:      {self._get_hex_str(recv_payload_bytes)}")
    #
    #     # if recv_cmd_key != cmd_key:
    #     #     log.warning(
    #     #         f'Ignoring unexpected async command response. '
    #     #         f'cmd_key expected/received: {cmd_key}/{recv_cmd_key}'
    #     #     )
    #     #     return
    #
    #     response_tup = self.unpack_payload_bytes(recv_payload_bytes, unpack_str)
    #
    #     if len(response_tup) == 1:
    #         return response_tup[0]
    #
    #     return response_tup

    def unpack_payload_bytes(self, recv_payload_bytes, unpack_str):
        try:
            response_tup = struct.unpack(unpack_str, recv_payload_bytes)
        except struct.error as e:
            raise WatchError(
                f"Unable to unpack value bytes in payload. Error: {str(e)}, "
                f"payload_bytes={self._get_hex_str(recv_payload_bytes)}, "
                f"unpack_str={self._get_hex_str(recv_payload_bytes)}"
            )
        if len(response_tup) == 1:
            return response_tup[0]
        return response_tup

    # def _get_payload(self, pkg_bytes):
    #      return self._strip_header(pkg_bytes)

    def _parse_initial_async_response(self, pkg_bytes):
        """Parse the first package that is returned as an async command response. If
        payload_byte_count > len(payload_bytes), the remaining bytes are expected in
        additional responses. Those responses contain only payload bytes (no header and
        no cmd_key.)
        """
        payload_byte_count = self._check_and_parse_header(pkg_bytes)
        payload_bytes = pkg_bytes[4:]
        cmd_key = struct.unpack("B", payload_bytes[0:1])[0]
        return cmd_key, payload_byte_count - 1, payload_bytes[1:]

    def _check_and_parse_header(self, pkg_bytes):
        if pkg_bytes[:3] != self._get_bytes("fe ea 10"):
            raise WatchError(
                f"Expected bytes to start with new header (fe ea 10). Received: {self._get_hex_str(pkg_bytes)}"
            )
        payload_byte_count = struct.unpack("B", pkg_bytes[3:4])[0] - 4
        log.debug(f"Received valid header for {payload_byte_count} payload bytes")
        return payload_byte_count

    def _handle_accelerometer(self, recv_pkg_bytes):
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"<- accelerometer data:")
            log.debug(f"   pkg_bytes:      {self._get_hex_str(recv_pkg_bytes)}")

    def _handle_disconnect(self):
        log.info("Disconnected")
        self._is_connected = False

    def _write_to_characteristic(self, charcs_uuid, pkg_bytes):
        """Write bytes to a characteristic."""
        log.debug(f"-> {self._get_hex_str(pkg_bytes)}")
        result = self._device.char_write(charcs_uuid, pkg_bytes)
        if result is not None:
            log.debug(f"-> result: {result}")

    def _strip_header(self, b):
        """Strip the header from a packet.
        """
        # self._parse_header(b)
        log.info(f"HEADER: {self._get_hex_str(b[:4])}")
        return b[4:]

    def _hex(self, v):
        return f"0x{v:02x}"

    def _format_args(self, *arg_tup):
        return " ".join(shlex.quote(str(s)) for s in arg_tup)


def data_callback(queue, handle, value):
    """Called when a notification is received from one of the subscribed interfaces.

    handle -- integer, characteristic read handle the data was received on
    value -- bytearray, the data returned in the notification
    """
    # Values are logged when they are pulled from the queue.
    queue.put(("notification", handle, value))


def disconnect_callback(queue, event_dict):
    """Called when watch is disconnected."""
    # debug_pprint(event_dict)
    # Event is logged when pulled from the queue.
    queue.put(("disconnected",))


def debug_pprint(o):
    for line in pprint.pformat(o).splitlines():
        log.debug(line)


class WatchError(Exception):
    pass


class WatchBleScanError(WatchError):
    pass
