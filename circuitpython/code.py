# Servo_Smooth - animatronic body bag for the Adafruit RP2040 Prop-Maker Feather
#
# Two DS3240MG servos pull the spine cables, an ultrasonic distance sensor
# (JSN-SR04T) or a PIR wakes the bag up, and a random WAV from /sounds plays
# through the on-board I2S amp each time it starts wriggling.
#
# Copy this file and a "sounds" folder of WAVs to the CIRCUITPY drive.
# No libraries from the bundle are needed.
#
# Wiring (see README.md):
#   Servo signals  -> D9, D10   (servo power from a separate 6 V UBEC!)
#   JSN-SR04T      -> Trig to D5, Echo to D6 through a 1k/2k divider,
#                     power from "5V" and "G" terminals
#   or PIR output  -> "Btn" screw terminal, PIR power from "5V" and "G"
#   Speaker        -> "+" and "-" screw terminals (one 4-8 ohm speaker)

import os
import random
import time

import audiobusio
import audiocore
import audiomixer
import board
import digitalio
import microcontroller
import neopixel_write
import pwmio

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Servo type. The DS3240MG maps 500..2500 us onto its full travel, which is
# 270 degrees on the version used here (180 on the other version).
SERVO_TRAVEL_DEG = 270
PULSE_MIN_US = 500
PULSE_MAX_US = 2500

# Angles are degrees from the servo's centre. The DS3240MG has roughly 10x
# the torque of the original S3004s - enough to snap the wire rope or crack
# a spine disk - so start narrow and widen a few degrees at a time while
# watching the spine.
SERVOS = (
    # pin,      min_deg, max_deg, rest_deg, reversed
    (board.D9,  -45,     45,      0,        False),
    (board.D10, -45,     45,      0,        False),
)

# Motion feel
FILTER = 0.10              # 0.01 (lazy) .. 1.0 (no smoothing)
MAX_SPEED_DEG_PER_S = 180  # hard speed cap; the servo can do ~350
MIN_AMPLITUDE = 0.35       # each new target is at least this far from rest (0..1)
UPDATE_S = 0.02            # servo update period (50 Hz)

# Timing (seconds)
NEW_TARGET_MIN_S = 0.05    # how often a new random target is chosen
NEW_TARGET_MAX_S = 0.5
FIT_MIN_S = 2.5            # length of one wriggling fit
FIT_MAX_S = 7.0
FIT_WAITS_FOR_SOUND = True # keep wriggling until the sound finishes
REST_MIN_S = 2.0           # pause between fits
REST_MAX_S = 10.0
DETACH_AFTER_S = 1.5       # stop driving the servos once settled at rest

# Which sensor wakes the bag up: "sonar" (JSN-SR04T ultrasonic) or "pir".
SENSOR = "sonar"
MOTION_HOLD_S = 10         # keep going for this long after the last detection
COOLDOWN_S = 30            # after the bag settles, ignore the sensor this long

# JSN-SR04T ultrasonic sensor. It triggers when something is closer than
# SONAR_TRIGGER_CM for SONAR_READINGS_NEEDED readings in a row. Aim it across
# the path, with nothing else (including the bag) inside that distance.
SONAR_TRIG_PIN = board.D5
SONAR_ECHO_PIN = board.D6  # through a 1k/2k divider - Echo is 5 V!
SONAR_TRIGGER_CM = 150     # anything closer than this counts as a person
SONAR_MIN_CM = 25          # the sensor can't measure closer than ~20-25 cm
SONAR_READINGS_NEEDED = 3  # consecutive close readings (3 x 0.1 s = 0.3 s)
SONAR_PING_S = 0.1         # time between readings
SONAR_WARMUP_S = 3
SONAR_PRINT_DISTANCE = False  # print every reading, handy for aiming

# PIR motion sensor (SENSOR = "pir")
PIR_PIN = board.EXTERNAL_BUTTON  # the "Btn" screw terminal
PIR_WARMUP_S = 45          # PIR output is unreliable for ~30-60 s after power-up

# False-trigger filtering (sunlight, shadows, wind). A "trigger" is the PIR
# output going high, plus one more for every PIR_SUSTAIN_S it stays high.
# Motion only counts once PIR_TRIGGERS_NEEDED triggers land within
# PIR_TRIGGER_WINDOW_S, so a single short blip is ignored but a person who
# keeps moving gets through. Set PIR_SUSTAIN_S just above the shortest pulse
# your PIR gives (the console prints each pulse length). 1 = no filtering.
PIR_TRIGGERS_NEEDED = 2
PIR_TRIGGER_WINDOW_S = 8
PIR_SUSTAIN_S = 4

