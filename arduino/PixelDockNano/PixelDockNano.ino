#include <Adafruit_NeoPixel.h>

// PixelDock32 serial protocol (USB CDC)
// Frame: ['P','D', CMD, LEN_LO, LEN_HI, PAYLOAD..., XOR_CHECKSUM]
// CMD=0x01 => full RGB frame payload (3 * LED_COUNT bytes)
// CMD=0x02 => brightness payload (1 byte 0..255)

constexpr uint8_t PIN_NEOPIXEL = 6;
constexpr uint16_t LED_COUNT = 256;
constexpr uint16_t MAX_PAYLOAD = LED_COUNT * 3;
constexpr uint8_t CMD_FRAME = 0x01;
constexpr uint8_t CMD_BRIGHTNESS = 0x02;
constexpr uint8_t CMD_PING = 0x03;
constexpr uint8_t CMD_PING_ACK = 0x83;
constexpr uint8_t MAGIC_0 = 'P';
constexpr uint8_t MAGIC_1 = 'D';

Adafruit_NeoPixel strip(LED_COUNT, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);

enum class RxState : uint8_t {
  WAIT_MAGIC_0,
  WAIT_MAGIC_1,
  WAIT_CMD,
  WAIT_LEN_LO,
  WAIT_LEN_HI,
  WAIT_PAYLOAD,
  WAIT_CHECKSUM,
};

RxState state = RxState::WAIT_MAGIC_0;
uint8_t command = 0;
uint16_t payloadLen = 0;
uint16_t payloadIndex = 0;
uint8_t checksum = 0;
uint8_t payload[MAX_PAYLOAD];


uint8_t computeChecksum(const uint8_t *buf, uint16_t len) {
  uint8_t value = 0;
  for (uint16_t i = 0; i < len; i++) {
    value ^= buf[i];
  }
  return value;
}

void sendPacket(uint8_t cmd, const uint8_t *buf, uint16_t len) {
  uint8_t header[5] = {MAGIC_0, MAGIC_1, cmd, static_cast<uint8_t>(len & 0xFF), static_cast<uint8_t>((len >> 8) & 0xFF)};
  uint8_t cs = computeChecksum(header, sizeof(header));
  Serial.write(header, sizeof(header));
  if (len > 0 && buf != nullptr) {
    Serial.write(buf, len);
    for (uint16_t i = 0; i < len; i++) {
      cs ^= buf[i];
    }
  }
  Serial.write(cs);
}

void resetRx() {
  state = RxState::WAIT_MAGIC_0;
  command = 0;
  payloadLen = 0;
  payloadIndex = 0;
  checksum = 0;
}

void applyBrightness(uint8_t value) {
  strip.setBrightness(value);
  strip.show();
}

void applyFrame(const uint8_t *buf, uint16_t len) {
  if (len != LED_COUNT * 3) {
    return;
  }

  for (uint16_t i = 0; i < LED_COUNT; i++) {
    const uint16_t off = i * 3;
    const uint8_t r = buf[off + 0];
    const uint8_t g = buf[off + 1];
    const uint8_t b = buf[off + 2];
    strip.setPixelColor(i, strip.Color(r, g, b));
  }
  strip.show();
}

void setup() {
  Serial.begin(1000000);
  strip.begin();
  strip.setBrightness(64);
  strip.show();
}

void loop() {
  while (Serial.available() > 0) {
    const uint8_t b = static_cast<uint8_t>(Serial.read());

    switch (state) {
      case RxState::WAIT_MAGIC_0:
        if (b == MAGIC_0) {
          checksum = b;
          state = RxState::WAIT_MAGIC_1;
        }
        break;

      case RxState::WAIT_MAGIC_1:
        if (b == MAGIC_1) {
          checksum ^= b;
          state = RxState::WAIT_CMD;
        } else {
          resetRx();
        }
        break;

      case RxState::WAIT_CMD:
        command = b;
        checksum ^= b;
        state = RxState::WAIT_LEN_LO;
        break;

      case RxState::WAIT_LEN_LO:
        payloadLen = b;
        checksum ^= b;
        state = RxState::WAIT_LEN_HI;
        break;

      case RxState::WAIT_LEN_HI:
        payloadLen |= static_cast<uint16_t>(b) << 8;
        payloadIndex = 0;
        checksum ^= b;
        if (payloadLen > MAX_PAYLOAD) {
          resetRx();
        } else if (payloadLen == 0) {
          state = RxState::WAIT_CHECKSUM;
        } else {
          state = RxState::WAIT_PAYLOAD;
        }
        break;

      case RxState::WAIT_PAYLOAD:
        payload[payloadIndex++] = b;
        checksum ^= b;
        if (payloadIndex >= payloadLen) {
          state = RxState::WAIT_CHECKSUM;
        }
        break;

      case RxState::WAIT_CHECKSUM:
        if (checksum == b) {
          if (command == CMD_BRIGHTNESS && payloadLen == 1) {
            applyBrightness(payload[0]);
          } else if (command == CMD_FRAME) {
            applyFrame(payload, payloadLen);
          } else if (command == CMD_PING && payloadLen == 4) {
            sendPacket(CMD_PING_ACK, payload, payloadLen);
          }
        }
        resetRx();
        break;
    }
  }
}
