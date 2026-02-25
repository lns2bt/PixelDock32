#include <Adafruit_NeoPixel.h>
#include <string.h>

// PixelDock32 serial protocol for Arduino UNO R3 (USB CDC)
// Frame: ['P','D', CMD, LEN_LO, LEN_HI, PAYLOAD..., XOR_CHECKSUM]
// CMD=0x01 => full RGB frame payload (3 * LED_COUNT bytes)
// CMD=0x02 => brightness payload (1 byte 0..255)
// CMD=0x03 => ping payload (4-byte nonce), reply CMD=0x83

constexpr uint8_t PIN_NEOPIXEL = 6;
constexpr uint16_t LED_COUNT = 256;
constexpr uint32_t SERIAL_BAUDRATE = 1000000;

constexpr uint16_t FRAME_PAYLOAD = LED_COUNT * 3;
constexpr uint8_t CMD_FRAME = 0x01;
constexpr uint8_t CMD_BRIGHTNESS = 0x02;
constexpr uint8_t CMD_PING = 0x03;
constexpr uint8_t CMD_PING_ACK = 0x83;
constexpr uint8_t CMD_DEBUG_SNAPSHOT = 0x04;
constexpr uint8_t CMD_DEBUG_SNAPSHOT_ACK = 0x84;
constexpr uint8_t MAGIC_0 = 'P';
constexpr uint8_t MAGIC_1 = 'D';
constexpr uint8_t DEBUG_PROTOCOL_VERSION = 1;

// Prevent parser lock on partial packets.
constexpr uint32_t RX_PACKET_TIMEOUT_MS = 40;

Adafruit_NeoPixel strip(LED_COUNT, PIN_NEOPIXEL, NEO_GRB + NEO_KHZ800);
uint8_t *stripPixels = nullptr;

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

// Small payload buffer for non-frame commands only.
uint8_t payloadSmall[4] = {0, 0, 0, 0};

// Streaming helpers for CMD_FRAME (avoid extra 768B frame buffer in SRAM).
uint8_t rgbScratch[3] = {0, 0, 0};
uint8_t rgbScratchLen = 0;
uint16_t frameLedIndex = 0;
uint8_t frameBrightness = 64;

uint32_t lastRxByteAtMs = 0;

struct DebugStats {
  uint32_t packetsOk = 0;
  uint32_t framePackets = 0;
  uint32_t brightnessPackets = 0;
  uint32_t pingPackets = 0;
  uint32_t debugPackets = 0;
  uint16_t checksumErrors = 0;
  uint16_t invalidPackets = 0;
  uint16_t packetTimeouts = 0;
  uint8_t lastCommand = 0;
};

DebugStats debugStats;

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
  rgbScratchLen = 0;
  frameLedIndex = 0;
}

void resetRxWithTimeout() {
  debugStats.packetTimeouts++;
  resetRx();
}

void sendDebugSnapshot() {
  uint8_t payload[33] = {0};
  uint8_t i = 0;

  payload[i++] = DEBUG_PROTOCOL_VERSION;

  const uint32_t uptime = millis();
  memcpy(&payload[i], &uptime, sizeof(uptime));
  i += sizeof(uptime);

  memcpy(&payload[i], &debugStats.packetsOk, sizeof(debugStats.packetsOk));
  i += sizeof(debugStats.packetsOk);
  memcpy(&payload[i], &debugStats.framePackets, sizeof(debugStats.framePackets));
  i += sizeof(debugStats.framePackets);
  memcpy(&payload[i], &debugStats.brightnessPackets, sizeof(debugStats.brightnessPackets));
  i += sizeof(debugStats.brightnessPackets);
  memcpy(&payload[i], &debugStats.pingPackets, sizeof(debugStats.pingPackets));
  i += sizeof(debugStats.pingPackets);
  memcpy(&payload[i], &debugStats.debugPackets, sizeof(debugStats.debugPackets));
  i += sizeof(debugStats.debugPackets);
  memcpy(&payload[i], &debugStats.checksumErrors, sizeof(debugStats.checksumErrors));
  i += sizeof(debugStats.checksumErrors);
  memcpy(&payload[i], &debugStats.invalidPackets, sizeof(debugStats.invalidPackets));
  i += sizeof(debugStats.invalidPackets);
  memcpy(&payload[i], &debugStats.packetTimeouts, sizeof(debugStats.packetTimeouts));
  i += sizeof(debugStats.packetTimeouts);

  payload[i++] = debugStats.lastCommand;
  payload[i++] = strip.getBrightness();

  sendPacket(CMD_DEBUG_SNAPSHOT_ACK, payload, sizeof(payload));
}

