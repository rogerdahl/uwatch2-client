"""Read and write settings on a uwatch2 watch.

Based on: https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9
"""
import datetime
import logging

import pytz
import tzlocal

import _uwatch2ble

log = logging.getLogger(__name__)


WatchError = _uwatch2ble.WatchError
WatchBleScanError = _uwatch2ble.WatchBleScanError


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
        log.info(f"Sending message: {msg_str}")
        self._send_packet(bytes([0x41, len(msg_bytes)]) + msg_bytes)

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
        alarm_tup = self.get_alarms_as_dicts()
        return self._format_alarms(alarm_tup)

    def get_alarms_as_dicts(self):
        """Get alarms as dict

        The watch supports 3 individually configurable alarms. This returns the state
        of the alarms as dict for further processing.

        Returns:
             tup: A tuple of 3 dicts. Each dicts describes one alarm.
             dict keys: enabled, hour, min, sec, days

        See Also:
            get_alarms()
        """
        alarm_bytes = self._get_raw_cmd(0x21, None, "24B")
        return tuple(
            self._parse_alarm(alarm_bytes[i * 8 : (i + 1) * 8]) for i in range(3)
        )

    def _parse_alarm(self, alarm_bytes):
        """Alarm bytes:

        0: Alarm index
        1: Enabled/disabled (0/1)
        2: ?
        3: Hour
        4: Minute
        5: Probably second, but can't be set in app. Would it be honored by the watch?
        6: ?
        7: Enabled/disabled for each day of the week

        Example alarm 0: 00 00 02 09 01 00 00 71

        Args:
            alarm_bytes (8 bytes)

        Returns: dict
        """
        return {
            "alarm_idx": alarm_bytes[0],
            "enabled": bool(alarm_bytes[1]),
            "hour": alarm_bytes[3],
            "min": alarm_bytes[4],
            "sec": alarm_bytes[5],
            "days": self._parse_alarm_days(alarm_bytes[7]),
        }

    def _format_alarms(self, alarm_tup):
        """Format alarms for display.

        Args:
            alarm_tup (tup):
                Tup returned by get_alarms().

        Returns:
            Tup of 3 strings.
        """

        def f_(d):
            en_str = "ON " if d["enabled"] else "OFF"
            if d["days"]:
                day_str = f'Repeats: {" ".join(d["days"])}'
            else:
                day_str = "Once"
            return f'Alarm {d["alarm_idx"]}: {d["hour"]:02d}:{d["min"]:02d}:{d["sec"]:02d} {en_str} {day_str}'

        return tuple(f_(d) for d in alarm_tup)

    def _parse_alarm_days(self, days_int):
        # SUN, MON, TUE, WED, THU, FRI, SAT = range(7)
        DAYS_TUP = "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"
        return tuple(
            DAYS_TUP[day_idx] for day_idx in range(7) if days_int >> day_idx & 1
        )

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