# Sound. WAVs must be mono, 16-bit, at SAMPLE_RATE (see README.md).
SOUND_DIR = "/sounds"
SAMPLE_RATE = 22050
VOLUME = 1.0               # 0.0 .. 1.0

# Built-in RGB LED shows what the bag is doing (see README.md for colours).
STATUS_LED = True
STATUS_BRIGHTNESS = 0.15   # 0.0 .. 1.0

DEBUG = True               # print timestamped events to the serial console

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def now_ms():
    # Integer milliseconds. time.monotonic() is a float and loses precision
    # after a few hours of uptime, which would make the motion stutter.
    return time.monotonic_ns() // 1_000_000


def ms(seconds):
    return int(seconds * 1000)


def random_ms(lo_s, hi_s):
    return random.randint(ms(lo_s), ms(hi_s))


BOOT_MS = now_ms()


def timestamp(now):
    """Time since start-up as [h:mm:ss.t]."""
    t = now - BOOT_MS
    tenths = (t % 1000) // 100
    secs = t // 1000
    return "[{}:{:02d}:{:02d}.{}]".format(secs // 3600, secs // 60 % 60, secs % 60, tenths)


def log(*args):
    if DEBUG:
        print(timestamp(now_ms()), *args)


# ---------------------------------------------------------------------------
# Servo motion
# ---------------------------------------------------------------------------

US_PER_DEG = (PULSE_MAX_US - PULSE_MIN_US) / SERVO_TRAVEL_DEG
CENTER_US = (PULSE_MIN_US + PULSE_MAX_US) / 2
PERIOD_US = 20000  # 50 Hz


def deg_to_us(deg):
    return CENTER_US + deg * US_PER_DEG


class Axis:
    def __init__(self, pin, min_deg, max_deg, rest_deg, reversed_):
        self.pwm = pwmio.PWMOut(pin, frequency=50, duty_cycle=0)
        lo_deg, hi_deg = min(min_deg, max_deg), max(min_deg, max_deg)
        self.lo_us = max(deg_to_us(lo_deg), PULSE_MIN_US)
        self.hi_us = min(deg_to_us(hi_deg), PULSE_MAX_US)
        self.min_deg = min_deg
        self.max_deg = max_deg
        self.rest_deg = rest_deg
        self.reversed = reversed_
        self.rest_us = deg_to_us(rest_deg)
        self.target = self.filtered = self.pos = self.rest_us
        self.enabled = False

    def clamp(self, us):
        return min(max(us, self.lo_us), self.hi_us)

    def bend_to_us(self, bend):
        """Convert a bend in -1..+1 (0 = rest) to a pulse width."""
        if self.reversed:
            bend = -bend
        if bend >= 0:
            return deg_to_us(self.rest_deg + bend * (self.max_deg - self.rest_deg))
        return deg_to_us(self.rest_deg + bend * (self.rest_deg - self.min_deg))

    def set_target(self, us):
        self.target = self.clamp(us)

    def enable(self):
        self.enabled = True
        self._write()

    def disable(self):
        # Duty cycle 0 = no pulses, so the servo stops holding and goes quiet.
        self.enabled = False
        self.pwm.duty_cycle = 0

    def _write(self):
        self.pwm.duty_cycle = int(self.clamp(self.pos) * 65535 / PERIOD_US)

    def update(self, dt_s):
        """Advance both filter stages one tick and write the result."""
        self.filtered += (self.target - self.filtered) * FILTER
        step = (self.filtered - self.pos) * FILTER * 2  # second, quicker stage
        max_step = MAX_SPEED_DEG_PER_S * US_PER_DEG * dt_s
        self.pos += min(max(step, -max_step), max_step)
        if self.enabled:
            self._write()

    def settled(self):
        return abs(self.pos - self.target) < 3 and abs(self.filtered - self.target) < 3


axes = [Axis(*cfg) for cfg in SERVOS]
side = [1 if i % 2 == 0 else -1 for i in range(len(axes))]


def go_to_rest():
    for a in axes:
        a.set_target(a.rest_us)


def pick_new_targets():
    # Always a decent distance from rest, usually on the opposite side from
    # last time, so the bag twists rather than drifting.
    for i, a in enumerate(axes):
        if random.random() < 0.7:
            side[i] = -side[i]
        amount = MIN_AMPLITUDE + (1.0 - MIN_AMPLITUDE) * random.random()
        a.set_target(a.bend_to_us(side[i] * amount))


# ---------------------------------------------------------------------------
# Sound
# ---------------------------------------------------------------------------

# The amp, servo header and 5V terminal (which powers the sensor) are all off
# until this pin goes high.
external_power = digitalio.DigitalInOut(board.EXTERNAL_POWER)
external_power.switch_to_output(value=True)

i2s = audiobusio.I2SOut(board.I2S_BIT_CLOCK, board.I2S_WORD_SELECT, board.I2S_DATA)
mixer = audiomixer.Mixer(
    voice_count=1,
    sample_rate=SAMPLE_RATE,
    channel_count=1,
    bits_per_sample=16,
    samples_signed=True,
    buffer_size=4096,
)
mixer.voice[0].level = VOLUME
i2s.play(mixer)


def find_sounds():
    try:
        names = os.listdir(SOUND_DIR)
    except OSError:
        print("No", SOUND_DIR, "folder - running without sound")
        return []
    sounds = []
    for name in sorted(names):
        if name.startswith(".") or not name.lower().endswith(".wav"):
            continue
        path = SOUND_DIR + "/" + name
        try:
            with open(path, "rb") as f:
                wav = audiocore.WaveFile(f)
                ok = (wav.sample_rate == SAMPLE_RATE and wav.channel_count == 1
                      and wav.bits_per_sample == 16)
        except (OSError, ValueError) as e:
            print("Skipping", path, "-", e)
            continue
        if ok:
            sounds.append(path)
        else:
            print("Skipping", path, "- must be mono 16-bit", SAMPLE_RATE, "Hz")
    log("Sounds:", sounds)
    return sounds


sounds = find_sounds()
last_sound = None
sound_file = None


def play_random_sound():
    global last_sound, sound_file
    if not sounds:
        return
    choices = [s for s in sounds if s != last_sound] or sounds
    path = random.choice(choices)
    last_sound = path
    mixer.voice[0].stop()
    if sound_file:
        sound_file.close()
    sound_file = open(path, "rb")
    mixer.voice[0].play(audiocore.WaveFile(sound_file))
    log("Playing", path)


def sound_playing():
    return mixer.voice[0].playing


# ---------------------------------------------------------------------------
# Sensors
# ---------------------------------------------------------------------------

led = digitalio.DigitalInOut(board.LED)  # mirrors the raw sensor, handy for aiming
led.switch_to_output(value=False)

last_motion_ms = None   # last time motion was confirmed
trigger_times = []      # recent PIR trigger timestamps, oldest first
cooldown_until_ms = 0


def motion_recent(now):
    return last_motion_ms is not None and now - last_motion_ms <= ms(MOTION_HOLD_S)


def ignored_reason(now):
    """Why detections are being ignored right now, or None."""
    if state == STARTUP:
        return "warm-up"
    if now < cooldown_until_ms:
        return "cooldown, {} s left".format((cooldown_until_ms - now) // 1000)
    return None


# --- PIR -------------------------------------------------------------------

pir_was_high = False
pir_high_since_ms = 0
next_sustain_ms = 0
if SENSOR == "pir":
    pir = digitalio.DigitalInOut(PIR_PIN)
    pir.switch_to_input(pull=digitalio.Pull.DOWN)  # reads "no motion" if unplugged


def register_trigger(now):
    global last_motion_ms
    reason = ignored_reason(now)
    if reason:
        log("PIR trigger ignored (" + reason + ")")
        return
    trigger_times.append(now)
    while trigger_times and now - trigger_times[0] > ms(PIR_TRIGGER_WINDOW_S):
        trigger_times.pop(0)
    log("PIR trigger", len(trigger_times), "of", PIR_TRIGGERS_NEEDED)
    if len(trigger_times) >= PIR_TRIGGERS_NEEDED:
        last_motion_ms = now


def update_pir(now):
    """Turn the PIR output into triggers: one when it goes high, then one
    more for every PIR_SUSTAIN_S it stays high."""
    global pir_was_high, pir_high_since_ms, next_sustain_ms
    motion = pir.value
    led.value = motion
    if motion and not pir_was_high:
        pir_high_since_ms = now
        next_sustain_ms = now + ms(PIR_SUSTAIN_S)
        register_trigger(now)
    elif motion and now >= next_sustain_ms:
        next_sustain_ms += ms(PIR_SUSTAIN_S)
        register_trigger(now)
    elif not motion and pir_was_high:
        log("PIR pulse", (now - pir_high_since_ms) / 1000, "s")
    pir_was_high = motion


# --- JSN-SR04T ultrasonic ----------------------------------------------------
#
# Each reading sends a 20 us trigger pulse and times the Echo pulse by polling
# the pin (more dependable than pulseio on the RP2040). It only waits as long
# as an echo from SONAR_TRIGGER_CM would take, so a reading blocks for at most
# ~15 ms; anything further away just reads as "far".

SONAR_ECHO_START_TIMEOUT_US = 10000  # echo should start within a few ms
SONAR_NO_ECHO_WARN_S = 10

sonar_near = 0           # consecutive close readings
next_ping_ms = 0
sonar_seen_echo = False  # has the sensor answered at all since start-up?
last_answer_ms = 0       # last time the sensor answered
busy_since_ms = None     # Echo already high when we wanted to ping
if SENSOR == "sonar":
    sonar_trig = digitalio.DigitalInOut(SONAR_TRIG_PIN)
    sonar_trig.switch_to_output(value=False)
    sonar_echo = digitalio.DigitalInOut(SONAR_ECHO_PIN)
    sonar_echo.switch_to_input()  # the divider's 2k pulls it low


def sonar_measure():
    """One reading. Returns (status, cm):
    "ok"   - echo received, cm is the distance
    "far"  - echo started but nothing within SONAR_TRIGGER_CM
    "none" - Echo never went high: the sensor didn't answer
    "busy" - Echo was still high from the last reading; skipped"""
    if sonar_echo.value:
        return "busy", None
    sonar_trig.value = True
    microcontroller.delay_us(20)
    sonar_trig.value = False
    deadline = time.monotonic_ns() + SONAR_ECHO_START_TIMEOUT_US * 1000
    while not sonar_echo.value:
        if time.monotonic_ns() > deadline:
            return "none", None
    start = time.monotonic_ns()
    limit = start + int((SONAR_TRIGGER_CM + 30) * 58 * 1000)  # 58 us per cm
    while sonar_echo.value:
        if time.monotonic_ns() > limit:
            return "far", None
    return "ok", (time.monotonic_ns() - start) / 58000


def check_sonar_health(now, status, cm):
    """Report the first answer, and explain if the sensor stops answering."""
    global sonar_seen_echo, last_answer_ms, busy_since_ms
    if status == "busy":
        if busy_since_ms is None:
            busy_since_ms = now
        elif now - busy_since_ms >= ms(SONAR_NO_ECHO_WARN_S):
            log("Sonar: Echo pin", SONAR_ECHO_PIN, "is stuck HIGH - check the Echo",
                "wiring and divider (1k in series, 2k from the pin to GND)")
            busy_since_ms = now
        return
    busy_since_ms = None
    if status in ("ok", "far"):
        if not sonar_seen_echo:
            log("Sonar OK, first reading:",
                "{:.0f} cm".format(cm) if cm is not None else "nothing within range")
        sonar_seen_echo = True
        last_answer_ms = now
    elif now - last_answer_ms >= ms(SONAR_NO_ECHO_WARN_S):
        log("Sonar: no echo for {} s. Echo never goes high. Check: 5V and GND at the"
            " sensor; Trig on {}; Echo through 1k to {} with 2k (not 1k) to GND".format(
                SONAR_NO_ECHO_WARN_S, SONAR_TRIG_PIN, SONAR_ECHO_PIN))
        last_answer_ms = now


def handle_distance(now, status, cm):
    global sonar_near, last_motion_ms
    check_sonar_health(now, status, cm)
    if status == "busy":
        return
    near = status == "ok" and SONAR_MIN_CM <= cm <= SONAR_TRIGGER_CM
    led.value = near
    if SONAR_PRINT_DISTANCE:
        if status == "ok":
            log("Distance {:.0f} cm".format(cm))
        elif status == "far":
            log("Distance >", SONAR_TRIGGER_CM, "cm")
        else:
            log("Distance: no echo")
    if not near:
        if sonar_near:
            log("Sonar clear")
        sonar_near = 0
        return
    sonar_near += 1
    if sonar_near == 1:
        log("Sonar: something at {:.0f} cm".format(cm))
    if sonar_near < SONAR_READINGS_NEEDED:
        return
    reason = ignored_reason(now)
    if reason:
        if sonar_near == SONAR_READINGS_NEEDED:
            log("Sonar detection ignored (" + reason + ")")
        return
    if not motion_recent(now):
        log("Sonar detection confirmed")
    last_motion_ms = now


def update_sonar(now):
    global next_ping_ms
    if now < next_ping_ms:
        return
    next_ping_ms = now + ms(SONAR_PING_S)
    status, cm = sonar_measure()
    handle_distance(now, status, cm)


def update_sensor(now):
    if SENSOR == "sonar":
        update_sonar(now)
    else:
        update_pir(now)


def start_cooldown(now):
    global cooldown_until_ms, last_motion_ms, sonar_near
    cooldown_until_ms = now + ms(COOLDOWN_S)
    last_motion_ms = None
    del trigger_times[:]
    sonar_near = 0
    if COOLDOWN_S:
        log("Cooldown", COOLDOWN_S, "s")


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------

STARTUP, WAITING, FIT, RESTING = "STARTUP", "WAITING", "FIT", "RESTING"
state = STARTUP
state_start_ms = 0
state_len_ms = 0
next_target_ms = 0
settled_since_ms = None


def enter_state(new_state, now, length_ms=0):
    global state, state_start_ms, state_len_ms
    state = new_state
    state_start_ms = now
    state_len_ms = length_ms
    log("->", new_state, "for", length_ms, "ms")


def start_fit(now):
    global next_target_ms
    for a in axes:
        a.enable()
    play_random_sound()
    next_target_ms = now
    enter_state(FIT, now, random_ms(FIT_MIN_S, FIT_MAX_S))


def detach_when_settled(now):
    """Once both servos have sat at rest a while, stop driving them."""
    global settled_since_ms
    if not all(a.settled() for a in axes):
        settled_since_ms = None
        return
    if settled_since_ms is None:
        settled_since_ms = now
    if now - settled_since_ms >= ms(DETACH_AFTER_S):
        for a in axes:
            if a.enabled:
                a.disable()


def run_behaviour(now):
    global next_target_ms
    elapsed = now - state_start_ms

    if state == STARTUP:
        detach_when_settled(now)
        if elapsed >= state_len_ms:
            enter_state(WAITING, now)

    elif state == WAITING:
        detach_when_settled(now)
        if motion_recent(now):
            start_fit(now)

    elif state == FIT:
        done = elapsed >= state_len_ms
        if FIT_WAITS_FOR_SOUND and sound_playing():
            done = False
        if done:
            go_to_rest()
            enter_state(RESTING, now, random_ms(REST_MIN_S, REST_MAX_S))
        elif now >= next_target_ms:
            pick_new_targets()
            next_target_ms = now + random_ms(NEW_TARGET_MIN_S, NEW_TARGET_MAX_S)

    elif state == RESTING:
        detach_when_settled(now)
        if elapsed >= state_len_ms:
            if motion_recent(now):
                start_fit(now)
            else:
                start_cooldown(now)
                enter_state(WAITING, now)


# ---------------------------------------------------------------------------
# Status LED
# ---------------------------------------------------------------------------

COLOURS = {
    "warmup": (128, 0, 255),    # purple: warming up, sensor ignored
    "armed": (0, 255, 0),       # green: waiting for someone
    "pending": (255, 160, 0),   # yellow: detected, waiting for confirmation
    "fit": (255, 0, 0),         # red: scaring
    "resting": (255, 60, 0),    # orange: pause between fits
    "cooldown": (0, 0, 255),    # blue: sensor ignored after a scare
}

status_pin = None
if STATUS_LED:
    status_pin = digitalio.DigitalInOut(board.NEOPIXEL)
    status_pin.direction = digitalio.Direction.OUTPUT
status_shown = None


def status_name(now):
    if state == STARTUP:
        return "warmup"
    if state == FIT:
        return "fit"
    if state == RESTING:
        return "resting"
    if now < cooldown_until_ms:
        return "cooldown"
    if SENSOR == "sonar" and 0 < sonar_near < SONAR_READINGS_NEEDED:
        return "pending"
    if SENSOR == "pir" and trigger_times and \
            now - trigger_times[-1] <= ms(PIR_TRIGGER_WINDOW_S):
        return "pending"
    return "armed"


def update_status_led(now):
    global status_shown
    if status_pin is None:
        return
    name = status_name(now)
    if name == status_shown:
        return
    status_shown = name
    r, g, b = [int(c * STATUS_BRIGHTNESS) for c in COLOURS[name]]
    neopixel_write.neopixel_write(status_pin, bytearray((g, r, b)))  # GRB order


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------

# We can't know where the servos are at power-up, so they jump to rest once.
# Enable them one at a time so both don't draw stall current together.
for a in axes:
    a.enable()
    time.sleep(0.4)

log("Sensor:", SENSOR)
warmup_s = SONAR_WARMUP_S if SENSOR == "sonar" else PIR_WARMUP_S
enter_state(STARTUP, now_ms(), ms(warmup_s))
last_update_ms = now_ms()

while True:
    now = now_ms()

    update_sensor(now)

    dt_ms = now - last_update_ms
    if dt_ms >= ms(UPDATE_S):
        last_update_ms = now
        run_behaviour(now)
        update_status_led(now)
        dt_s = min(dt_ms, 100) / 1000
        for a in axes:
            a.update(dt_s)

    time.sleep(0.002)
