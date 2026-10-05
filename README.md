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

### Electronics

| Part | Notes |
| --- | --- |
| [Adafruit RP2040 Prop-Maker Feather](https://www.adafruit.com/product/5768) | Replaces the Uno, Motor Shield and Audio FX board. |
| 2 × DS3240MG servos, **270° version** | |
| PIR motion sensor | Adafruit #189 or an HC-SR501. Needs 5 V. |
| 1 × speaker, 4 Ω or 8 Ω, up to 3 W | Mono amp, one speaker only. |
| 6 V UBEC, **8 A continuous** | e.g. the Henge/FEICHAO 8A UBEC: 7–25.5 V in, jumper set to **6.0 V**. |
| Power source | USB-C (option A) or a battery (option B), see [Power](#power). |
| 1000 µF electrolytic capacitor, 10 V or more | Across the UBEC output, near the servos. |
| 470 µF electrolytic capacitor, **35 V** or more | Across the UBEC input. Absorbs servo current spikes so the supply doesn't cut out. |
| Inline fuse holder + **5 A** fuse | On the positive wire into the UBEC. Cheap insurance inside a foam-filled bag. |
| Small terminal block, Wago lever nuts or a servo power board | To split the 6 V supply to both servos. |
| 2 × servo extension leads | If the servos sit further from the Feather than their leads reach. |
| 18 AWG wire (red/black) | For everything carrying servo current. |
| 74AHCT125 level shifter (optional) | Only if the servos jitter on the 3.3 V signals. Cheap enough to order now. |

### Tools

- Multimeter, to check every supply voltage **before** connecting the servos or the Feather.
- Soldering iron, for the capacitors, the trigger-board voltage jumper and the PIR header.

## Power

The servos and the Feather get **separate** supplies. Servo current spikes
would reset the Feather, and the UBEC's 6 V is too much for the Feather's
USB input. The grounds are joined.

### Option A: USB-C wall power (recommended for a fixed display)

```
65 W+ USB-C PD charger
        │  USB-C cable rated 60 W+ (100 W / 5 A preferred)
        ▼
USB-C PD trigger board, set to 20 V ──► 5 A fuse ──┬──► 6 V UBEC ──► servos
                                                   │   (470 µF on input,
                                                   │    1000 µF on output)
                                                   │
                                                   └──► 5 V buck ──► Feather USB pin + GND
```

- **Charger**: 65 W or more, with **20 V at 3.25 A or more** in its specs (most
  laptop chargers do). At full stall the two servos pull about 50 W.
  Most chargers only supply 3 A (36 W) at 12 V, which isn't enough, so use 20 V.
- **PD trigger board**: rated 3 A or more and set to **20 V**. Most use a solder
  jumper, a button or a fixed version. Check the output with a multimeter before
  connecting anything; it must stay under the UBEC's 25.5 V input limit.
- **Feather supply**: a small 5 V buck converter (1–2 A, input rated 24 V or more)
  from the same 20 V line, wired to the Feather's **USB** pin and **GND**. One
  charger and one cable power everything.
  - **Don't plug the Feather into a computer while the buck is connected.**
    The buck's 5 V would push back into the computer's USB port. Disconnect the
    buck's red wire to edit code. Alternatively, power the Feather over its own USB-C
    cable from a second charger port and skip the buck. Note that multi-port
    chargers usually split their power, so the PD port may no longer deliver
    65 W with both ports in use.
- A **USB-C power bank** with 20 V PD output (labelled 65 W or more) can replace
  the charger. Some power banks switch off when the draw is very low, and the
  Feather alone may not draw enough between fits to keep it on.

### Option B: battery

```
2S–6S LiPo ──► 5 A fuse ──┬──► 6 V UBEC ──► servos
                           └──► 5 V UBEC/buck ──► Feather USB pin + GND
```

Same rules as option A: 470 µF on the UBEC input, 1000 µF on its output, and
don't connect a computer while the 5 V converter is connected.

### Power checks before first connection

1. Measure the trigger board or battery output: 20 V, or the pack voltage.
2. Measure the UBEC output with nothing attached: **6.0 V** (not 7.4 V).
3. Measure the 5 V converter output: 4.9–5.2 V.
4. Only then connect the Feather, then the servos.

## Wiring

```
  6 V UBEC +  ──┬── Servo 1 V+
                └── Servo 2 V+          (1000 uF cap across UBEC + and -)
  6 V UBEC -  ──┬── Servo 1 GND
                ├── Servo 2 GND
                └── Feather GND         <- common ground!

  Servo 1 SIG ───── Feather D9
  Servo 2 SIG ───── Feather D10

  5 V converter + ── Feather USB pin
  5 V converter - ── Feather GND

  PIR VCC ── terminal "5V"
  PIR GND ── terminal "G"
  PIR OUT ── terminal "Btn"

  Speaker + / - ── terminals "+" / "-"
```

- **Don't power the DS3240MGs from the Feather's servo header.** Its V+ comes
  from the Feather's own supply through a small switch and can't supply 3–4 A
  per servo. Only the signal wires go to the Feather.
- **Never connect the servos to more than 6.8 V.** Check that the UBEC jumper is
  on 6.0 V, and never connect a 2S LiPo or the 20 V line to them directly.
- The servo signals are 3.3 V. Most digital servos accept that. If they
  jitter, add the 74AHCT125 level shifter (powered from 5 V).
- **One speaker only.** The amp is mono and needs 4–8 Ω. Never wire two 4 Ω
  speakers in parallel (2 Ω).
- The terminal-block 5V output, the amp and the servo header only get power
  once the code sets `EXTERNAL_POWER` high, which `code.py` does at start-up.
  That 5V output comes from the Feather's own 5 V (USB pin) supply, which is why
  the PIR and the amp work best with the Feather on 5 V rather than a LiPo.

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
