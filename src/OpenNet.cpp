#include "OpenNet.h"

#include <cmath>
#include <cstring>
#include <utility>

String OpenNetMessage::text() const {
  if (valueType != OpenNetValueType::Utf8 &&
      valueType != OpenNetValueType::Json) {
    return String();
  }
  String result;
  result.reserve(payload.size());
  for (uint8_t byte : payload) {
    result += static_cast<char>(byte);
  }
  return result;
}

bool OpenNetMessage::asInt(int64_t& value) const {
  if (valueType != OpenNetValueType::Int64 || payload.size() != 8) {
    return false;
  }
  uint64_t bits = 0;
  for (uint8_t byte : payload) {
    bits = (bits << 8) | byte;
  }
  memcpy(&value, &bits, sizeof(value));
  return true;
}

bool OpenNetMessage::asDouble(double& value) const {
  if (valueType != OpenNetValueType::Float64 || payload.size() != 8) {
    return false;
  }
  uint64_t bits = 0;
  for (uint8_t byte : payload) {
    bits = (bits << 8) | byte;
  }
  memcpy(&value, &bits, sizeof(value));
  return std::isfinite(value);
}

bool OpenNetMessage::asBool(bool& value) const {
  if (valueType != OpenNetValueType::Bool || payload.size() != 1 ||
      payload[0] > 1) {
    return false;
  }
  value = payload[0] == 1;
  return true;
}

bool OpenNetMessage::isNull() const {
  return valueType == OpenNetValueType::Null && payload.empty();
}

OpenNetClient::OpenNetClient(Stream& transport, uint32_t maxPayload)
    : transport_(transport),
      clientTransport_(nullptr),
      maxPayload_(maxPayload),
      nextMessageId_(1),
      lastAcknowledged_(0),
      lastError_(OpenNetError::None),
      headerReceived_(0),
      bodyReceived_(0),
      expectedTopicLength_(0),
      expectedPayloadLength_(0) {}

OpenNetClient::OpenNetClient(Client& transport, uint32_t maxPayload)
    : OpenNetClient(static_cast<Stream&>(transport), maxPayload) {
  clientTransport_ = &transport;
}

bool OpenNetClient::connect(const char* host, uint16_t port) {
  if (clientTransport_ == nullptr || host == nullptr || host[0] == '\0' ||
      port == 0) {
    lastError_ = OpenNetError::InvalidArgument;
    return false;
  }
  resetReceiver();
  if (!clientTransport_->connect(host, port)) {
    lastError_ = OpenNetError::NotConnected;
    return false;
  }
  lastError_ = OpenNetError::None;
  return true;
}

void OpenNetClient::disconnect(const char* reason) {
  if (connected()) {
    const uint8_t* bytes = reinterpret_cast<const uint8_t*>(reason);
    const size_t length = reason == nullptr ? 0 : strlen(reason);
    sendFrame(OpenNetFrameKind::Close, OpenNetValueType::Utf8, "", bytes,
              length, 0, 0);
  }
  stopTransport();
  resetReceiver();
}

bool OpenNetClient::connected() const {
  return clientTransport_ == nullptr || clientTransport_->connected();
}

void OpenNetClient::poll() {
  if (!connected()) {
    return;
  }

  while (transport_.available() > 0) {
    if (headerReceived_ < kHeaderSize) {
      const int byte = transport_.read();
      if (byte < 0) {
        return;
      }
      header_[headerReceived_++] = static_cast<uint8_t>(byte);
      if (headerReceived_ == kHeaderSize && !prepareBody()) {
        stopTransport();
        resetReceiver();
        return;
      }
    } else {
      const size_t total =
          static_cast<size_t>(expectedTopicLength_) + expectedPayloadLength_;
      while (bodyReceived_ < total && transport_.available() > 0) {
        const int byte = transport_.read();
        if (byte < 0) {
          return;
        }
        body_[bodyReceived_++] = static_cast<uint8_t>(byte);
      }
      if (bodyReceived_ == total) {
        handleFrame();
        resetReceiver();
      }
    }
  }
}

void OpenNetClient::onMessage(MessageHandler handler) {
  handler_ = std::move(handler);
}

OpenNetError OpenNetClient::lastError() const { return lastError_; }

uint32_t OpenNetClient::lastAcknowledgedMessage() const {
  return lastAcknowledged_;
}

