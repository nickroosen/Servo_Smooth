# Servo_Smooth - animatronic body bag for the Adafruit RP2040 Prop-Maker Feather
#
# Two DS3240MG servos pull the spine cables, a PIR sensor wakes the bag up,
# and a random WAV from /sounds plays through the on-board I2S amp each time
# it starts wriggling.
#
# Copy this file and a "sounds" folder of WAVs to the CIRCUITPY drive.
# No libraries from the bundle are needed.
#
# Wiring (see README.md):
#   Servo signals  -> D9, D10   (servo power from a separate 6 V UBEC!)
#   PIR output     -> "Btn" screw terminal, PIR power from "5V" and "G"
#   Speaker        -> "+" and "-" screw terminals (one 4-8 ohm speaker)

import os
import random
import time

import audiobusio
import audiocore
import audiomixer
import board
import digitalio
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

# PIR motion sensor
PIR_PIN = board.EXTERNAL_BUTTON  # the "Btn" screw terminal
PIR_WARMUP_S = 45          # PIR output is unreliable for ~30-60 s after power-up
PIR_HOLD_S = 10            # keep going for this long after the last motion

# Sound. WAVs must be mono, 16-bit, at SAMPLE_RATE (see README.md).
SOUND_DIR = "/sounds"
SAMPLE_RATE = 22050
VOLUME = 0.8               # 0.0 .. 1.0

DEBUG = True               # print state changes to the serial console

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


def log(*args):
    if DEBUG:
        print(*args)


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

# The amp, servo header and 5V terminal (which powers the PIR) are all off
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
# PIR
# ---------------------------------------------------------------------------

pir = digitalio.DigitalInOut(PIR_PIN)
pir.switch_to_input(pull=digitalio.Pull.DOWN)  # reads "no motion" if unplugged

led = digitalio.DigitalInOut(board.LED)  # mirrors the PIR, handy for aiming it
led.switch_to_output(value=False)

last_motion_ms = None


def motion_recent(now):
    return last_motion_ms is not None and now - last_motion_ms <= ms(PIR_HOLD_S)


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
                enter_state(WAITING, now)


# ---------------------------------------------------------------------------
# Start-up
# ---------------------------------------------------------------------------

# We can't know where the servos are at power-up, so they jump to rest once.
# Enable them one at a time so both don't draw stall current together.
for a in axes:
    a.enable()
    time.sleep(0.4)

enter_state(STARTUP, now_ms(), ms(PIR_WARMUP_S))
last_update_ms = now_ms()

while True:
    now = now_ms()

    motion = pir.value
    led.value = motion
    if motion and state != STARTUP:
        last_motion_ms = now

    dt_ms = now - last_update_ms
    if dt_ms >= ms(UPDATE_S):
        last_update_ms = now
        run_behaviour(now)
        dt_s = min(dt_ms, 100) / 1000
        for a in axes:
            a.update(dt_s)

    time.sleep(0.002)