bool commandAndLengthValid(uint8_t cmd, uint16_t len) {
  if (cmd == CMD_FRAME) {
    return len == FRAME_PAYLOAD;
  }
  if (cmd == CMD_BRIGHTNESS) {
    return len == 1;
  }
  if (cmd == CMD_PING) {
    return len == 4;
  }
  if (cmd == CMD_DEBUG_SNAPSHOT) {
    return len == 0;
  }
  return false;
}

void applyBrightness(uint8_t value) {
  strip.setBrightness(value);
  strip.show();
}

uint8_t scaleChannelForBrightness(uint8_t value, uint8_t brightness) {
  if (brightness >= 255) {
    return value;
  }
  if (brightness == 0) {
    return 0;
  }
  const uint16_t scale = static_cast<uint16_t>(brightness) + 1;
  return static_cast<uint8_t>((static_cast<uint16_t>(value) * scale) >> 8);
}

void onFramePayloadByte(uint8_t value) {
  rgbScratch[rgbScratchLen++] = value;
  if (rgbScratchLen < 3) {
    return;
  }

  uint8_t r = rgbScratch[0];
  uint8_t g = rgbScratch[1];
  uint8_t b = rgbScratch[2];

  if (frameBrightness != 255) {
    r = scaleChannelForBrightness(r, frameBrightness);
    g = scaleChannelForBrightness(g, frameBrightness);
    b = scaleChannelForBrightness(b, frameBrightness);
  }

  if (stripPixels != nullptr) {
    const uint16_t offset = frameLedIndex * 3;
    // NEO_GRB buffer layout for the configured strip type.
    stripPixels[offset + 0] = g;
    stripPixels[offset + 1] = r;
    stripPixels[offset + 2] = b;
  } else {
    strip.setPixelColor(frameLedIndex, strip.Color(r, g, b));
  }
  frameLedIndex++;
  rgbScratchLen = 0;
}

void setup() {
  Serial.begin(SERIAL_BAUDRATE);
  strip.begin();
  strip.setBrightness(64);
  stripPixels = strip.getPixels();
  strip.show();
}

void loop() {
  const uint32_t now = millis();
  if (state != RxState::WAIT_MAGIC_0 && (now - lastRxByteAtMs) > RX_PACKET_TIMEOUT_MS) {
    resetRxWithTimeout();
  }

  while (Serial.available() > 0) {
    const uint8_t b = static_cast<uint8_t>(Serial.read());
    lastRxByteAtMs = millis();

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

        if (!commandAndLengthValid(command, payloadLen)) {
          debugStats.invalidPackets++;
          resetRx();
        } else if (payloadLen == 0) {
          state = RxState::WAIT_CHECKSUM;
        } else {
          if (command == CMD_FRAME) {
            frameBrightness = strip.getBrightness();
          }
          state = RxState::WAIT_PAYLOAD;
        }
        break;

      case RxState::WAIT_PAYLOAD:
        if (command == CMD_FRAME) {
          onFramePayloadByte(b);
        } else if (payloadIndex < sizeof(payloadSmall)) {
          payloadSmall[payloadIndex] = b;
        }

        payloadIndex++;
        checksum ^= b;
        if (payloadIndex >= payloadLen) {
          state = RxState::WAIT_CHECKSUM;
        }
        break;

      case RxState::WAIT_CHECKSUM:
        if (checksum == b) {
          debugStats.packetsOk++;
          debugStats.lastCommand = command;
          if (command == CMD_BRIGHTNESS) {
            debugStats.brightnessPackets++;
            applyBrightness(payloadSmall[0]);
          } else if (command == CMD_FRAME) {
            debugStats.framePackets++;
            strip.show();
          } else if (command == CMD_PING) {
            debugStats.pingPackets++;
            sendPacket(CMD_PING_ACK, payloadSmall, 4);
          } else if (command == CMD_DEBUG_SNAPSHOT) {
            debugStats.debugPackets++;
            sendDebugSnapshot();
          }
        } else {
          debugStats.checksumErrors++;
        }
        resetRx();
        break;
    }
  }
}
