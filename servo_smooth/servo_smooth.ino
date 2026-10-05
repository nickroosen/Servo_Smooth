// Servo_Smooth - animatronic body bag controller
//
// Rewrite of servo_with_random_delay.ino for higher-torque servos.
//   - Non-blocking: no delay() in the motion path, so both servos move
//     smoothly and the sensor is checked continuously.
//   - Two-stage low-pass filter plus a speed limit gives soft starts and
//     stops instead of slamming the spine/cables.
//   - Per-servo pulse limits, centre and direction.
//   - Wriggles in "fits": sound + thrashing for a few seconds, then a
//     random rest, repeated while the sensor stays triggered.
//   - Servos are attached one at a time on power-up and detached while
//     resting, to avoid brown-outs and buzzing/heating.
//
// Hardware: Arduino Uno, Adafruit Motor Shield V2 (servo headers are
// D9/D10), 2 x DS3240MG servos on their own 6 V supply, optional Adafruit
// Audio FX board, optional sensor on A2.
// No extra libraries needed (Metro is no longer used).

#include <Servo.h>

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Servo type. The DS3240MG maps 500..2500 us onto its full travel, which
// is 180 or 270 degrees depending on the version you bought (it's on the
// label). Getting this wrong makes every angle below 1.5x too big or small.
const float SERVO_TRAVEL_DEG = 270;
const int PULSE_MIN_US = 500;
const int PULSE_MAX_US = 2500;

// Angles are in degrees from the servo's centre (1500 us). The DS3240MG has
// roughly 10x the torque of the original S3004s, enough to snap the wire
// rope or crack a spine disk, so start narrow and widen a few degrees at a
// time while watching the spine. (The original 800..2200 us range would be
// about +/-63 deg on the 180 deg version, +/-95 deg on the 270.)
struct ServoConfig {
  uint8_t pin;
  float minDeg;   // furthest safe angle one way (negative)
  float maxDeg;   // furthest safe angle the other way (positive)
  float restDeg;  // angle where the spine hangs straight/relaxed
  bool reversed;  // flip if this side moves the wrong way
};

const uint8_t NUM_SERVOS = 2;
ServoConfig SERVO_CFG[NUM_SERVOS] = {
  // pin, minDeg, maxDeg, restDeg, reversed
  {  9,    -45,    45,     0,     false },  // "right" in the original sketch
  { 10,    -45,    45,     0,     false },  // "left"
};

// Motion feel
const float FILTER = 0.10;              // 0.01 (lazy) .. 1.0 (no smoothing); was "filtro"
const float MAX_SPEED_DEG_PER_S = 180;  // hard speed cap; the servo can do ~350
const unsigned long UPDATE_MS = 20;  // servo refresh period (50 Hz)
const float MIN_AMPLITUDE = 0.35;    // each new target is at least this far from rest (0..1)

// Timing (milliseconds)
const unsigned long STARTUP_DELAY_MS = 5000;    // wait after power-up, like the original
const unsigned long NEW_TARGET_MIN_MS = 50;     // how often a new random target is chosen
const unsigned long NEW_TARGET_MAX_MS = 500;
const unsigned long FIT_MIN_MS = 2500;          // length of one wriggling fit
const unsigned long FIT_MAX_MS = 7000;
const unsigned long REST_MIN_MS = 2000;         // pause between fits (was MIN_TIM/MAX_TIM)
const unsigned long REST_MAX_MS = 10000;
const unsigned long DETACH_AFTER_MS = 1500;     // detach servos once settled at rest

// Sound: Audio FX trigger pin, pulled LOW to play. Set to -1 to disable.
const int SOUND_PIN = 13;
const unsigned long SOUND_PULSE_MS = 150;

// Trigger sensor on an analog pin. The bag only wriggles while the reading
// is inside [SENSOR_LOW, SENSOR_HIGH] (same window as the original sketch).
// Set USE_SENSOR to false to wriggle forever on the random schedule.
const bool USE_SENSOR = true;
const uint8_t SENSOR_PIN = A2;
const int SENSOR_LOW = 200;
const int SENSOR_HIGH = 400;

const bool DEBUG = true;  // print state changes to Serial (115200 baud)

