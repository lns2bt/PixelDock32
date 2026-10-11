#include <cassert>
#include <iostream>
#include "../../arduino/PixelDockUnoR3/PixelDockUnoR3.ino"

std::vector<uint8_t> packet(uint8_t cmd, const std::vector<uint8_t> &payload) {
  std::vector<uint8_t> result = {'P', 'D', cmd, uint8_t(payload.size()), uint8_t(payload.size() >> 8)};
  result.insert(result.end(), payload.begin(), payload.end());
  uint8_t checksum = 0;
  for (auto b : result) checksum ^= b;
  result.push_back(checksum);
  return result;
}

void feed(const std::vector<uint8_t> &bytes) {
  Serial.input.insert(Serial.input.end(), bytes.begin(), bytes.end());
  Serial.output.clear();
  events.clear();
  loop();
}

int main() {
  setup();
  std::vector<uint8_t> frame(770, 255);
  frame[0] = 123;
  frame[1] = 0;
  frame[2] = 200; // R
  frame[3] = 100; // G
  frame[4] = 0;   // B
  feed(packet(CMD_FRAME_V2, frame));
  assert(frameBufferValid);
  assert(Serial.output == packet(CMD_FRAME_ACK, {123, 0}));
  assert(events.front() == 1); // show before ACK writes
  assert(strip.pixels[0] == 25); // scaled G in the GRB buffer
  assert(strip.pixels[1] == 50); // scaled R
  assert(strip.pixels[2] == 0);  // B

  auto corrupt = packet(CMD_FRAME_V2, frame);
  corrupt.back() ^= 1;
  int shows = strip.shows;
  feed(corrupt);
  assert(strip.shows == shows);
  assert(!frameBufferValid);
  assert(Serial.output.empty());
  feed(packet(CMD_BRIGHTNESS_V3, {100}));
  assert(strip.shows == shows); // corrupt pixels must never become visible
  assert(Serial.output == packet(CMD_BRIGHTNESS_ACK, {100}));

  feed(packet(CMD_FRAME_V2, frame));
  assert(frameBufferValid);
  assert(strip.shows == shows + 1);
  feed(packet(CMD_BRIGHTNESS_V3, {120}));
  assert(events.front() == 1);
  assert(Serial.output == packet(CMD_BRIGHTNESS_ACK, {120}));

  auto partial = packet(CMD_FRAME_V2, frame);
  partial.resize(20);
  feed(partial);
  fakeMillis += 100;
  feed({});
  assert(state == RxState::WAIT_MAGIC_0);
  assert(!frameBufferValid);
  shows = strip.shows;
  feed(packet(CMD_BRIGHTNESS, {80}));
  assert(strip.shows == shows); // legacy brightness also cannot expose partial frame
  feed(packet(CMD_FRAME_V2, frame));
  assert(frameBufferValid);
  assert(Serial.output == packet(CMD_FRAME_ACK, {123, 0}));

  feed(packet(CMD_DEBUG_SNAPSHOT, {}));
  assert(Serial.output[5] == 3);
  std::cout << "firmware-parser-ok\n";
}
