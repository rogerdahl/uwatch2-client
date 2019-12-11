### Python client for UMIDIGI Uwatch2 Smart Watch

> **For reference only, not usable at this time.**

> **For Linux only.**

Based on reverse engineering of the protocol by @kabbi
https://gist.github.com/kabbi/854a541c1a32e15fb0dfa3338f4ee4a9

#### Dependencies

```bash
$ pip install pygatt pexpect hjson
```

#### Setup

Change `UWATCH2_MAC` in the script to match the MAC address of your watch. Get the MAC address with long tap on the main watch face screen.

#### Examples

Use the `--debug` command line switch to get details on the protocol.

##### To use the interactive mode, start the script without command line arguments, then type at the prompt.

To get a list of the commands:

    > list

- Only a couple of them are currently implemented, marked by a star `*`.

To get the current number of steps for the daily goal:

    > 26

To set the number of steps for the daily goal to `12000`:

    > 16 12000

##### To issue a single command then exit, pass the command on the command line.

To set the number of steps for the daily goal to `12000`:

    > $ ./uwatch.py 16 12000
    
