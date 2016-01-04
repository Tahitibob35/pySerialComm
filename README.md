# SerialComm

# About

This python module simplifies serial communications with an arduino board (https://github.com/Tahitibob35/SerialComm).

# Features

- Attach actions to functions
- Simply send and receive strings or integers
- Manage acknowledgments

# Examples

## 1 - Python -> Arduino, without ack

Arduino receiver code
```c
SerialComm s(Serial);

void remoteAnalogWrite( void ) {
    int pin = 0;
    int value = 0;
    s.getData("ii", &pin, &value);
    analogWrite(pin, value);
}

void setup() {
  s.attach(2, remoteAnalogWrite);
}
```

Python sender script
```python
arduino = SerialComm('/dev/ttyUSB0', baudrate=115200)
pin = 9
value = 120
resp = arduino.sendmessage(2, (pin,value), ack=False)
```

## 2 - Python -> Arduino, with ack

### Arduino receiver code

```c
SerialComm s(Serial);

void remoteAnalogRead( void ) {
    int pin;
    s.getData("i", &pin);
    int value = analogRead(pin);
    s.sendAck(s.getId() , "i", value);
}

void setup() {
  s.attach(2, remoteAnalogRead);
}
```

### Python sender script
```python
arduino = SerialComm('/dev/ttyUSB0', baudrate=115200)
pin = 5
resp = arduino.sendmessage(2, (i,), ack=True)
values = arduino.parsedata("i", resp)
pin_value = values[0]
```