bool OpenNetClient::acknowledged(uint32_t messageId) const {
  return messageId != 0 && lastAcknowledged_ == messageId;
}

uint32_t OpenNetClient::send(const char* topic, OpenNetValueType type,
                             const uint8_t* payload, size_t length,
                             bool requireAck) {
  if (!connected()) {
    lastError_ = OpenNetError::NotConnected;
    return 0;
  }
  if (topic == nullptr || topic[0] == '\0' ||
      (payload == nullptr && length != 0)) {
    lastError_ = OpenNetError::InvalidArgument;
    return 0;
  }
  const uint32_t id = nextMessageId_;
  nextMessageId_ = id == UINT32_MAX ? 1 : id + 1;
  if (!sendFrame(OpenNetFrameKind::Data, type, topic, payload, length, id,
                 requireAck ? kAckRequired : 0)) {
    return 0;
  }
  return id;
}

uint32_t OpenNetClient::sendText(const char* topic, const String& value,
                                 bool requireAck) {
  return send(topic, OpenNetValueType::Utf8,
              reinterpret_cast<const uint8_t*>(value.c_str()), value.length(),
              requireAck);
}

uint32_t OpenNetClient::sendJson(const char* topic, const String& json,
                                 bool requireAck) {
  return send(topic, OpenNetValueType::Json,
              reinterpret_cast<const uint8_t*>(json.c_str()), json.length(),
              requireAck);
}

uint32_t OpenNetClient::sendBinary(const char* topic, const uint8_t* value,
                                   size_t length, bool requireAck) {
  return send(topic, OpenNetValueType::Bytes, value, length, requireAck);
}

uint32_t OpenNetClient::sendInt(const char* topic, int64_t value,
                                bool requireAck) {
  uint8_t bytes[8];
  const uint64_t bits = static_cast<uint64_t>(value);
  for (size_t i = 0; i < sizeof(bytes); ++i) {
    bytes[i] = static_cast<uint8_t>(bits >> (56 - 8 * i));
  }
  return send(topic, OpenNetValueType::Int64, bytes, sizeof(bytes), requireAck);
}

uint32_t OpenNetClient::sendDouble(const char* topic, double value,
                                   bool requireAck) {
  if (!std::isfinite(value)) {
    lastError_ = OpenNetError::InvalidArgument;
    return 0;
  }
  static_assert(sizeof(double) == sizeof(uint64_t),
                "OpenNet requires an IEEE-754 64-bit double");
  uint64_t bits;
  memcpy(&bits, &value, sizeof(bits));
  uint8_t bytes[8];
  for (size_t i = 0; i < sizeof(bytes); ++i) {
    bytes[i] = static_cast<uint8_t>(bits >> (56 - 8 * i));
  }
  return send(topic, OpenNetValueType::Float64, bytes, sizeof(bytes),
              requireAck);
}

uint32_t OpenNetClient::sendBool(const char* topic, bool value,
                                 bool requireAck) {
  const uint8_t byte = value ? 1 : 0;
  return send(topic, OpenNetValueType::Bool, &byte, 1, requireAck);
}

uint32_t OpenNetClient::sendNull(const char* topic, bool requireAck) {
  return send(topic, OpenNetValueType::Null, nullptr, 0, requireAck);
}

bool OpenNetClient::ping() {
  return sendFrame(OpenNetFrameKind::Ping, OpenNetValueType::Null, "", nullptr,
                   0, 0, 0);
}

