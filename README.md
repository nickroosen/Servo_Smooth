# Servo_Smooth

Controller for the [Animatronic Body Bag](https://www.thingiverse.com/thing:1114406):
two servos pull wire rope through a printed spine so a foam-filled bag
wriggles, with an optional sound effect and trigger sensor.

- `servo_smooth/servo_smooth.ino` – the current sketch, revised for higher-torque servos.
- `original/servo_with_random_delay/` – the 2015 sketch, kept for reference.

## Hardware

- Arduino Uno with the Adafruit Motor Shield V2 (servo headers = D9, D10)
- 2 × DS3240MG servos (originally Futaba S3004)
- Adafruit Audio FX board, trigger input on D13 (pulled LOW to play) – optional
- Analog sensor on A2. The bag runs while the reading is between 200 and 400 – optional

No extra libraries are needed. The Metro library from the original is no longer used.

### Powering the DS3240MG servos

Specs for this servo family: 5–6.8 V, stall current of about 3.1 A at 5 V and
3.9 A at 6.8 V, and 500–2500 µs pulses for full travel.

The Motor Shield V2 servo headers take 5 V from the Arduino's regulator, which
can't supply these servos. When the regulator sags, the Uno resets or the
servos jitter. Instead:

1. Power the servos from their own **6 V supply rated for 8 A or more**: a
   regulated supply, or a 6 V UBEC from a battery. **Don't connect a 2S LiPo
   (7.4–8.4 V) directly.** It's above the 6.8 V maximum.
2. Connect only the servo **signal** wires to D9/D10. Connect the supply ground
   to the Arduino's GND (a common ground is required).
3. Put a large electrolytic capacitor (1000 µF or more, rated 10 V or more)
   across the servo supply close to the servos.
4. Use 18 AWG or heavier wire for the servo power. The thin servo leads are fine.

### Mechanical notes

The DS3240MG is roughly 10× as strong as the S3004, so the spine and cables
take far more load:

- Crimp the ferrules properly, and print the pulleys and spine disks in PETG or
  with more walls/infill.
- Set the travel limits so the servo stops before the cable is fully taut.
  Otherwise the servo stalls against the rig, draws about 3–4 A and heats up.
- Make sure the servo mount is bolted down solidly; the servo now has the
  torque to twist the mount loose.

## Behaviour

1. Power-up: the servos are attached one at a time and centred, then the sketch waits 5 s.
2. When the sensor is in its window, a **fit** starts. The sound plays and the
   servos thrash to new random positions every 50–500 ms for 2.5–7 s.
3. **Rest**: the spine eases back to straight and the servos detach (no buzzing
   or heating). After a random 2–10 s it checks the sensor and starts another fit.

Motion goes through a two-stage low-pass filter with a hard speed cap, so
changes of direction ease in and out instead of snapping.

## Tuning (top of the sketch)

| Setting | What it does |
| --- | --- |
| `SERVO_TRAVEL_DEG` | 180 or 270, matching the version on your servo's label (set to 270). |
| `SERVO_CFG` | Per servo: pin, min/max angle (degrees from centre), rest angle, reverse. The default is ±45°. Widen it a few degrees at a time while watching the spine. |
| `FILTER` | Smoothing, from 0.01 (lazy) to 1.0 (none). |
| `MAX_SPEED_DEG_PER_S` | Top speed (default 180°/s; the servo can do about 350°/s). Lower it if the rig shakes itself apart. |
| `MIN_AMPLITUDE` | Minimum bend for each move (0–1), so moves aren't tiny twitches. |
| `NEW_TARGET_*`, `FIT_*`, `REST_*` | Timing ranges in ms. |
| `USE_SENSOR`, `SENSOR_*` | Trigger window. Set `USE_SENSOR = false` to run continuously. |
| `SOUND_PIN` | Audio FX trigger pin. Set to `-1` to disable. |
| `DEBUG` | Prints state changes to Serial at 115200 baud. |

## Fixes compared with the original

- Smoothing filter applied once and then followed by a 2–10 s `delay()`, so the
  servos moved in big jumps → filter now runs every 20 ms without blocking.
- Sensor read only once, so the `do/while` either looped forever or ran once
  → it is now checked between every fit.
- Smoothed position started at 0, slamming the servos at the first move → it starts at rest.
- Sound triggered on every pass with a 1 s blocking pulse → now one 150 ms pulse per fit.
- `Serial.begin()` was never called; `loop_num` was unused; integer
  truncation stopped the filter short of its target → fixed or removed.
