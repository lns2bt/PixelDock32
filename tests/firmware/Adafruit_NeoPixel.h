#pragma once
#include <cstdint>
#include <deque>
#include <vector>

// Host-only replacements: validate parser logic, not AVR or electrical timing.
constexpr int NEO_GRB = 1;
constexpr int NEO_KHZ800 = 2;
inline uint32_t fakeMillis = 0;
inline uint32_t millis() { return fakeMillis; }
inline std::vector<int> events;

struct FakeSerial {
  std::deque<uint8_t> input;
  std::vector<uint8_t> output;
  void begin(uint32_t) {}
  int available() { return input.size(); }
  int read() { auto b = input.front(); input.pop_front(); return b; }
  void write(const uint8_t *data, uint16_t len) {
    events.push_back(2);
    output.insert(output.end(), data, data + len);
  }
  void write(uint8_t b) { events.push_back(2); output.push_back(b); }
};
inline FakeSerial Serial;

class Adafruit_NeoPixel {
 public:
  std::vector<uint8_t> pixels;
  uint8_t brightness = 64;
  int shows = 0;
  Adafruit_NeoPixel(uint16_t count, uint8_t, int) : pixels(count * 3) {}
  void begin() {}
  void setBrightness(uint8_t value) { brightness = value; }
  uint8_t getBrightness() { return brightness; }
  uint8_t *getPixels() { return pixels.data(); }
  uint32_t Color(uint8_t r, uint8_t g, uint8_t b) {
    return (uint32_t(r) << 16) | (uint32_t(g) << 8) | b;
  }
  void setPixelColor(uint16_t index, uint32_t rgb) {
    pixels[index * 3] = (rgb >> 8) & 255;
    pixels[index * 3 + 1] = (rgb >> 16) & 255;
    pixels[index * 3 + 2] = rgb & 255;
  }
  void show() { events.push_back(1); ++shows; }
};
