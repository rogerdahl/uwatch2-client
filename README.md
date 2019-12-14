### Linux client for the UMIDIGI Uwatch2 smart watch (Python)

> **NOTE**: 
> 
> Alpha: Only a couple of commands implemented and tested. 
>
> For Linux only.

Based on [reverse engineering of the protocol by @kabbi](https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9).

#### Dependencies

```bash
$ pip install pygatt pexpect hjson blessed
```

#### Usage

The MAC address is required in order to connect to the device. Get the MAC address with a long tap (around 2 seconds) on the main watch face screen, and pass it when starting the script:

    $ ./uwatch.py --mac <your MAC address on form 11:22:33:44:55:66>

If the script is started without a MAC address, a BLE scan is performed to discover the MAC address. This is slow and may require sudo access.

    $ ./uwatch.py  

* If the watch name has been changed from the default of "Uwatch2", use `--name <my-name>` to specify the new name.

Use the `--debug` command line switch to get details on the protocol.

#### Examples

##### Interactive mode

Start the script without passing a command:

    $ ./uwatch2.py --debug --mac 11:22:33:44:55:66

To get a list of the commands:

    > list

- Only the commands marked with a star (`*`) are currently implemented.

To send a text message to the watch:

    > msg A Unicode test message;  ﯮ ﯯ ﯰ ¡ ¢ £ ¤ ¥ ¦ § ¨ © ª « ¬ ­ ®

To get the current number of steps for the daily goal:

    > 26

To set the number of steps for the daily goal to `12000`:

    > 16 12000

##### To issue a single command then exit, pass the command on the command line.

To set the number of steps for the daily goal to `12000`:

    $ ./uwatch.py 16 12000
    
#### Troubleshooting

- The client does not see the watch:

    - Make sure that the watch is removed from the "Da Fit" app or any other app or device it may be bonded to. The watch will not advertise itself as available unless unbonded.

        - In the "Da Fit" watch settings, tap `Remove` (under the battery display) if the watch is listed there. 

        - Using the Reset function on the watch itself will not unbond it.

    - Do not set the watch up as a new device in the Bluetooth settings in Linux.

- The client crashes:

    - Open the Bluetooth settings in Linux. If the watch is visible there, use "Remove device" to remove the device from the "known devices list."
     
     Apparently, what the Bluetooth stack stores about a device can get corrupted, breaking all further use of the device until the entry is cleared.

#### Protocol

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

