#pragma once

#include <Arduino.h>
#include <Client.h>

#include <functional>
#include <vector>

enum class OpenNetFrameKind : uint8_t {
  Data = 1,
  Ack = 2,
  Ping = 3,
  Pong = 4,
  Close = 5,
  Error = 6,
};

enum class OpenNetValueType : uint8_t {
  Bytes = 0,
  Utf8 = 1,
  Json = 2,
  Int64 = 3,
  Float64 = 4,
  Bool = 5,
  Null = 6,
};

static_assert(sizeof(OpenNetFrameKind) == sizeof(uint8_t),
              "OpenNet frame kinds must remain one byte");
static_assert(sizeof(OpenNetValueType) == sizeof(uint8_t),
              "OpenNet value types must remain one byte");

struct OpenNetMessage {
  OpenNetFrameKind kind;
  OpenNetValueType valueType;
  String topic;
  std::vector<uint8_t> payload;
  uint32_t messageId;
  uint8_t flags;

  String text() const;
  bool asInt(int64_t& value) const;
  bool asDouble(double& value) const;
  bool asBool(bool& value) const;
  bool isNull() const;
};

enum class OpenNetError : uint8_t {
  None,
  NotConnected,
  InvalidArgument,
  TopicTooLong,
  PayloadTooLarge,
  TransportWrite,
  InvalidFrame,
  ChecksumMismatch,
};

static_assert(sizeof(OpenNetError) == sizeof(uint8_t),
              "OpenNet errors must remain one byte");

class OpenNetClient {
 public:
  using MessageHandler = std::function<void(const OpenNetMessage&)>;

  static constexpr uint32_t kDefaultMaxPayload = 4096;
  static constexpr uint16_t kMaxTopicLength = 1024;

  explicit OpenNetClient(Client& transport,
                         uint32_t maxPayload = kDefaultMaxPayload);
  explicit OpenNetClient(Stream& transport,
                         uint32_t maxPayload = kDefaultMaxPayload);

  // Stream transports such as Serial and BluetoothSerial are opened by their
  // caller; connect() is available for Client transports such as WiFiClient.
  bool connect(const char* host, uint16_t port);
  void disconnect(const char* reason = nullptr);
  bool connected() const;
  void poll();

  void onMessage(MessageHandler handler);
  OpenNetError lastError() const;
  uint32_t lastAcknowledgedMessage() const;
  bool acknowledged(uint32_t messageId) const;

  uint32_t send(const char* topic, OpenNetValueType type,
                const uint8_t* payload, size_t length,
                bool requireAck = true);
  uint32_t sendText(const char* topic, const String& value,
                    bool requireAck = true);
  uint32_t sendJson(const char* topic, const String& json,
                    bool requireAck = true);
  uint32_t sendBinary(const char* topic, const uint8_t* value, size_t length,
                      bool requireAck = true);
  uint32_t sendInt(const char* topic, int64_t value, bool requireAck = true);
  uint32_t sendDouble(const char* topic, double value,
                      bool requireAck = true);
  uint32_t sendBool(const char* topic, bool value, bool requireAck = true);
  uint32_t sendNull(const char* topic, bool requireAck = true);
  bool ping();

 private:
  static constexpr size_t kHeaderSize = 24;
  static constexpr uint8_t kAckRequired = 0x01;
  static constexpr uint8_t kAllowedFlags = 0x03;

  Stream& transport_;
  Client* clientTransport_;
  uint32_t maxPayload_;
  uint32_t nextMessageId_;
  uint32_t lastAcknowledged_;
  OpenNetError lastError_;
  MessageHandler handler_;

  uint8_t header_[kHeaderSize];
  size_t headerReceived_;
  std::vector<uint8_t> body_;
  size_t bodyReceived_;
  uint16_t expectedTopicLength_;
  uint32_t expectedPayloadLength_;

  bool sendFrame(OpenNetFrameKind kind, OpenNetValueType type,
                 const char* topic, const uint8_t* payload, size_t length,
                 uint32_t messageId, uint8_t flags);
  bool writeAll(const uint8_t* data, size_t length);
  void stopTransport();
  void resetReceiver();
  bool prepareBody();
  void handleFrame();

  static uint16_t readU16(const uint8_t* bytes);
  static uint32_t readU32(const uint8_t* bytes);
  static void writeU16(uint8_t* bytes, uint16_t value);
  static void writeU32(uint8_t* bytes, uint32_t value);
  static uint32_t crc32(const uint8_t* data, size_t length,
                        uint32_t previous = 0);
};

const char* openNetErrorName(OpenNetError error);
