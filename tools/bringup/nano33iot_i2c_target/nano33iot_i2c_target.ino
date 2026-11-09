// Deterministic 3.3 V I2C target for the Arty bring-up fixture.
#include <Wire.h>

#if !defined(ARDUINO_SAMD_NANO_33_IOT)
#error "Select Arduino Nano 33 IoT with the Arduino SAMD Boards core"
#endif

constexpr uint8_t targetAddress = 0x50;
constexpr uint8_t response[] = {0x50, 0x49, 0x4f};

void discardWrite(int) {
    while (Wire.available()) {
        Wire.read();
    }
}

void sendResponse() {
    // A repeated START can invoke onRequest before onReceive on SAMD.
    // The response is independent of the incoming register-pointer byte.
    Wire.write(response, sizeof(response));
}

void setup() {
    Wire.onReceive(discardWrite);
    Wire.onRequest(sendResponse);
    Wire.begin(targetAddress);
}

void loop() {}
