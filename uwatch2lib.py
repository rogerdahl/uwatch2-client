"""Read and write settings on a uwatch2 watch.

Based on: https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9
"""
import datetime
import logging
import pprint

import pytz
import tzlocal

import _uwatch2ble

log = logging.getLogger(__name__)


WatchError = _uwatch2ble.WatchError
WatchBleScanError = _uwatch2ble.WatchBleScanError

DAYS_TUP = "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"
# SUN, MON, TUE, WED, THU, FRI, SAT = range(7)


class Uwatch2(_uwatch2ble.Uwatch2Ble):
    def __init__(
        self,
        mac_addr=None,
        auto_reconnect=None,
        connect_timeout_sec=None,
        squelch_pygatt=True,
        scan_as_root=False,
        scan_for_name="Uwatch2",
    ):
        super().__init__(
            mac_addr,
            auto_reconnect,
            connect_timeout_sec,
            squelch_pygatt,
            scan_as_root,
            scan_for_name,
        )

    def send_message(self, msg_str):
        """Send notification message

        Causes the watch to vibrate immediately and queues the message for display on
        the watch.

        Args:
          msg_str (str): The notification to send. May contain Unicode characters.

        TODO: Have not found out how to display the message type, like "Twitter".
        """
        msg_bytes = msg_str.encode("utf-8")
        # Send message in 255 - packet_header(4) - string_header(2) = 249 byte chunks
        while True:
            msg1_bytes, msg2_bytes = self._split_utf8(msg_bytes, 255 - 4 - 2)
            msg1_str = msg1_bytes.decode("utf-8")
            log.info(f"Sending message: {msg1_str}")
            print(len(msg1_bytes), msg1_bytes)
            self._send_packet(bytes([0x41, len(msg1_bytes)]) + msg1_bytes)
            if msg2_bytes is None:
                break
            msg_bytes = msg2_bytes

    def _split_utf8(self, b, n):
        assert isinstance(b, bytes)
        if len(b) <= n:
            return b, None
        while 0x80 <= b[n] < 0xC0:
            n -= 1
        return b[:n], b[n:]

    def set_user_info(self, height_cm, weight_kg, age_years, gender_bool):
        """Set user info

        Set user height (cm), weight (kg), age (years), and gender (male or female).

        Args:
            height_cm (int): Height in cm.
            weight_kg (int): Weight in kg.
            age_years (int): Age in years.
            gender_bool (bool): Gender. False=Male, True=Female

        Returns: None
        """
        self._send_raw_cmd(0x12, "BBBB", height_cm, weight_kg, age_years, gender_bool)

    def get_user_info(self):
        """Get user info

        Get user height (cm), weight (kg), age (years), and gender (male or female).

        Returns:
            height_cm (int): Height in cm.
            weight_kg (int): Weight in kg.
            age_years (int): Age in years.
            gender_bool (bool): Gender. False=Male, True=Female
        """
        return self._get_raw_cmd(0x22, None, "BBBB")

    # Steps

    def set_steps_goal(self, steps_int):
        """Set daily goal for number of steps to walk

        Args:
            steps_int (int): Number of steps
        """
        self._send_raw_cmd(0x16, ">I", steps_int)

    def get_steps_goal(self):
        """Get daily goal for number of steps to walk

        Returns:
            int: Number of steps
        """
        return self._get_raw_cmd(0x26, None, "<I")

    def set_step_length(self, step_length_cm):
        """Set step length

        Args:
            step_length_cm (int): Length of one step in cm.
        """
        return self._send_raw_cmd(0x54, "B", step_length_cm)

    # Does not return anything.
    # def get_steps_category(self):
    #     """Get steps category
    #     """
    #     return self._get_raw_cmd(0x59, None, "B")

    # Quick View

    def set_quick_view(self, enabled_bool):
        """Enable or disable Quick View

        When enabled, the watch display turns on automatically when turning the watch
        towards you.

        Args:
            enabled_bool (bool):
                False or 0: Disable Quick View
                True or 1: Enable Quick View
        """
        return self._send_raw_cmd(0x18, "B", enabled_bool)

    def get_quick_view(self):
        """Get Quick View enabled/disabled

        Returns:
            False or 0: Quick View is disabled
            True or 1: Quick View is enabled
        """
        return bool(self._get_raw_cmd(0x28, None, "B"))

    def set_quick_view_enabled_period(
        self, from_hour_int, from_min_int, to_hour_int, to_min_int
    ):
        """Set Quick View enabled period

        Args:
            from_hour_int:
            from_min_int:
            to_hour_int:
            to_min_int:

            24 hour clock.
            0 0 0 0 = all the time
        """
        return self._send_raw_cmd(
            0x72, "BBBB", from_hour_int, from_min_int, to_hour_int, to_min_int,
        )

    def get_quick_view_enabled_period(self):
        """Get Quick View enabled period

        Returns:
            from_hour_int
            from_min_int
            to_hour_int
            to_min_int

            24 hour clock.
            0 0 0 0 = all the time
        """
        from_min, to_min = self._get_raw_cmd(0x82, None, "hh")
        return (*divmod(from_min, 60), *divmod(to_min, 60))

    # Language

    # def set_device_language(self, args="B"):
    #     """Set device language
    #     Args index?
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x1B, "B", "index?", None)
    #
    # def get_device_language(self, args=None):
    #     """Get device language
    #     Args None
    #     Returns 00 00 90 1f ff
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x2B, None, None, "BBBBB")

    # Device

    # def set_device_version(self, args="B"):
    #     """Set device version
    #     Args version
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x1E, "B", "version", None)
    #
    # def get_device_version(self, args=None):
    #     """Get device version
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x2E, None, None, "B")

    def shutdown(self):
        """Shutdown

        The watch turns turns off (kind off -- it stops responding). To turn it back on,
        tap and hold the watch face for 2-3 seconds.
        """
        return self._send_raw_cmd(0x51, "B", 255)

    def find_device(self):
        """Find device

        The watch vibrates for several seconds.
        """
        return self._send_raw_cmd(0x61, None)

    # Heart

    # Unknown.
    # 10, 11, 12 works.
    # 20, 30 does not work.
    def set_timing_measure_heart_rate(self, unknown):
        """Set timing measure heart rate

        Args:
            unknown
        """
        return self._send_raw_cmd(0x1F, "B", unknown)

    def get_timing_measure_heart_rate(self):
        """Get timing measure heart rate

        Returns:
             int
        """
        return self._get_raw_cmd(0x2F, None, "B")

    def get_heart_rate(self):
        """Get heart rates in beats per minute (BPM)

        Returns:
            2-tup of tuples
            tuple 0: 2-tup of values that may be the highest and lowest heart rates
            tuple 1: 10-tup of heart rates

        """
        raw_heart_rate_list = self._get_raw_cmd(0x35, None, "73B")
        return self._parse_heart_rate(raw_heart_rate_list)

    def _parse_heart_rate(self, raw_heart_rate_list):
        """Parse the raw data returned from the get_heart_rate() command.

        The raw data returned are on forms such as these:

            0, 0, 0, 0, X,
            0, 0, 0, 0, 0, Y,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, R,
            0

        or

            0, 0, 0, 0, X,
            0, 0, 0, 0, 0, Y,
            0, 0, 0, 0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, R,
            0, 0, 0, 0, 0

        Where X and Y look like highest and lowest heart rates and R look like regular
        measurements.

        Returns:
            2-tup of tuples
            tuple 0: 2-tup of values that may be the highest and lowest heart rates
            tuple 1: Rest of non-zero values in the returned block
        """
        t = raw_heart_rate_list
        return (
            (t[4], t[10]),
            # (t[19::6]),
            tuple(v for v in t if v),
        )

    # def get_heart_rate(self, args="B"):
    #     """Get heart rate
    #     Args byte
    #     Returns Returns nothing with or without sending a byte arg
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x36, "B", "byte", None)
    #
    # def get_movement_heart_rate(self, args=None):
    #     """Get movement heart rate
    #     Args ?
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x37, None, "?", "60 bytes")
    #
    # def ecg_heart_rate_command(self, args=None):
    #     """ECG heart rate command
    #     Args cmd
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x6F, None, "cmd", None)
    #

    # Alarms

    def get_alarms(self):
        """Get alarms

        The watch supports 3 individually configurable alarms. This returns the state
        of the alarms as strings for display.

        Returns:
             tup: A tuple of 3 strings. Each string describes one alarm.

        See Also:
            get_alarm_dicts()
        """
        alarm_tup = self.get_alarm_tup()
        # self._dump_alarm_tup(alarm_tup)
        return tuple(self._format_alarm(d) for d in alarm_tup)

    def set_alarm(
        self,
        alarm_idx,
        enabled_bool=None,
        hour_int=None,
        min_int=None,
        *repeat_days_tup,
    ):
        """Set an alarm

        This updates the alarm with any of the provided values that are not None, then
        activates the alarm, so that it will fire at least once.

        Args:
            alarm_idx (int): alarm index (0, 1 or 2)
            enabled_bool (bool or int 0/1): Only enabled alarms will fire. An alarm
              that is set to fire once (repeat_days_tup is empty), will set enabled_bool
              to False after the alarm has fired.
            hour_int (int): Hour for alarm (0-23, 24-hour clock)
            min_int (int): Minute for alarm (0-59)
            repeat_days_tup (list of str): List of abbreviated days in which the alarm
              will repeat. If no days are provided, the alarm is set to trigger only one
              time.

        Examples:
            Set alarm 3 to activate at 9:30 (in the morning, always within 24 hours), and not repeat:
                set-alarm 3 1 9 30

            Set alarm 1 to activate at 22:45 on Tuesdays and Wednesdays until it's disabled:
                set-alarm 1 22 45 tue wed
        """
        alarm_tup = self.get_alarm_tup()
        alarm_dict = alarm_tup[alarm_idx]
        alarm_dict["alarm_idx"] = alarm_idx

        for s in ("enabled_bool", "hour_int", "min_int", "repeat_days_tup"):
            v = locals()[s]
            if v is not None:
                alarm_dict[s] = v
        alarm_dict["_unknown1_int"] = 0
        if not repeat_days_tup:
            # If the alarm is set not to repeat, the app sets the following values, which
            # appear to be necessary in order for the alarm to fire once.
            alarm_dict["_unknown1_int"] = 0x00
            alarm_dict["_unknown2_int"] = 0x52
            alarm_dict["_unknown3_int"] = 0x0B
        else:
            # If the alarm is set to repeat, the app sets the following values.
            alarm_dict["_unknown1_int"] = 0x02
            alarm_dict["_unknown2_int"] = 0x00
            alarm_dict["_unknown3_int"] = 0x00
        # self._dump_alarm_tup(alarm_tup)
        self.set_alarm_dict(alarm_tup[alarm_idx])
        self.get_alarm_tup()

    def _dump_alarm_tup(self, alarm_tup):
        log.debug("-" * 100)
        log.debug("alarm_tup:")
        for alarm_dict in alarm_tup:
            alarm_str = pprint.pformat(alarm_dict)
            for line in alarm_str.splitlines():
                log.debug(f"  {line}")
        log.debug("-" * 100)

    def get_alarm_tup(self):
        """Get all alarms

        The watch supports 3 individually configurable alarms. This returns the state
        of all the alarms.

        Returns:
             alarm_tup: A tuple of 3 dicts. Each dicts describes one alarm. The
                 dict_keys are alarm_idx, enabled, hour_int, min_int,
                 repeat_days_tup

        See Also:
            set_alarm_tup()

        Bytes:
            0: Alarm index
            1: Enabled (True/False, 0/1)
            2: ?
            3: Hour
            4: Minute
            5: ? (apparently not seconds)
            6: ?
            7: Repeat enabled/disabled for each day of the week
        """

        def d_(a):
            return {
                "alarm_idx": a[0],
                "enabled_bool": bool(a[1]),
                "_unknown1_int": a[2],
                "hour_int": a[3],
                "min_int": a[4],
                "_unknown2_int": a[5],
                "_unknown3_int": a[6],
                "repeat_days_tup": self._parse_alarm_repeat_days(a[7]),
            }

        alarm_bytes = self._get_raw_cmd(0x21, None, "24B")
        self._dump_alarm_bytes("RECV", alarm_bytes)
        return tuple(d_(alarm_bytes[i * 8 : (i + 1) * 8]) for i in range(3))

    def set_alarm_dict(self, alarm_dict):
        """Set one alarm

        The watch supports 3 individually configurable alarms. This overwrites the
        alarm designated by alarm_idx in {alarm_dict}.

        To modify only some of the values in the alarm, e.g., to only toggle the alarm
        from disabled to enabled, read out all
        the alarms with get_alarm_tup(), modify the values in the alarm_dict for the
        desired alarm, then write it back by passing it to this method.

        Args:
             alarm_dict: Dict describing an alarm. dict_keys are alarm_idx, enabled,
               hour_int, min_int, repeat_days_tup

        See Also:
            get_alarm_tup()
        """
        d = alarm_dict
        alarm_bytes = [
            d["alarm_idx"],
            d["enabled_bool"],
            d["_unknown1_int"],
            d["hour_int"],
            d["min_int"],
            d["_unknown2_int"],
            d["_unknown3_int"],
            self._make_alarm_repeat_days_int(d["repeat_days_tup"]),
        ]
        self._assert_alarm_dict(alarm_dict)
        self._dump_alarm_bytes("SEND", alarm_bytes)
        return self._send_raw_cmd(0x11, "8B", *alarm_bytes)

    def _assert_alarm_dict(self, alarm_dict):
        d = alarm_dict
        if d["alarm_idx"] not in (0, 1, 2):
            raise _uwatch2ble.WatchError(
                f"alarm_idx must be 0, 1 or 2, not {d['alarm_idx']}"
            )
        if not 0 <= d["hour_int"] < 24:
            raise _uwatch2ble.WatchError(
                f"hour_int must be 0 - 23, not not {d['hour_int']}"
            )
        if not 0 <= d["min_int"] < 60:
            raise _uwatch2ble.WatchError(
                f"min_int must be 0 - 59, not not {d['min_int']}"
            )

    def _dump_alarm_bytes(self, msg, alarm_list):
        def f(alarm_idx):
            i = alarm_idx * 8
            return " ".join(f"{v: 3d}" for v in alarm_list[i : i + 8])

        log.error(f"{msg}: {f(0)}  {f(1)}  {f(2)}")

    def _format_alarm(self, alarm_dict):
        """Format alarm for display

        Args:
            alarm_dict (dict): Desc

        Returns:
            Tup of 3 strings.
        """
        d = alarm_dict
        if d["repeat_days_tup"]:
            day_str = f'Repeats: {" ".join(d["repeat_days_tup"])}'
        else:
            day_str = "Once"
        return (
            f'Alarm {d["alarm_idx"]}: {d["hour_int"]:02d}:{d["min_int"]:02d} '
            f'{"ON " if d["enabled_bool"] else "OFF"} '
            f"{day_str}"
        )

    def _parse_alarm_repeat_days(self, repeat_days_int):
        """Parse the byte that holds the days in which an alarm should repeat

        Returns:
            tup of str: An ordered tuple of abbreviated day names for which the alarm is
            set to repeat.
        """
        return tuple(
            DAYS_TUP[day_idx] for day_idx in range(7) if repeat_days_int >> day_idx & 1
        )

    def _make_alarm_repeat_days_int(self, repeat_days_tup):
        """Format a list of abbreviated day names to the byte that holds the days
        in which an alarm should repeat.

        Returns:
            int: Value between 0 and 127 with bits set for the repeat days.
        """
        repeat_days_int = 0
        days_lower_tup = tuple(s.lower() for s in DAYS_TUP)
        for day_str in repeat_days_tup:
            try:
                day_idx = days_lower_tup.index(day_str.lower())
            except ValueError:
                raise _uwatch2ble.WatchError(
                    f'Invalid abbreviated day "{day_str}". Must be one of: {", ".join(DAYS_TUP)} (case insensitive)'
                )
            repeat_days_int |= 1 << day_idx
        return repeat_days_int

    # Time format

    def set_time_format(self, format_bool):
        """Set time format

        Args:
            format_bool (bool):
                False or 0: 12 hour AM/PM
                True or 1: 24 hour
        """
        return self._send_raw_cmd(0x17, "B", format_bool)

    def get_time_format(self):
        """Get time format

        Returns:
            bool:
                False or 0: 12 hour AM/PM
                True or 1: 24 hour
        """
        return self._get_raw_cmd(0x27, None, "B")

    # Metric

    def set_metric_system(self, imperial_bool):
        """Set metric system

        Args:
            imperial_bool (bool):
                False or 0: metric / km
                True or 1: imperial / miles
        """
        return self._send_raw_cmd(0x1A, "B", imperial_bool)

    def get_metric_system(self):
        """Get metric system

        Returns bool:
            False or 0: metric / km
            True or 1: imperial / miles
        """
        return self._get_raw_cmd(0x2A, None, "B")

    def sync_time(self, now_dt=None):
        """Set the time.

        Args:
            now_dt (datetime): Timezone aware datetime.datetime object (tz argument
            specified). If not provided, the current date and time at UTC is used.
        """
        if now_dt is None:
            now_dt = datetime.datetime.now(tz=tzlocal.get_localzone())

        tz_hours, tz_remainder = divmod(now_dt.utcoffset().total_seconds(), (60 * 60))
        if tz_remainder:
            raise _uwatch2ble.WatchError(
                "Only full hour timezones are supported by the Uwatch2"
            )

        return self._send_raw_cmd(
            0x31, ">Ib", datetime.datetime.timestamp(now_dt), tz_hours
        )

    # Sleep tracking

    # def sync_sleep(self, args=None):
    #     """Sync sleep
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x32, None, None, None)
    #
    # def sync_past_sleep(self, args="B"):
    #     """Sync past sleep
    #     Args byte
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x33, "B", "byte", None)
    #
    # def get_last_dynamic_rate(self, args=None):
    #     """Get last dynamic rate
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x34, None, None, "B")
    #
    # def get_sleep_action(self, args=None):
    #     """Get sleep action
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x3A, None, None, "B")

    # Message

    def set_other_message(self, enable_bool):
        """Set other message

        Setting is retained by I have no idea what it does.

        Args:
            enable_bool (bool): 0 (off), 1 (on) ?
        """
        return self._send_raw_cmd(0x1C, "B", enable_bool)

    def get_other_message(self):
        """Get other message

        Setting is retained by I have no idea what it does.

        Returns:
            bool: 0 (off), 1 (on) ?
        """
        return self._get_raw_cmd(0x2C, None, "B")

    # Weather

    # def set_future_weather(self, args=None):
    #     """Set future weather
    #     Args 21 bytes from C2439F
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x42, None, "21 bytes from C2439F", None)
    #
    # def set_today_weather(self, args=None):
    #     """Set today weather
    #     Args variable length from C2439F
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x43, None, "variable length from C2439F", None)
    #
    # def set_calibrate_gsensor(self, args=None):
    #     """Set calibrate gsensor
    #     Args
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x52, None, "", None)
    #
    # def abort_firmware_upgrade(self, args="BBBB"):
    #     """Abort firmware upgrade
    #     Args 255 255 255 255
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x63, "BBBB", "255 255 255 255", None)
    #
    # def switch_camera_view(self, args=None):
    #     """Switch camera view
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x66, None, None, None)
    #
    # def unknown(self, args=None):
    #     """Unknown
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x68, None, None, None)
    #
    # def ui_file_transfer(self, args=None):
    #     """UI file transfer
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x6C, None, None, None)
    #
    # def unknown(self, args=None):
    #     """Unknown
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x6D, None, None, None)
    #

    # Watch face

    def set_watch_face(self, watch_face_idx):
        """Set watch face to display
        Args:
             watch_face_idx (int): 0, 1 or 2
        """
        return self._send_raw_cmd(0x19, "B", watch_face_idx + 1)

    def get_watch_face(self):
        """Get watch face to display
        Returns:
             int: 0, 1 or 2
        """
        return self._get_raw_cmd(0x29, None, "B") - 1

    # def set_watch_face_layout(self, args=None):
    #     """Set watch face layout
    #     Args 37 bytes from C2438E
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x38, None, "37 bytes from C2438E", None)
    #
    # def get_watch_face_layout(self, args=None):
    #     """Get watch face layout
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x39, None, None, None)
    #
    # def start_watch_face_upload(self, args=None):
    #     """Start watch face upload
    #     Args uint32
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x6E, None, "uint32", None)
    #
    # def start_watch_face_file_transfer(self, args=None):
    #     """Start watch face file transfer
    #     Args uint32 size
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x74, None, "uint32 size", None)
    #
    # def get_supported_watch_face(self, args=None):
    #     """Get supported watch face
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x84, None, None, "B")
    #

    # Breathing light

    # This is what I've found about origin of the term, "breathing light." I've now seen
    # it used to mean any generic notification LED on products that don't have a screen.

    # "Instead of incorporating a notification light, Xiaomi has come up with a
    # thoughtful method to alert the user about notifications on the Mi CC9 Pro. The
    # side of the upcoming smartphone’s AMOLED display will flicker when the device
    # receives a phone call, message or any other type of notification. This is the
    # feature that Xiaomi is referring to as “breathing light” display."

    def set_breathing_light(self, enable_bool):
        """Set breathing light
        Args:
            enable_bool (bool):
        """
        return self._send_raw_cmd(0x78, "B", enable_bool)

    def get_breathing_light(self):
        """Get breathing light
        Returns:
            bool
        """
        return self._get_raw_cmd(0x88, None, "B")

    # Do not disturb

    def set_dnd_period(self, from_hour_int, from_min_int, to_hour_int, to_min_int):
        """Set Do Not Disturb period

        Args:
            from_hour_int:
            from_min_int:
            to_hour_int:
            to_min_int:

            24 hour clock.
            0 0 0 0 = all the time
        """
        return self._send_raw_cmd(
            0x71, "BBBB", from_hour_int, from_min_int, to_hour_int, to_min_int,
        )

    def get_dnd_period(self):
        """Get Do Not Disturb period

        Returns:
            from_hour_int
            from_min_int
            to_hour_int
            to_min_int

            24 hour clock.
            0 0 0 0 = all the time
        """
        from_min, to_min = self._get_raw_cmd(0x81, None, "hh")
        return (*divmod(from_min, 60), *divmod(to_min, 60))

    # Sedentary reminder

    def set_sedentary_reminder(self, enable_bool):
        """Enable sedentary reminder
        Args:
            enable_bool (bool)
        """
        return self._send_raw_cmd(0x1D, "B", enable_bool)

    def get_sedentary_reminder(self):
        """Get sedentary reminder status
        Returns:
            bool
        """
        return self._get_raw_cmd(0x2D, None, "B")

    def set_sedentary_reminder_period(
        self, from_hour_int, from_min_int, to_hour_int, to_min_int
    ):
        """Set sedentary reminder period

        Args:
            from_hour_int:
            from_min_int:
            to_hour_int:
            to_min_int:

            24 hour clock.
            0 0 0 0 = all the time
        """
        return self._send_raw_cmd(
            0x71, "BBBB", from_hour_int, from_min_int, to_hour_int, to_min_int,
        )

    def get_sedentary_reminder_period(self):
        """Get Do Not Disturb period

        Returns:
            from_hour_int
            from_min_int
            to_hour_int
            to_min_int

            24 hour clock.
            0 0 0 0 = all the time
        """
        from_min, to_min = self._get_raw_cmd(0x81, None, "hh")
        return (*divmod(from_min, 60), *divmod(to_min, 60))

    #
    # Unsupported?
    #

    # Blood pressure / oxygen

    # def stop_measure_blood_pressure(self, args=None):
    #     """Stop measure blood pressure
    #     Args 0xff, 0xff, 0xff
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x69, None, "0xff, 0xff, 0xff", None)
    #
    # def stop_measure_blood_oxygen(self, args=None):
    #     """Stop measure blood oxygen
    #     Args 0xff
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x6B, None, "0xff", None)
    #

    # Hand

    # def set_dominant_hand(self, args=None):
    #     """Set dominant hand
    #     Args hand
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x14, None, "hand", None)
    #
    # def get_dominant_hand(self, args=None):
    #     """Get dominant hand
    #     Args None
    #     Returns 0 (off), 1 (on)  ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x24, None, None, "B")
    #
    # def set_display_device_function(self, args=None):
    #     """Set display device function
    #     Args null terminated list of bytes
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x15, None, "null terminated list of bytes", None)
    #
    # def set_display_device_function_support(self, args="B"):
    #     """Set display device function support
    #     Args 255
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x25, "B", "255", "BBBBBBBBBBB")
    #

    # Physiological? Maybe exercise period?
    # 85 does not return anything. Unsupported?

    # def set_physiological_period_reminder(self, args="BBBBBBBBBBBBBB"):
    #     """Set physiological period reminder
    #     Args 14 bytes
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x75, "BBBBBBBBBBBBBB", "14 bytes", None)
    #
    # def get_physiological_period(self, args=None):
    #     """Get physiological period
    #     Args None
    #     Returns ?
    #     tested_and_working: False
    # """
    #     return self._send_raw_cmd(0x85, None, None, "BBBB")