// ---------------------------------------------------------------------------
// Servo motion
// ---------------------------------------------------------------------------

struct Axis {
  Servo servo;
  float target;    // where we want to go (us)
  float filtered;  // first filter stage
  float pos;       // second filter stage = what the servo is told (us)
  bool attached;
};

Axis axes[NUM_SERVOS];

const float US_PER_DEG = (PULSE_MAX_US - PULSE_MIN_US) / SERVO_TRAVEL_DEG;
const float CENTER_US = (PULSE_MIN_US + PULSE_MAX_US) / 2.0;

float degToUs(float deg) {
  return CENTER_US + deg * US_PER_DEG;
}

float restUs(uint8_t i) {
  return degToUs(SERVO_CFG[i].restDeg);
}

int clampUs(uint8_t i, float us) {
  const ServoConfig &c = SERVO_CFG[i];
  float lo = degToUs(min(c.minDeg, c.maxDeg));
  float hi = degToUs(max(c.minDeg, c.maxDeg));
  lo = max(lo, (float)PULSE_MIN_US);
  hi = min(hi, (float)PULSE_MAX_US);
  return (int)(constrain(us, lo, hi) + 0.5);
}

// Convert a bend in -1..+1 (0 = rest) to a pulse width for servo i.
float bendToUs(uint8_t i, float bend) {
  const ServoConfig &c = SERVO_CFG[i];
  if (c.reversed) bend = -bend;
  if (bend >= 0) return degToUs(c.restDeg + bend * (c.maxDeg - c.restDeg));
  return degToUs(c.restDeg + bend * (c.restDeg - c.minDeg));
}

void attachAxis(uint8_t i) {
  if (axes[i].attached) return;
  // Setting the pulse before attach() makes the first pulse go to the
  // current position rather than the library default of 1500 us.
  axes[i].servo.writeMicroseconds(clampUs(i, axes[i].pos));
  axes[i].servo.attach(SERVO_CFG[i].pin, PULSE_MIN_US, PULSE_MAX_US);
  axes[i].attached = true;
}

void detachAxis(uint8_t i) {
  if (!axes[i].attached) return;
  axes[i].servo.detach();
  axes[i].attached = false;
}

void setTarget(uint8_t i, float us) {
  axes[i].target = clampUs(i, us);
}

// Advance both filter stages one tick and write the result.
void updateAxis(uint8_t i, float dtS) {
  Axis &a = axes[i];
  a.filtered += (a.target - a.filtered) * FILTER;
  float step = (a.filtered - a.pos) * FILTER * 2;  // second, quicker stage
  float maxStep = MAX_SPEED_DEG_PER_S * US_PER_DEG * dtS;
  a.pos += constrain(step, -maxStep, maxStep);
  if (a.attached) a.servo.writeMicroseconds(clampUs(i, a.pos));
}

bool axisSettled(uint8_t i) {
  return fabs(axes[i].pos - axes[i].target) < 3 &&
         fabs(axes[i].filtered - axes[i].target) < 3;
}

// ---------------------------------------------------------------------------
// Sound (non-blocking pulse)
// ---------------------------------------------------------------------------

unsigned long soundStartedMs = 0;
bool soundActive = false;

void playSound() {
  if (SOUND_PIN < 0) return;
  digitalWrite(SOUND_PIN, LOW);
  soundStartedMs = millis();
  soundActive = true;
}

void updateSound(unsigned long now) {
  if (soundActive && now - soundStartedMs >= SOUND_PULSE_MS) {
    digitalWrite(SOUND_PIN, HIGH);
    soundActive = false;
  }
}

// ---------------------------------------------------------------------------
// Behaviour
// ---------------------------------------------------------------------------

bool sensorTriggered() {
  if (!USE_SENSOR) return true;
  int v = analogRead(SENSOR_PIN);
  return v >= SENSOR_LOW && v <= SENSOR_HIGH;
}

enum State { STARTUP, WAITING, FIT, RESTING };
State state = STARTUP;
unsigned long stateStartMs = 0;
unsigned long stateLengthMs = 0;
unsigned long nextTargetMs = 0;
unsigned long settledSinceMs = 0;

