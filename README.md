## Python library and client for the UMIDIGI Uwatch2 smart watch (Linux )

Based on [reverse engineering of the protocol by @kabbi](https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9).

### Dependencies

```bash
$ pip install pygatt pexpect pytz tzlocal
```

### Usage

#### Client

The MAC address is required in order to connect to the device. Get the MAC address with a long tap (around 2 seconds) on the main watch face screen, and pass it when starting the script. E.g.,

    $ ./uwatch2-client.py --mac 11:22:33:44:55:66

Or set it as an environment variable named `UWATCH2_MAC`.

    $ export UWATCH_MAC='11:22:33:44:55:66'
    $ ./uwatch2-client.py

To use the client interactively, run it without passing any commands on the command line:

    $ ./uwatch2-client.py
    INFO     Starting...
    INFO     Using MAC address from UWATCH2_MAC environment variable: FD:D1:C7:18:70:2D
    INFO     Connecting to MAC FD:D1:C7:18:70:2D...
    INFO     
    INFO     list, l: List commands
    INFO     help, h <command>: Show help for a command
    INFO     
    > set-watch-face-to-display 1
    INFO     ok
    > get-watch-face-to-display
    INFO     1

To use the client for running commands directly, e.g., from shell scripts, pass the
commands on the command line:

    ./uwatch2-client.py get-alarms find-device "set-steps-goal 9000" 

To get a list of all commands:

    ./uwatch2-client.py list
    
    
Use the `--debug` command line switch to get details on the protocol.

 
##### BLE scan

Automatically setting the MAC address by using a BLE scan is also supported. Since the MAC address for the watch is easily available by long tap on the main watch screen, this procedure is not typically necessary. It is also slow and unreliable.

By default, scanning with gatttool requires root. Enable regular users to perform BLE scans with:

    $ setcap 'cap_net_raw,cap_net_admin+eip' `which hcitool`
    
Alternatively, allow the script to attempt to escalate to root privileges by passing `--root` to the command or, when using the library, creating the `uwatch2lib.Uwatch2` instance with `scan_as_root=True`. Note however that if the scan does not fully complete for any reason, the Bluetooth adapter may be left in a bad state, requiring a reset with `hciconfig hci0 reset`.

If the watch name has been changed from the default of "Uwatch2", pass the new name of the watch with `--name <my-name>` to the command or, when using the library, creating the `uwatch2lib.Uwatch` instance with `scan_for_name` set to the name.
    
#### Library

See the source for the client, `uwatch2-client.py`.

### Supported commands

```none
find-device
get-alarms
get-breathing-light
get-dnd-period
get-heart-rate
get-metric-system
get-other-message
get-quick-view
get-quick-view-enabled-period
get-sedentary-reminder
get-sedentary-reminder-period
get-steps-goal
get-time-format
get-timing-measure-heart-rate
get-user-info
get-watch-face
send-message msg-str
set-breathing-light enable-bool
set-dnd-period from-hour-int from-min-int to-hour-int to-min-int
set-metric-system imperial-bool
set-other-message enable-bool
set-quick-view enabled-bool
set-quick-view-enabled-period from-hour-int from-min-int to-hour-int to-min-int
set-sedentary-reminder enable-bool
set-sedentary-reminder-period from-hour-int from-min-int to-hour-int to-min-int
set-step-length step-length-cm
set-steps-goal steps-int
set-time-format format-bool
set-timing-measure-heart-rate unknown
set-user-info height-cm weight-kg age-years gender-bool
set-watch-face watch-face-idx
shutdown
sync-time now-dt
unpack-payload-bytes recv-payload-bytes unpack-str
```
    
### Troubleshooting

- The client does not see the watch:

    - Make sure that the watch is removed from the "Da Fit" app or any other app or device it may be bonded to. The watch will not advertise itself as available unless unbonded.

        - In the "Da Fit" watch settings, tap `Remove` (under the battery display) if the watch is listed there. 

        - Using the Reset function on the watch itself will not unbond it.

    - Do not set the watch up as a new device in the Bluetooth settings in Linux.

- The client crashes:

    - Open the Bluetooth settings in Linux. If the watch is visible there, use "Remove device" to remove the device from the "known devices list."
     
     Apparently, what the Bluetooth stack stores about a device can get corrupted, breaking all further use of the device until the entry is cleared.

### Protocol

Some observations related to the Uwatch2 (you watch too?) BLE GATT protocol.

- Responses to the commands are returned asynchronously through notifications for which one must subscribe.

        <- (async) characteristic_uuid="0000fee3-0000-1000-8000-00805f9b34fb"
         handle="0x39" value="fe ea 10 09 26 40 1f 00 00"

    - The first byte after the header holds the key of the command for which the notification is a response.

- `set` commands take little-endian values while `get` commands return big-endian values.

- Accelerometer values?

    Notification received once per second when the watch is being moved.

        <- (async) characteristic_uuid="0000fcc1-0000-1000-8000-00805f9b34fb"
         handle="0x4d" value="94 03 bc ff 04 fe"
        

- Some other characteristics also return information:  

        <- (async) characteristic_uuid="0000fee1-0000-1000-8000-00805f9b34fb"
         handle="0x34" value="14 01 00 da 00 00 0f 00 00"

        <- (async) characteristic_uuid="0000fea1-0000-1000-8000-00805f9b34fb" 
         handle="0x47" value="07 14 01 00 da 00 00 0f 00 00"
