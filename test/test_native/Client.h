#pragma once

#include <cstddef>
#include <cstdint>

#include <Arduino.h>

class Client : public Stream {
 public:
  virtual ~Client() = default;
  virtual int connect(const char* host, uint16_t port) = 0;
  virtual std::size_t write(const uint8_t* data, std::size_t size) = 0;
  virtual int available() = 0;
  virtual int read() = 0;
  virtual void stop() = 0;
  virtual uint8_t connected() = 0;
};
