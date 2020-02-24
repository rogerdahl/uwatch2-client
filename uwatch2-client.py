#!/usr/bin/env python

"""Read and write settings on a uwatch2 watch.
"""
import argparse
import inspect
import logging
import re
import sys

import uwatch2lib

SUN, MON, TUE, WED, THU, FRI, SAT = range(7)
DAYS_TUP = "SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"


log = logging.getLogger(__name__)
log.setLevel(0)

# Commands that do not work or are not relevant in an interactive client.
SKIP_COMMAND_LIST = [
    "get_alarm_tup",
    "set_alarm_tup",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Debug level logging")
    ex_group = parser.add_mutually_exclusive_group()
    ex_group.add_argument(
        "--mac", metavar="11:22:33:44:55:66", help="Connect by MAC address"
    )
    ex_group.add_argument("--name", dest="watch_name", help="Connect by watch name")
    parser.add_argument(
        "command_list",
        metavar="command",
        nargs="*",
        help="Run one or more commands without entering command_interface mode",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    ret = 0

    try:
        with uwatch2lib.Uwatch2(
            mac_addr=args.mac, scan_for_name=args.watch_name
        ) as uwatch2:
            command_interface = CommandInterface(uwatch2, args.debug)
            if args.command_list:
                command_interface.run_commands(args.command_list)
            else:
                command_interface.run_interactive()
    except Exception as e:
        if args.debug:
            log.exception("")
        else:
            log.error(e)
        ret = 1
    except KeyboardInterrupt:
        pass
    return ret


class CommandInterface(object):
    def __init__(self, uwatch2, debug=False):
        self._debug = debug
        self._uwatch2 = uwatch2

    def run_interactive(self):
        log.info("")
        log.info("list, l            List commands")
        log.info("help, h <command>  Show help for a command")
        log.info("exit, ctrl-c       Exit")
        log.info("")

        while True:
            try:
                cmd_str = input("> ")
                if cmd_str.strip() == "exit":
                    break
                self._dispatch_cmd(cmd_str)
            except uwatch2lib.WatchError as e:
                if self._debug:
                    raise
                log.error(e)

    def run_commands(self, command_list):
        for cmd_str in command_list:
            try:
                self._dispatch_cmd(cmd_str)
            except uwatch2lib.WatchError as e:
                log.error(e)

    def _dispatch_cmd(self, cmd_str):
        """Split command into command and arguments, then call the appropriate
        command method.
        """
        cmd_key, *arg_tup = re.split(r"\s+", cmd_str)
        if cmd_key == "exit":
            return
        elif cmd_key in ("list", "l"):
            self.list_commands()
        elif cmd_key == "help":
            self.display_help(arg_tup[0])
        else:
            self.call_command(cmd_key, *arg_tup)

    def list_commands(self):
        """List all commands"""
        for member_name, member_obj in inspect.getmembers(uwatch2lib.Uwatch2):
            if not re.match(r"[a-z]", member_name):
                continue
            if not inspect.isfunction(member_obj):
                continue
            if member_name in SKIP_COMMAND_LIST:
                continue
            arg_list = inspect.getfullargspec(member_obj).args
            command_str = " ".join(
                v.replace("_", "-") for v in (member_name, *arg_list[1:])
            )
            log.info(f"{command_str}")

    def display_help(self, command_name):
        """Display help for a command."""
        for member_name, member_obj in inspect.getmembers(uwatch2lib.Uwatch2):
            if member_name == command_name.replace("-", "_"):
                log.info(inspect.getdoc(member_obj))

    def call_command(self, command_name, *arg_tup):
        command_name = command_name.replace("-", "_")
        arg_tup = tuple(int(v) if v.isdecimal() else v for v in arg_tup)
        for member_name, member_obj in inspect.getmembers(uwatch2lib.Uwatch2):
            if member_name == command_name:
                try:
                    res = member_obj(self._uwatch2, *arg_tup)
                except Exception as e:
                    if self._debug:
                        raise
                    raise uwatch2lib.WatchError(f"Command failed: {e}")

                if member_name == "get_alarms":
                    self.format_get_alarms(res)
                else:
                    self.format_general(res)

                break
        else:
            raise uwatch2lib.WatchError(
                f'Unknown command: {command_name.replace("_", "-")}'
            )

    def format_get_alarms(self, alarm_tup):
        alarm_tup = self._uwatch2.get_alarms()
        for alarm_str in alarm_tup:
            log.info(alarm_str)

    def format_general(self, res):
        if res is None:
            log.info("ok")
        elif isinstance(res, (list, tuple)):
            log.info(" ".join(map(str, res)))
        else:
            log.info(res)


if __name__ == "__main__":
    sys.exit(main())