void enterState(State s, unsigned long now, unsigned long lengthMs) {
  state = s;
  stateStartMs = now;
  stateLengthMs = lengthMs;
  if (DEBUG) {
    static const char *const names[] = { "STARTUP", "WAITING", "FIT", "RESTING" };
    Serial.print(F("-> "));
    Serial.print(names[s]);
    Serial.print(F(" for "));
    Serial.print(lengthMs);
    Serial.println(F(" ms"));
  }
}

void goToRest() {
  for (uint8_t i = 0; i < NUM_SERVOS; i++) setTarget(i, restUs(i));
}

void startFit(unsigned long now) {
  for (uint8_t i = 0; i < NUM_SERVOS; i++) attachAxis(i);
  playSound();
  nextTargetMs = now;
  enterState(FIT, now, random(FIT_MIN_MS, FIT_MAX_MS + 1));
}

// Pick a fresh random bend for every servo, always a decent distance from
// rest and on alternating sides so the bag twists rather than drifts.
void pickNewTargets() {
  static int8_t side[NUM_SERVOS] = { 1, -1 };
  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    if (random(100) < 70) side[i] = -side[i];  // usually swap sides
    float amount = MIN_AMPLITUDE + (1.0 - MIN_AMPLITUDE) * random(1001) / 1000.0;
    setTarget(i, bendToUs(i, side[i] * amount));
  }
}

// Once both servos have sat at rest for DETACH_AFTER_MS, stop driving them
// so they don't buzz and heat up while idle.
void detachWhenSettled(unsigned long now) {
  bool settled = true;
  for (uint8_t i = 0; i < NUM_SERVOS; i++) settled &= axisSettled(i);
  if (!settled) {
    settledSinceMs = 0;
    return;
  }
  if (settledSinceMs == 0) settledSinceMs = now;
  if (now - settledSinceMs >= DETACH_AFTER_MS) {
    for (uint8_t i = 0; i < NUM_SERVOS; i++) detachAxis(i);
  }
}

void runBehaviour(unsigned long now) {
  unsigned long elapsed = now - stateStartMs;

  switch (state) {
    case STARTUP:
      detachWhenSettled(now);
      if (elapsed >= stateLengthMs) enterState(WAITING, now, 0);
      break;

    case WAITING:
      detachWhenSettled(now);
      if (sensorTriggered()) startFit(now);
      break;

    case FIT:
      if (elapsed >= stateLengthMs) {
        goToRest();
        enterState(RESTING, now, random(REST_MIN_MS, REST_MAX_MS + 1));
      } else if ((long)(now - nextTargetMs) >= 0) {
        pickNewTargets();
        nextTargetMs = now + random(NEW_TARGET_MIN_MS, NEW_TARGET_MAX_MS + 1);
      }
      break;

    case RESTING:
      detachWhenSettled(now);
      if (elapsed >= stateLengthMs) {
        if (sensorTriggered()) startFit(now);
        else enterState(WAITING, now, 0);
      }
      break;
  }
}

// ---------------------------------------------------------------------------

void setup() {
  if (DEBUG) Serial.begin(115200);
  randomSeed(analogRead(A0) ^ (analogRead(A1) << 4) ^ micros());

  if (SOUND_PIN >= 0) {
    digitalWrite(SOUND_PIN, HIGH);  // idle high before becoming an output
    pinMode(SOUND_PIN, OUTPUT);
  }

  // We can't know where the servos are at power-up, so they will jump to
  // rest once. Attach them one at a time so two high-torque servos don't
  // draw their stall current at the same moment and reset the board.
  for (uint8_t i = 0; i < NUM_SERVOS; i++) {
    axes[i].target = axes[i].filtered = axes[i].pos = restUs(i);
    attachAxis(i);
    delay(400);
  }

  enterState(STARTUP, millis(), STARTUP_DELAY_MS);
}

void loop() {
  static unsigned long lastUpdateMs = 0;
  unsigned long now = millis();

  updateSound(now);

  if (now - lastUpdateMs < UPDATE_MS) return;
  float dtS = (now - lastUpdateMs) / 1000.0;
  if (dtS > 0.1) dtS = 0.1;
  lastUpdateMs = now;

  runBehaviour(now);
  for (uint8_t i = 0; i < NUM_SERVOS; i++) updateAxis(i, dtS);
}