bool OpenNetClient::sendFrame(OpenNetFrameKind kind, OpenNetValueType type,
                              const char* topic, const uint8_t* payload,
                              size_t length, uint32_t messageId,
                              uint8_t flags) {
  if (!connected()) {
    lastError_ = OpenNetError::NotConnected;
    return false;
  }
  const char* safeTopic = topic == nullptr ? "" : topic;
  const size_t topicLength = strlen(safeTopic);
  if (topicLength > kMaxTopicLength || topicLength > UINT16_MAX) {
    lastError_ = OpenNetError::TopicTooLong;
    return false;
  }
  if (length > maxPayload_ || length > UINT32_MAX) {
    lastError_ = OpenNetError::PayloadTooLarge;
    return false;
  }

  uint8_t header[kHeaderSize] = {};
  header[0] = 'O';
  header[1] = 'N';
  header[2] = 1;
  header[3] = static_cast<uint8_t>(kind);
  header[4] = flags;
  header[5] = static_cast<uint8_t>(type);
  writeU16(header + 6, static_cast<uint16_t>(topicLength));
  writeU32(header + 8, messageId);
  writeU32(header + 12, static_cast<uint32_t>(length));
  uint32_t checksum =
      crc32(reinterpret_cast<const uint8_t*>(safeTopic), topicLength);
  checksum = crc32(payload, length, checksum);
  writeU32(header + 16, checksum);

  if (!writeAll(header, kHeaderSize) ||
      !writeAll(reinterpret_cast<const uint8_t*>(safeTopic), topicLength) ||
      !writeAll(payload, length)) {
    lastError_ = OpenNetError::TransportWrite;
    return false;
  }
  lastError_ = OpenNetError::None;
  return true;
}

bool OpenNetClient::writeAll(const uint8_t* data, size_t length) {
  size_t offset = 0;
  while (offset < length) {
    const size_t written = transport_.write(data + offset, length - offset);
    if (written == 0 || written > length - offset) {
      return false;
    }
    offset += written;
  }
  return true;
}

void OpenNetClient::stopTransport() {
  if (clientTransport_ != nullptr) {
    clientTransport_->stop();
  }
}

void OpenNetClient::resetReceiver() {
  headerReceived_ = 0;
  body_.clear();
  bodyReceived_ = 0;
  expectedTopicLength_ = 0;
  expectedPayloadLength_ = 0;
}

bool OpenNetClient::prepareBody() {
  if (header_[0] != 'O' || header_[1] != 'N' || header_[2] != 1 ||
      header_[3] < static_cast<uint8_t>(OpenNetFrameKind::Data) ||
      header_[3] > static_cast<uint8_t>(OpenNetFrameKind::Error) ||
      header_[5] > static_cast<uint8_t>(OpenNetValueType::Null) ||
      (header_[4] & ~kAllowedFlags) != 0) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  expectedTopicLength_ = readU16(header_ + 6);
  expectedPayloadLength_ = readU32(header_ + 12);
  const auto kind = static_cast<OpenNetFrameKind>(header_[3]);
  const auto valueType = static_cast<OpenNetValueType>(header_[5]);
  const uint32_t messageId = readU32(header_ + 8);
  if (kind == OpenNetFrameKind::Data &&
      (expectedTopicLength_ == 0 || messageId == 0)) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  if (kind != OpenNetFrameKind::Data && expectedTopicLength_ != 0) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  if (kind == OpenNetFrameKind::Ack &&
      (messageId == 0 || expectedPayloadLength_ != 0 ||
       valueType != OpenNetValueType::Null)) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  if ((kind == OpenNetFrameKind::Ping || kind == OpenNetFrameKind::Pong) &&
      (messageId != 0 || expectedPayloadLength_ != 0 ||
       valueType != OpenNetValueType::Null)) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  if ((kind == OpenNetFrameKind::Close || kind == OpenNetFrameKind::Error) &&
      (messageId != 0 ||
       (expectedPayloadLength_ != 0 && valueType != OpenNetValueType::Utf8))) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  if (kind == OpenNetFrameKind::Data &&
      ((valueType == OpenNetValueType::Null && expectedPayloadLength_ != 0) ||
       (valueType == OpenNetValueType::Bool && expectedPayloadLength_ != 1) ||
       ((valueType == OpenNetValueType::Int64 ||
         valueType == OpenNetValueType::Float64) &&
        expectedPayloadLength_ != 8))) {
    lastError_ = OpenNetError::InvalidFrame;
    return false;
  }
  if (expectedTopicLength_ > kMaxTopicLength ||
      expectedPayloadLength_ > maxPayload_) {
    lastError_ = OpenNetError::PayloadTooLarge;
    return false;
  }
  body_.resize(static_cast<size_t>(expectedTopicLength_) +
               expectedPayloadLength_);
  if (body_.empty()) {
    handleFrame();
    resetReceiver();
  }
  return true;
}

