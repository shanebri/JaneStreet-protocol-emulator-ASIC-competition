// Nano 33 BLE (nRF52840), Arduino Mbed OS Nano Boards core.
// Hardware SPIS2/EasyDMA, mode 0, MSB-first. No SPI.begin() or BLE libraries.
#include <Arduino.h>
#include <nrf.h>

#if !defined(ARDUINO_ARDUINO_NANO33BLE)
#error "Select Arduino Nano 33 BLE with the Arduino Mbed OS Nano Boards core"
#endif

// Arduino's official Nano 33 BLE variant: D10=P1.02, D11=P1.01,
// D12=P1.08, D13=P0.13. D2 is our READY output, not an SPI signal.
static const uint32_t PIN_CS = 32 + 2, PIN_MOSI = 32 + 1;
static const uint32_t PIN_MISO = 32 + 8, PIN_SCK = 13;
static const int READY_PIN = 2;
alignas(4) static uint8_t txBuffer[1];
alignas(4) static uint8_t rxBuffer[2]; // A second byte detects overlong transfers.
static uint16_t sequenceNumber = 0;
static uint16_t failures = 0;
static bool armed = false, pendingRearm = false;
static uint32_t endedAt = 0;
static char command[24];
static size_t commandLength = 0;

static bool acquireBuffer() {
    NRF_SPIS2->EVENTS_ACQUIRED = 0;
    NRF_SPIS2->TASKS_ACQUIRE = 1;
    uint32_t started = millis();
    while (!NRF_SPIS2->EVENTS_ACQUIRED) {
        if (millis() - started > 100) {
            Serial.println("ERROR semaphore_timeout");
            return false;
        }
    }
    __DMB();
    return true;
}

static void prepareByte() {
    // CPU owns the semaphore here; DMA buffers live in RAM, not Flash/stack.
    txBuffer[0] = static_cast<uint8_t>(sequenceNumber) ^ 0xA5;
    rxBuffer[0] = rxBuffer[1] = 0;
    NRF_SPIS2->TXD.PTR = reinterpret_cast<uint32_t>(txBuffer);
    NRF_SPIS2->TXD.MAXCNT = 1;
    NRF_SPIS2->RXD.PTR = reinterpret_cast<uint32_t>(rxBuffer);
    NRF_SPIS2->RXD.MAXCNT = 2;
    NRF_SPIS2->EVENTS_END = 0;
    NRF_SPIS2->EVENTS_ACQUIRED = 0;
    __DMB();
    NRF_SPIS2->TASKS_RELEASE = 1;
    __DSB();
    armed = true;
    digitalWrite(READY_PIN, HIGH);
}

static void armBatch() {
    digitalWrite(READY_PIN, LOW);
    armed = pendingRearm = false;
    // ARM is only allowed while the FPGA is idle/reset, CS_n high.
    if (digitalRead(10) == LOW) {
        Serial.println("ERROR cs_active_reset_fpga_first");
        return;
    }
    NRF_SPIS2->ENABLE = 0;
    NRF_SPIS2->EVENTS_END = 0;
    NRF_SPIS2->EVENTS_ACQUIRED = 0;
    NRF_SPIS2->ENABLE = SPIS_ENABLE_ENABLE_Enabled;
    sequenceNumber = failures = 0;
    if (!acquireBuffer()) return;
    prepareByte();
    Serial.println("ARMED 256 MODE0 MSB");
}

void setup() {
    pinMode(READY_PIN, OUTPUT);
    digitalWrite(READY_PIN, LOW);
    pinMode(10, INPUT_PULLUP);
    pinMode(11, INPUT);
    pinMode(12, INPUT); // SPIS controls MISO direction, including CS high-Z.
    pinMode(13, INPUT); // D13's onboard LED may flicker with SCLK; do not drive it.
    Serial.begin(115200); // USB CDC; no while(!Serial) startup deadlock.
    NRF_SPIS2->ENABLE = 0;
    NRF_SPIS2->INTENCLR = 0xFFFFFFFF;
    NRF_SPIS2->PSEL.SCK = PIN_SCK;
    NRF_SPIS2->PSEL.MOSI = PIN_MOSI;
    NRF_SPIS2->PSEL.MISO = PIN_MISO;
    NRF_SPIS2->PSEL.CSN = PIN_CS;
    NRF_SPIS2->CONFIG = 0; // CPOL=0, CPHA=0, ORDER=MSB-first.
    NRF_SPIS2->DEF = 0xEE;
    NRF_SPIS2->ORC = 0xEE;
    NRF_SPIS2->SHORTS = SPIS_SHORTS_END_ACQUIRE_Msk;
    NRF_SPIS2->ENABLE = SPIS_ENABLE_ENABLE_Enabled;
}

void loop() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            command[commandLength] = 0;
            if (!strcmp(command, "ARM")) armBatch();
            else if (!strcmp(command, "PING")) Serial.println("PIO_SPI_NANO_V1");
            else Serial.println("ERROR unknown_command");
            commandLength = 0;
        } else if (commandLength < sizeof(command) - 1) command[commandLength++] = c;
        else { commandLength = 0; Serial.println("ERROR command_too_long"); }
    }
    if (armed && NRF_SPIS2->EVENTS_END && NRF_SPIS2->EVENTS_ACQUIRED) {
        digitalWrite(READY_PIN, LOW);
        __DMB();
        uint32_t amount = NRF_SPIS2->RXD.AMOUNT;
        uint8_t received = rxBuffer[0];
        bool ok = amount == 1 && received == static_cast<uint8_t>(sequenceNumber);
        if (!ok) failures++;
        // Decimal fields: sequence, MOSI received, MISO sent, byte count, pass.
        Serial.print("RX "); Serial.print(sequenceNumber);
        Serial.print(' '); Serial.print(received);
        Serial.print(' '); Serial.print(txBuffer[0]);
        Serial.print(' '); Serial.print(amount);
        Serial.print(' '); Serial.println(ok ? 1 : 0);
        armed = false;
        sequenceNumber++;
        if (sequenceNumber == 256) {
            Serial.print("DONE 256 "); Serial.println(failures);
        } else {
            endedAt = millis();
            pendingRearm = true;
        }
    }
    // Hold READY low long enough to observe, without relying on USB print timing.
    if (pendingRearm && millis() - endedAt >= 5 && digitalRead(10) == HIGH) {
        pendingRearm = false;
        prepareByte(); // END_ACQUIRE has already returned ownership to the CPU.
    }
}
