#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

inline unsigned long& fakeArduinoMillis() {
  static unsigned long value = 0;
  return value;
}

inline unsigned long millis() { return fakeArduinoMillis(); }
inline void yield() { ++fakeArduinoMillis(); }

class Stream {
 public:
  virtual ~Stream() = default;
  virtual std::size_t write(const uint8_t* data, std::size_t size) = 0;
  virtual int available() = 0;
  virtual int read() = 0;
};

class String {
 public:
  String() = default;
  String(const char* value) : value_(value == nullptr ? "" : value) {}

  void reserve(std::size_t size) { value_.reserve(size); }
  String& operator+=(char value) {
    value_ += value;
    return *this;
  }
  const char* c_str() const { return value_.c_str(); }
  std::size_t length() const { return value_.length(); }

 private:
  std::string value_;
};
