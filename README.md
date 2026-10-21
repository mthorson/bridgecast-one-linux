# BRIDGE CAST ONE for Linux

An unofficial Linux GUI for the Roland BRIDGE CAST ONE mixer. It shows live level meters and provides controls for the device settings currently supported by this project.

## Run

Connect the BRIDGE CAST ONE by USB with its hardware switch set to **PC**. Install Python 3, PyQt6, ALSA utilities (`amidi`), and `libasound`, then run:

```sh
python3 bridgecast_gui.py
```

The app finds the BRIDGE CAST ONE APP MIDI port automatically. It reads the current mixer state when it connects. Live meters poll every 40 ms.

## Current controls

- Separate Stream Mix and Personal Mix channel faders and mutes
- LINE OUT level, output enables, and LINE OUT source mode
- Mic input gain and selected mic processing controls
- A **Stop mic monitoring** action that turns the mic off in both device mixes while keeping USB mic capture available

Some displayed source assignments and controls are read-only until their device commands are verified. The app does not update firmware or reset the device. Enabling mic monitoring with speakers connected can cause feedback.

Run the protocol checks with `python3 -m unittest -q test_bridgecast_protocol.py`.

## Artwork

`assets/bridgecast-linux-icon.png` is the custom icon for this controller. The remaining graphics in `assets/` were extracted from the Roland software supplied with the device. BRIDGE CAST and Roland are trademarks of Roland Corporation. This project is not affiliated with Roland.