void OpenNetClient::handleFrame() {
  const uint32_t expectedChecksum = readU32(header_ + 16);
  const uint8_t* topicBytes = body_.empty() ? nullptr : body_.data();
  const uint8_t* payload =
      body_.empty() ? nullptr : body_.data() + expectedTopicLength_;
  uint32_t actualChecksum = crc32(topicBytes, expectedTopicLength_);
  actualChecksum = crc32(payload, expectedPayloadLength_, actualChecksum);
  if (actualChecksum != expectedChecksum) {
    lastError_ = OpenNetError::ChecksumMismatch;
    stopTransport();
    return;
  }

  const auto kind = static_cast<OpenNetFrameKind>(header_[3]);
  const uint32_t messageId = readU32(header_ + 8);
  if (kind == OpenNetFrameKind::Ack) {
    lastAcknowledged_ = messageId;
    return;
  }
  if (kind == OpenNetFrameKind::Ping) {
    sendFrame(OpenNetFrameKind::Pong, OpenNetValueType::Null, "", nullptr, 0,
              0, 0);
    return;
  }
  if (kind != OpenNetFrameKind::Data) {
    return;
  }
  if (static_cast<OpenNetValueType>(header_[5]) == OpenNetValueType::Bool &&
      payload[0] > 1) {
    lastError_ = OpenNetError::InvalidFrame;
    stopTransport();
    return;
  }

  OpenNetMessage message;
  message.kind = kind;
  message.valueType = static_cast<OpenNetValueType>(header_[5]);
  message.messageId = messageId;
  message.flags = header_[4];
  message.topic.reserve(expectedTopicLength_);
  for (size_t i = 0; i < expectedTopicLength_; ++i) {
    message.topic += static_cast<char>(body_[i]);
  }
  message.payload.assign(payload, payload + expectedPayloadLength_);
  if (message.valueType == OpenNetValueType::Float64) {
    double value = 0;
    if (!message.asDouble(value)) {
      lastError_ = OpenNetError::InvalidFrame;
      stopTransport();
      return;
    }
  }
  if (handler_) {
    handler_(message);
  }
  if ((message.flags & kAckRequired) != 0) {
    sendFrame(OpenNetFrameKind::Ack, OpenNetValueType::Null, "", nullptr, 0,
              message.messageId, 0);
  }
}

uint16_t OpenNetClient::readU16(const uint8_t* bytes) {
  return static_cast<uint16_t>((static_cast<uint16_t>(bytes[0]) << 8) |
                               bytes[1]);
}

uint32_t OpenNetClient::readU32(const uint8_t* bytes) {
  return (static_cast<uint32_t>(bytes[0]) << 24) |
         (static_cast<uint32_t>(bytes[1]) << 16) |
         (static_cast<uint32_t>(bytes[2]) << 8) | bytes[3];
}

void OpenNetClient::writeU16(uint8_t* bytes, uint16_t value) {
  bytes[0] = static_cast<uint8_t>(value >> 8);
  bytes[1] = static_cast<uint8_t>(value);
}

void OpenNetClient::writeU32(uint8_t* bytes, uint32_t value) {
  bytes[0] = static_cast<uint8_t>(value >> 24);
  bytes[1] = static_cast<uint8_t>(value >> 16);
  bytes[2] = static_cast<uint8_t>(value >> 8);
  bytes[3] = static_cast<uint8_t>(value);
}

uint32_t OpenNetClient::crc32(const uint8_t* data, size_t length,
                              uint32_t previous) {
  uint32_t crc = previous ^ 0xFFFFFFFFu;
  for (size_t i = 0; i < length; ++i) {
    crc ^= data[i];
    for (uint8_t bit = 0; bit < 8; ++bit) {
      const uint32_t mask = -(crc & 1u);
      crc = (crc >> 1) ^ (0xEDB88320u & mask);
    }
  }
  return crc ^ 0xFFFFFFFFu;
}

const char* openNetErrorName(OpenNetError error) {
  switch (error) {
    case OpenNetError::None:
      return "none";
    case OpenNetError::NotConnected:
      return "not connected";
    case OpenNetError::InvalidArgument:
      return "invalid argument";
    case OpenNetError::TopicTooLong:
      return "topic too long";
    case OpenNetError::PayloadTooLarge:
      return "payload too large";
    case OpenNetError::TransportWrite:
      return "transport write failed";
    case OpenNetError::InvalidFrame:
      return "invalid frame";
    case OpenNetError::ChecksumMismatch:
      return "checksum mismatch";
  }
  return "unknown error";
}
