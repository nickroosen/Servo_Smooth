# Servo_Smooth

Controller for the [Animatronic Body Bag](https://www.thingiverse.com/thing:1114406):
two servos pull wire rope through a printed spine so a foam-filled bag
wriggles. A motion sensor wakes it up and it plays a sound effect.

| Folder | What it is |
| --- | --- |
| `circuitpython/` | **Current build.** Adafruit RP2040 Prop-Maker Feather, DS3240MG servos, PIR sensor, one speaker. |
| `servo_smooth/` | Arduino sketch for the old Uno + Motor Shield V2 + Audio FX build, updated for DS3240MG servos. |
| `original/` | The 2015 sketch, kept for reference. |

## Parts

- [Adafruit RP2040 Prop-Maker Feather](https://www.adafruit.com/product/5768). It replaces the Uno, Motor Shield and Audio FX board.
- 2 × DS3240MG servos, **270° version**
- PIR motion sensor (e.g. Adafruit #189 or an HC-SR501)
- One 4 Ω or 8 Ω speaker, up to 3 W
- 6 V UBEC or regulated supply, **8 A or more**, for the servos
- 1000 µF (10 V or more) electrolytic capacitor
- Power for the Feather: 5 V over USB-C, or a 3.7 V LiPo (see the notes on volume and the PIR below)

## Wiring

```
                 6 V / 8 A UBEC
                 +           -
                 |           |
     +-----------+-----+     |      (1000 uF cap across + and -, near the servos)
     |                 |     |
  Servo 1 V+      Servo 2 V+ |
  Servo 1 GND ----Servo 2 GND+----------------- Feather GND   <- common ground!
  Servo 1 SIG ------------------------------- Feather D9
  Servo 2 SIG ------------------------------- Feather D10

  PIR VCC --- terminal "5V"
  PIR GND --- terminal "G"
  PIR OUT --- terminal "Btn"

  Speaker + / - --- terminals "+" / "-"
```

- **Don't power the DS3240MGs from the Feather's servo header.** Its V+ comes
  from USB/LiPo through a small switch and can't supply 3–4 A per servo. Only
  the signal wires go to the Feather.
- **Don't connect a 2S LiPo (7.4–8.4 V) to the servos directly.** It's above
  their 6.8 V maximum, so use a 6 V UBEC. Use 18 AWG or heavier wire for servo power.
- The servo signals are 3.3 V. Most digital servos accept that. If they
  jitter, add a 74AHCT125 level shifter.
- **One speaker only.** The amp is mono and needs 4–8 Ω. Never wire two 4 Ω
  speakers in parallel (2 Ω).
- The terminal-block 5V output, the amp and the servo header only get power
  once the code sets `EXTERNAL_POWER` high, which `code.py` does at start-up.
  That 5V output comes from USB or the LiPo. On a LiPo it is only about 3.7 V,
  which is too low for an HC-SR501 (it needs 4.5 V or more), and the amp is
  quieter. Power the Feather from 5 V for best results.

### PIR settings

- Turn the **time** knob to minimum and set the jumper to **retrigger (H)**.
  The code decides how long the bag keeps going (`PIR_HOLD_S`).
- After power-up the PIR needs 30–60 s to settle. The code ignores it for
  `PIR_WARMUP_S`, and the Feather's red LED mirrors the PIR output so you can
  aim it.

### Mechanical notes

The DS3240MG is roughly 10× as strong as the S3004, so the spine and cables
take far more load:

- Crimp the ferrules properly, and print the pulleys and spine disks in PETG or
  with more walls/infill.
- Set the travel limits so the servo stops before the cable is fully taut.
  Otherwise the servo stalls against the rig, draws about 3–4 A and heats up.
- Make sure the servo mount is bolted down solidly.

## Setting up CircuitPython

1. Install CircuitPython for the "RP2040 Prop-Maker Feather" from
   [circuitpython.org/downloads](https://circuitpython.org/downloads).
2. Copy `circuitpython/code.py` to the `CIRCUITPY` drive.
3. Make a `sounds` folder on `CIRCUITPY` and copy your WAV files into it. No
   libraries are needed.

### Sound files

The WAVs must be **mono, 16-bit, 22050 Hz** (any other format is skipped,
with a message on the serial console). Each fit plays a random sound, never the same
one twice in a row. Keep them short (a few seconds), because the bag keeps
wriggling until the sound ends. In [Audacity](https://www.audacityteam.org/):
Tracks → Mix → Mix Stereo Down to Mono, set Project Rate to 22050, then
File → Export → WAV, Signed 16-bit PCM. Or with ffmpeg:

```
ffmpeg -i scream.mp3 -ac 1 -ar 22050 -sample_fmt s16 scream.wav
```

At this format each second of sound is about 44 KB, so the drive holds a
couple of minutes of audio in total.

## Behaviour

1. **Power-up**: the servos are enabled one at a time and centred, then switch
   off. The PIR is ignored for 45 s while it warms up.
2. **Motion** starts a **fit**: a random sound plays, and the servos thrash to
   new random positions every 50–500 ms for 2.5–7 s, or until the sound ends.
3. **Rest**: the spine eases back to straight and the servos switch off (no buzzing or
   heating). After a random 2–10 s, if there has been motion in the last 10 s,
   another fit starts. Otherwise it waits for the next motion.

Motion goes through a two-stage low-pass filter with a hard speed cap, so
changes of direction ease in and out instead of snapping.

## First power-up and tuning

All settings are at the top of `code.py`. Saving the file restarts it.

1. Set `PIR_WARMUP_S = 5` while testing, with the cables slack. Each servo
   goes to `rest_deg`. If the spine isn't straight there, adjust `rest_deg`.
2. Wave at the PIR. If a servo pulls the wrong way, flip `reversed`.
3. Widen `min_deg` / `max_deg` in steps of about 5°, and stop just before a cable goes fully taut.
4. Put `PIR_WARMUP_S` back to 45.

| Setting | What it does |
| --- | --- |
| `SERVOS` | Per servo: pin, min/max angle (degrees from centre), rest angle, reverse. The default is ±45°. |
| `SERVO_TRAVEL_DEG` | 270 for these servos (180 for the other DS3240MG version). |
| `FILTER` | Smoothing, from 0.01 (lazy) to 1.0 (none). |
| `MAX_SPEED_DEG_PER_S` | Top speed (default 180°/s; the servo can do about 350°/s). |
| `MIN_AMPLITUDE` | Minimum bend for each move (0–1). |
| `NEW_TARGET_*`, `FIT_*`, `REST_*` | Timing ranges in seconds. |
| `FIT_WAITS_FOR_SOUND` | Keep wriggling until the sound finishes. |
| `PIR_WARMUP_S`, `PIR_HOLD_S` | PIR settle time, and how long motion keeps the bag active. |
| `VOLUME` | 0.0–1.0. For more, solder the amp's 12 dB gain jumper on the back. |
| `DEBUG` | Prints state changes to the serial console. |

## Fixes compared with the 2015 sketch

- Smoothing filter applied once and then followed by a 2–10 s `delay()`, so the
  servos moved in big jumps → filter now runs every 20 ms without blocking.
- Sensor read only once, so the `do/while` either looped forever or ran once
  → it is now checked continuously.
- Smoothed position started at 0, slamming the servos at the first move → it starts at rest.
- Sound triggered on every pass with a 1 s blocking pulse → now one random sound per fit.
