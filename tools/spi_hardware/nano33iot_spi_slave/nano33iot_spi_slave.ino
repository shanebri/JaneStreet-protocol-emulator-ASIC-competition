// Arduino Nano 33 IoT (SAMD21), SERCOM1 hardware SPI slave.
#include <Arduino.h>
#include <wiring_private.h>

#if !defined(ARDUINO_SAMD_NANO_33_IOT)
#error "Select Arduino Nano 33 IoT with the Arduino SAMD Boards core"
#endif

// SERCOM1 function C uses D11/PA16 for DI (PAD0), D13/PA17 for SCK
// (PAD1), D8/PA18 for SS (PAD2), and D12/PA19 for DO (PAD3).
static constexpr uint8_t CS_PIN = 8, MOSI_PIN = 11, MISO_PIN = 12, SCK_PIN = 13;
static constexpr uint8_t READY_PIN = 2;
static constexpr uint8_t FRAME_FLAGS = SERCOM_SPI_INTFLAG_SSL | SERCOM_SPI_INTFLAG_TXC;
static SercomSpi &spi = SERCOM1->SPI;
static uint16_t sequenceNumber = 0, failures = 0;
static uint8_t reply = 0;
static bool armed = false, pendingRearm = false;
static uint32_t endedAt = 0;
static char command[24];
static size_t commandLength = 0;
static bool commandTooLong = false;

static void resetSpi() {
    spi.CTRLA.reg = SERCOM_SPI_CTRLA_SWRST;
    while (spi.CTRLA.bit.SWRST || spi.SYNCBUSY.bit.SWRST) {}
    // Mode 0, MSB first, eight bits, hardware chip select. Report overflow at once.
    spi.CTRLA.reg = SERCOM_SPI_CTRLA_MODE_SPI_SLAVE | SERCOM_SPI_CTRLA_DIPO(0) |
                   SERCOM_SPI_CTRLA_DOPO(2) | SERCOM_SPI_CTRLA_IBON;
    spi.CTRLB.reg = SERCOM_SPI_CTRLB_RXEN | SERCOM_SPI_CTRLB_PLOADEN | SERCOM_SPI_CTRLB_SSDE;
    while (spi.SYNCBUSY.bit.CTRLB) {}
    pinPeripheral(CS_PIN, PIO_SERCOM);
    spi.CTRLA.bit.ENABLE = 1;
    while (spi.SYNCBUSY.bit.ENABLE) {}
}

static bool waitForDataRegister(const char *error) {
    const uint32_t start = millis();
    while (!spi.INTFLAG.bit.DRE) {
        if (millis() - start >= 100) {
            Serial.println(error);
            return false;
        }
    }
    return true;
}

static bool prepareByte() {
    if (!waitForDataRegister("ERROR spi_data_register_busy")) return false;
    spi.INTFLAG.reg = FRAME_FLAGS;
    reply = static_cast<uint8_t>(sequenceNumber) ^ 0xA5;
    spi.DATA.reg = reply;
    // With SS high, PLOADEN moves the byte to the shifter before READY rises.
    if (!waitForDataRegister("ERROR spi_preload_timeout")) return false;
    armed = true;
    digitalWrite(READY_PIN, HIGH);
    return true;
}

static void armBatch() {
    digitalWrite(READY_PIN, LOW);
    armed = pendingRearm = false;
    // Check the physical idle level as GPIO before SERCOM takes over the pin.
    pinMode(CS_PIN, INPUT_PULLUP);
    delayMicroseconds(2);
    if (digitalRead(CS_PIN) == LOW) {
        Serial.println("ERROR cs_active_reset_fpga_first");
        return;
    }
    resetSpi();
    sequenceNumber = failures = 0;
    if (prepareByte()) Serial.println("ARMED 256 MODE0 MSB");
}

static void reportFrame() {
    digitalWrite(READY_PIN, LOW);
    armed = false;
    const bool overflow = spi.STATUS.bit.BUFOVF;
    uint8_t received = 0, count = 0;
    while (spi.INTFLAG.bit.RXC) {
        const uint8_t byte = spi.DATA.reg;
        if (count++ == 0) received = byte;
    }
    const bool validLength = !overflow && count == 1;
    const bool ok = validLength && received == static_cast<uint8_t>(sequenceNumber);
    if (!ok) ++failures;
    Serial.print("RX "); Serial.print(sequenceNumber);
    Serial.print(' '); Serial.print(received);
    Serial.print(' '); Serial.print(reply);
    Serial.print(' '); Serial.print(count);
    Serial.print(' '); Serial.println(ok ? 1 : 0);
    if (++sequenceNumber == 256) {
        Serial.print("DONE 256 "); Serial.println(failures);
    } else if (validLength) {
        endedAt = millis();
        pendingRearm = true;
    }
}

void setup() {
    pinMode(READY_PIN, OUTPUT);
    digitalWrite(READY_PIN, LOW);
    pinMode(CS_PIN, INPUT_PULLUP);
    pinMode(MOSI_PIN, INPUT);
    pinMode(MISO_PIN, INPUT);
    pinMode(SCK_PIN, INPUT);
    pinPeripheral(MOSI_PIN, PIO_SERCOM);
    pinPeripheral(MISO_PIN, PIO_SERCOM);
    pinPeripheral(SCK_PIN, PIO_SERCOM);

    PM->APBCMASK.reg |= PM_APBCMASK_SERCOM1;
    GCLK->CLKCTRL.reg = GCLK_CLKCTRL_ID_SERCOM1_CORE | GCLK_CLKCTRL_GEN_GCLK0 | GCLK_CLKCTRL_CLKEN;
    while (GCLK->STATUS.bit.SYNCBUSY) {}
    Serial.begin(115200);
}

void loop() {
    while (Serial.available()) {
        const char c = Serial.read();
        if (c == '\r') continue;
        if (c == '\n') {
            command[commandLength] = '\0';
            if (commandTooLong) Serial.println("ERROR command_too_long");
            else if (!strcmp(command, "ARM")) armBatch();
            else if (!strcmp(command, "PING")) Serial.println("PIO_SPI_NANO_V1");
            else Serial.println("ERROR unknown_command");
            commandLength = 0;
            commandTooLong = false;
        } else if (commandLength < sizeof(command) - 1) {
            command[commandLength++] = c;
        } else {
            commandTooLong = true;
        }
    }

    // SSL proves selection happened. TXC records the end when SS rises.
    if (armed && (spi.INTFLAG.reg & FRAME_FLAGS) == FRAME_FLAGS) reportFrame();
    // A valid TXC already observed SS rising. The host waits for READY.
    if (pendingRearm && millis() - endedAt >= 5) {
        pendingRearm = false;
        prepareByte();
    }
}
