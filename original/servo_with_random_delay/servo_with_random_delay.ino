// easing servo movements with low pass filter
// the servo signal must be connected directly to the arduino pin 2
 
// Time interval, this executes one piece of code from time to time
// Download Metro lybrary and instructions:
// http://www.arduino.cc/playground/Code/Metro
#include <Metro.h>
int duration = 1000; // duration of the interval in miliseconds
Metro intervaller = Metro (duration);
 
// MegaServo library
// download and instructions:
// http://www.arduino.cc/playground/Code/MegaServo
//#include <MegaServo.h>
//MegaServo servos;
 
#include <Servo.h>
 
// servos minimum and maximum position
#define MIN_POS 800 // the minuimum pulse width for your servos
#define MAX_POS 2200 // maximum pulse width for your servos
#define MIN_TIM 2000 // minimum time to wait between loops
#define MAX_TIM 10000 // maximum time to wait between loops
 
Servo left;
Servo right;
const int soundPin =  13;
 
// servo pin
//#define s0_pin 9
//#define s1_pin 10
 
// variables to hold new destination positions
int d0; // destination0
int d1;
int d0_sh; // destination0 to be smoothed
int d1_sh;
int repeat;
int loop_num;


// the filter to be aplied
// this value will be multiplied by "d0" and added to "d0_sh"
float filtro = 0.1; // 0.01 to 1.0
 
// setup runs once, when the sketch starts
void setup() {
  // set sound pin
  pinMode(soundPin, OUTPUT);
  // set servo pin
  right.attach(9);
  left.attach(10);
}
 
// main program loop, executes forever after setup()
void loop() {
  delay(5000);  
  int sensorValue = analogRead(A2);
  do{
      
      digitalWrite(soundPin, LOW);
      delay(1000);
      digitalWrite(soundPin, HIGH);
      
      loop_num = random(400, 800);
      repeat = random(MIN_TIM, MAX_TIM);

      if (intervaller.check() == 1) {
        // calculate a new random position between max and min values
        d0 = random(MIN_POS, MAX_POS);
        d1 = random(MIN_POS, MAX_POS);
   
        // resets interval with a new random duration
        intervaller.interval(random(50,500));
       }
   
      // smooth the destination value
      d0_sh = d0_sh * (1.0-filtro) + d0 * filtro;
      d1_sh = d1_sh * (1.0-filtro) + d1 * filtro;
   
      // assign new position to the servo
      right.write(d0_sh);
      left.write(d1_sh);

      // delay to make the servo move
      delay(20);

        
      //then pause
      Serial.println(sensorValue);
      delay(repeat);  
  } while(200 < sensorValue && sensorValue < 400);
}
