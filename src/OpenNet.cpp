#include "OpenNet.h"

#include <cmath>
#include <cstring>
#include <utility>

namespace {

bool isContinuation(uint8_t byte) { return (byte & 0xC0u) == 0x80u; }

bool validUtf8(const uint8_t* data, size_t length) {
  size_t index = 0;
  while (index < length) {
    const uint8_t first = data[index++];
    if (first <= 0x7Fu) {
      continue;
    }
    if (first >= 0xC2u && first <= 0xDFu) {
      if (index >= length || !isContinuation(data[index++])) {
        return false;
      }
      continue;
    }
    if (first >= 0xE0u && first <= 0xEFu) {
      if (index + 1 >= length) {
        return false;
      }
      const uint8_t second = data[index++];
      const uint8_t third = data[index++];
      if (!isContinuation(third) ||
          (first == 0xE0u && (second < 0xA0u || second > 0xBFu)) ||
          (first == 0xEDu && (second < 0x80u || second > 0x9Fu)) ||
          (first != 0xE0u && first != 0xEDu &&
           !isContinuation(second))) {
        return false;
      }
      continue;
    }
    if (first >= 0xF0u && first <= 0xF4u) {
      if (index + 2 >= length) {
        return false;
      }
      const uint8_t second = data[index++];
      const uint8_t third = data[index++];
      const uint8_t fourth = data[index++];
      if (!isContinuation(third) || !isContinuation(fourth) ||
          (first == 0xF0u && (second < 0x90u || second > 0xBFu)) ||
          (first == 0xF4u && (second < 0x80u || second > 0x8Fu)) ||
          (first != 0xF0u && first != 0xF4u &&
           !isContinuation(second))) {
        return false;
      }
      continue;
    }
    return false;
  }
  return true;
}

class JsonValidator {
 public:
  JsonValidator(const uint8_t* data, size_t length)
      : data_(data), length_(length), position_(0) {}

  bool validate() {
    skipWhitespace();
    if (!parseValue(0)) {
      return false;
    }
    skipWhitespace();
    return position_ == length_;
  }

 private:
  static constexpr uint8_t kMaxDepth = 32;

  const uint8_t* data_;
  size_t length_;
  size_t position_;

  void skipWhitespace() {
    while (position_ < length_ &&
           (data_[position_] == ' ' || data_[position_] == '\t' ||
            data_[position_] == '\r' || data_[position_] == '\n')) {
      ++position_;
    }
  }

  bool consume(char expected) {
    if (position_ >= length_ ||
        data_[position_] != static_cast<uint8_t>(expected)) {
      return false;
    }
    ++position_;
    return true;
  }

  bool consumeLiteral(const char* literal) {
    for (size_t index = 0; literal[index] != '\0'; ++index) {
      if (!consume(literal[index])) {
        return false;
      }
    }
    return true;
  }

  bool parseValue(uint8_t depth) {
    if (position_ >= length_) {
      return false;
    }
    switch (data_[position_]) {
      case '"':
        return parseString();
      case '{':
        return parseObject(depth);
      case '[':
        return parseArray(depth);
      case 't':
        return consumeLiteral("true");
      case 'f':
        return consumeLiteral("false");
      case 'n':
        return consumeLiteral("null");
      default:
        return parseNumber();
    }
  }

  bool parseObject(uint8_t depth) {
    if (depth >= kMaxDepth || !consume('{')) {
      return false;
    }
    skipWhitespace();
    if (consume('}')) {
      return true;
    }
    while (true) {
      if (!parseString()) {
        return false;
      }
      skipWhitespace();
      if (!consume(':')) {
        return false;
      }
      skipWhitespace();
      if (!parseValue(static_cast<uint8_t>(depth + 1))) {
        return false;
      }
      skipWhitespace();
      if (consume('}')) {
        return true;
      }
      if (!consume(',')) {
        return false;
      }
      skipWhitespace();
    }
  }

  bool parseArray(uint8_t depth) {
    if (depth >= kMaxDepth || !consume('[')) {
      return false;
    }
    skipWhitespace();
    if (consume(']')) {
      return true;
    }
    while (true) {
      if (!parseValue(static_cast<uint8_t>(depth + 1))) {
        return false;
      }
      skipWhitespace();
      if (consume(']')) {
        return true;
      }
      if (!consume(',')) {
        return false;
      }
      skipWhitespace();
    }
  }

  static bool isHex(uint8_t byte) {
    return (byte >= '0' && byte <= '9') ||
           (byte >= 'a' && byte <= 'f') ||
           (byte >= 'A' && byte <= 'F');
  }

  static uint16_t hexValue(uint8_t byte) {
    if (byte >= '0' && byte <= '9') {
      return static_cast<uint16_t>(byte - '0');
    }
    if (byte >= 'a' && byte <= 'f') {
      return static_cast<uint16_t>(byte - 'a' + 10);
    }
    return static_cast<uint16_t>(byte - 'A' + 10);
  }

  bool parseHexEscape(uint16_t& value) {
    if (position_ + 4 > length_) {
      return false;
    }
    value = 0;
    for (uint8_t index = 0; index < 4; ++index) {
      const uint8_t byte = data_[position_++];
      if (!isHex(byte)) {
        return false;
      }
      value = static_cast<uint16_t>((value << 4) | hexValue(byte));
    }
    return true;
  }

  bool parseString() {
    if (!consume('"')) {
      return false;
    }
    while (position_ < length_) {
      const uint8_t byte = data_[position_++];
      if (byte == '"') {
        return true;
      }
      if (byte < 0x20u) {
        return false;
      }
      if (byte != '\\') {
        continue;
      }
      if (position_ >= length_) {
        return false;
      }
      const uint8_t escape = data_[position_++];
      if (escape == '"' || escape == '\\' || escape == '/' ||
          escape == 'b' || escape == 'f' || escape == 'n' ||
          escape == 'r' || escape == 't') {
        continue;
      }
      if (escape != 'u') {
        return false;
      }
      uint16_t code = 0;
      if (!parseHexEscape(code)) {
        return false;
      }
      if (code >= 0xD800u && code <= 0xDBFFu) {
        if (!consume('\\') || !consume('u')) {
          return false;
        }
        uint16_t low = 0;
        if (!parseHexEscape(low) || low < 0xDC00u || low > 0xDFFFu) {
          return false;
        }
      } else if (code >= 0xDC00u && code <= 0xDFFFu) {
        return false;
      }
    }
    return false;
  }

  bool parseDigits() {
    const size_t start = position_;
    while (position_ < length_ && data_[position_] >= '0' &&
           data_[position_] <= '9') {
      ++position_;
    }
    return position_ > start;
  }

  bool parseNumber() {
    if (position_ < length_ && data_[position_] == '-') {
      ++position_;
    }
    if (position_ >= length_) {
      return false;
    }
    if (data_[position_] == '0') {
      ++position_;
      if (position_ < length_ && data_[position_] >= '0' &&
          data_[position_] <= '9') {
        return false;
      }
    } else if (data_[position_] >= '1' && data_[position_] <= '9') {
      if (!parseDigits()) {
        return false;
      }
    } else {
      return false;
    }
    if (position_ < length_ && data_[position_] == '.') {
      ++position_;
      if (!parseDigits()) {
        return false;
      }
    }
    if (position_ < length_ &&
        (data_[position_] == 'e' || data_[position_] == 'E')) {
      ++position_;
      if (position_ < length_ &&
          (data_[position_] == '+' || data_[position_] == '-')) {
        ++position_;
      }
      if (!parseDigits()) {
        return false;
      }
    }
    return true;
  }
};

bool validJson(const uint8_t* data, size_t length) {
  return validUtf8(data, length) && JsonValidator(data, length).validate();
}

bool validTypedPayload(OpenNetValueType type, const uint8_t* payload,
                       size_t length) {
  if (payload == nullptr && length != 0) {
    return false;
  }
  switch (type) {
    case OpenNetValueType::Bytes:
      return true;
    case OpenNetValueType::Utf8:
      return validUtf8(payload, length);
    case OpenNetValueType::Json:
      return validJson(payload, length);
    case OpenNetValueType::Int64:
      return length == 8;
    case OpenNetValueType::Float64: {
      if (length != 8) {
        return false;
      }
      uint64_t bits = 0;
      for (size_t index = 0; index < 8; ++index) {
        bits = (bits << 8) | payload[index];
      }
      double value = 0;
      memcpy(&value, &bits, sizeof(value));
      return std::isfinite(value);
    }
    case OpenNetValueType::Bool:
      return length == 1 && payload[0] <= 1;
    case OpenNetValueType::Null:
      return length == 0;
  }
  return false;
}

}  // namespace

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

OpenNetClient::OpenNetClient(Stream& transport, uint32_t maxPayload,
                             uint32_t writeTimeoutMs)
    : transport_(transport),
      clientTransport_(nullptr),
      maxPayload_(maxPayload),
      writeTimeoutMs_(writeTimeoutMs),
      nextMessageId_(1),
      lastAcknowledged_(0),
      pendingAcks_{},
      pendingAckCount_(0),
      acknowledgedIds_{},
      acknowledgedCount_(0),
      lastError_(OpenNetError::None),
      viewHandler_(nullptr),
      viewContext_(nullptr),
      headerReceived_(0),
      receiveBuffer_(nullptr),
      receiveCapacity_(0),
      bodyReceived_(0),
      expectedTopicLength_(0),
      expectedPayloadLength_(0) {}

OpenNetClient::OpenNetClient(Client& transport, uint32_t maxPayload,
                             uint32_t writeTimeoutMs)
    : OpenNetClient(static_cast<Stream&>(transport), maxPayload,
                    writeTimeoutMs) {
  clientTransport_ = &transport;
}

OpenNetClient::OpenNetClient(Stream& transport, uint8_t* receiveBuffer,
                             size_t receiveCapacity, uint32_t maxPayload,
                             uint32_t writeTimeoutMs)
    : OpenNetClient(transport, maxPayload, writeTimeoutMs) {
  receiveBuffer_ = receiveBuffer;
  receiveCapacity_ = receiveCapacity;
}

OpenNetClient::OpenNetClient(Client& transport, uint8_t* receiveBuffer,
                             size_t receiveCapacity, uint32_t maxPayload,
                             uint32_t writeTimeoutMs)
    : OpenNetClient(static_cast<Stream&>(transport), receiveBuffer,
                    receiveCapacity, maxPayload, writeTimeoutMs) {
  clientTransport_ = &transport;
}

bool OpenNetClient::connect(const char* host, uint16_t port) {
  if (clientTransport_ == nullptr || host == nullptr || host[0] == '\0' ||
      port == 0) {
    lastError_ = OpenNetError::InvalidArgument;
    return false;
  }
  resetReceiver();
  resetAcknowledgements();
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
  resetAcknowledgements();
}

bool OpenNetClient::connected() const {
  return clientTransport_ == nullptr || clientTransport_->connected();
}

void OpenNetClient::poll(size_t maxBytes) {
  if (!connected()) {
    return;
  }

  size_t processed = 0;
  while (transport_.available() > 0 && processed < maxBytes) {
    if (headerReceived_ < kHeaderSize) {
      const int byte = transport_.read();
      if (byte < 0) {
        return;
      }
      ++processed;
      header_[headerReceived_++] = static_cast<uint8_t>(byte);
      if (headerReceived_ == kHeaderSize && !prepareBody()) {
        stopTransport();
        resetReceiver();
        return;
      }
    } else {
      const size_t total =
          static_cast<size_t>(expectedTopicLength_) + expectedPayloadLength_;
      while (bodyReceived_ < total && transport_.available() > 0 &&
             processed < maxBytes) {
        const int byte = transport_.read();
        if (byte < 0) {
          return;
        }
        ++processed;
        bodyData()[bodyReceived_++] = static_cast<uint8_t>(byte);
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

void OpenNetClient::onMessageView(MessageViewHandler handler, void* context) {
  viewHandler_ = handler;
  viewContext_ = context;
}

OpenNetError OpenNetClient::lastError() const { return lastError_; }

uint32_t OpenNetClient::lastAcknowledgedMessage() const {
  return lastAcknowledged_;
}

bool OpenNetClient::acknowledged(uint32_t messageId) const {
  if (messageId == 0) {
    return false;
  }
  for (size_t index = 0; index < acknowledgedCount_; ++index) {
    if (acknowledgedIds_[index] == messageId) {
      return true;
    }
  }
  return false;
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
  if (requireAck && pendingAckCount_ >= kAckWindowSize) {
    lastError_ = OpenNetError::TooManyPendingAcks;
    return 0;
  }
  uint32_t id = nextMessageId_;
  while (isPendingAck(id)) {
    id = id == UINT32_MAX ? 1 : id + 1;
  }
  nextMessageId_ = id == UINT32_MAX ? 1 : id + 1;
  if (!sendFrame(OpenNetFrameKind::Data, type, topic, payload, length, id,
                 requireAck ? kAckRequired : 0)) {
    return 0;
  }
  if (requireAck && !rememberPendingAck(id)) {
    lastError_ = OpenNetError::TooManyPendingAcks;
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
  if (!validUtf8(reinterpret_cast<const uint8_t*>(safeTopic), topicLength)) {
    lastError_ = OpenNetError::InvalidArgument;
    return false;
  }
  if (length > maxPayload_ || length > UINT32_MAX) {
    lastError_ = OpenNetError::PayloadTooLarge;
    return false;
  }
  if ((flags & ~kAllowedFlags) != 0) {
    lastError_ = OpenNetError::InvalidArgument;
    return false;
  }
  if (kind == OpenNetFrameKind::Data) {
    if (topicLength == 0 || messageId == 0 ||
        !validTypedPayload(type, payload, length)) {
      lastError_ = OpenNetError::InvalidArgument;
      return false;
    }
  } else if (kind == OpenNetFrameKind::Ack) {
    if (topicLength != 0 || messageId == 0 || length != 0 ||
        type != OpenNetValueType::Null) {
      lastError_ = OpenNetError::InvalidArgument;
      return false;
    }
  } else if (kind == OpenNetFrameKind::Ping ||
             kind == OpenNetFrameKind::Pong) {
    if (topicLength != 0 || messageId != 0 || length != 0 ||
        type != OpenNetValueType::Null || flags != 0) {
      lastError_ = OpenNetError::InvalidArgument;
      return false;
    }
  } else if (kind == OpenNetFrameKind::Close ||
             kind == OpenNetFrameKind::Error) {
    if (topicLength != 0 || messageId != 0 || flags != 0 ||
        (length != 0 && type != OpenNetValueType::Utf8) ||
        !validUtf8(payload, length)) {
      lastError_ = OpenNetError::InvalidArgument;
      return false;
    }
  } else {
    lastError_ = OpenNetError::InvalidArgument;
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
    if (lastError_ != OpenNetError::WriteTimeout) {
      lastError_ = OpenNetError::TransportWrite;
    }
    return false;
  }
  lastError_ = OpenNetError::None;
  return true;
}

bool OpenNetClient::writeAll(const uint8_t* data, size_t length) {
  size_t offset = 0;
  const uint32_t started = millis();
  while (offset < length) {
    if (offset > 0 &&
        static_cast<uint32_t>(millis() - started) >= writeTimeoutMs_) {
      lastError_ = OpenNetError::WriteTimeout;
      return false;
    }
    const size_t written = transport_.write(data + offset, length - offset);
    if (written == 0 || written > length - offset) {
      return false;
    }
    offset += written;
    if (offset < length) {
      yield();
    }
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
  clearBody();
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
  const size_t bodyLength =
      static_cast<size_t>(expectedTopicLength_) + expectedPayloadLength_;
  if (!reserveBody(bodyLength)) {
    lastError_ = OpenNetError::ReceiveBufferTooSmall;
    return false;
  }
  if (bodyLength == 0) {
    handleFrame();
    resetReceiver();
  }
  return true;
}

void OpenNetClient::handleFrame() {
  const uint32_t expectedChecksum = readU32(header_ + 16);
  const size_t bodyLength =
      static_cast<size_t>(expectedTopicLength_) + expectedPayloadLength_;
  const uint8_t* topicBytes = bodyLength == 0 ? nullptr : bodyData();
  const uint8_t* payload =
      bodyLength == 0 ? nullptr : bodyData() + expectedTopicLength_;
  uint32_t actualChecksum = crc32(topicBytes, expectedTopicLength_);
  actualChecksum = crc32(payload, expectedPayloadLength_, actualChecksum);
  if (actualChecksum != expectedChecksum) {
    lastError_ = OpenNetError::ChecksumMismatch;
    stopTransport();
    return;
  }

  const auto kind = static_cast<OpenNetFrameKind>(header_[3]);
  const auto valueType = static_cast<OpenNetValueType>(header_[5]);
  const uint32_t messageId = readU32(header_ + 8);
  if (kind == OpenNetFrameKind::Data &&
      !validUtf8(topicBytes, expectedTopicLength_)) {
    lastError_ = OpenNetError::InvalidFrame;
    stopTransport();
    return;
  }
  if ((kind == OpenNetFrameKind::Close ||
       kind == OpenNetFrameKind::Error) &&
      !validUtf8(payload, expectedPayloadLength_)) {
    lastError_ = OpenNetError::InvalidFrame;
    stopTransport();
    return;
  }
  if (kind == OpenNetFrameKind::Data &&
      !validTypedPayload(valueType, payload, expectedPayloadLength_)) {
    lastError_ = OpenNetError::InvalidFrame;
    stopTransport();
    return;
  }
  if (kind == OpenNetFrameKind::Ack) {
    if (rememberAcknowledged(messageId)) {
      lastAcknowledged_ = messageId;
    }
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
  if ((header_[4] & kAckRequired) != 0) {
    sendFrame(OpenNetFrameKind::Ack, OpenNetValueType::Null, "", nullptr, 0,
              messageId, 0);
  }
  if (viewHandler_ != nullptr) {
    const OpenNetMessageView view{
        kind,
        valueType,
        topicBytes,
        expectedTopicLength_,
        payload,
        expectedPayloadLength_,
        messageId,
        header_[4],
    };
    viewHandler_(view, viewContext_);
  }
  if (handler_) {
    OpenNetMessage message;
    message.kind = kind;
    message.valueType = valueType;
    message.messageId = messageId;
    message.flags = header_[4];
    message.topic.reserve(expectedTopicLength_);
    for (size_t i = 0; i < expectedTopicLength_; ++i) {
      message.topic += static_cast<char>(topicBytes[i]);
    }
    if (receiveBuffer_ != nullptr) {
      if (expectedPayloadLength_ > 0) {
        message.payload.assign(payload, payload + expectedPayloadLength_);
      }
    } else {
      if (expectedPayloadLength_ > 0) {
        memmove(body_.data(), payload, expectedPayloadLength_);
        body_.resize(expectedPayloadLength_);
      } else {
        body_.clear();
      }
      message.payload = std::move(body_);
    }
    handler_(message);
    if (receiveBuffer_ == nullptr) {
      body_ = std::move(message.payload);
    }
  }
}

uint8_t* OpenNetClient::bodyData() {
  return receiveBuffer_ == nullptr ? body_.data() : receiveBuffer_;
}

const uint8_t* OpenNetClient::bodyData() const {
  return receiveBuffer_ == nullptr ? body_.data() : receiveBuffer_;
}

bool OpenNetClient::reserveBody(size_t length) {
  if (receiveBuffer_ != nullptr) {
    return length <= receiveCapacity_;
  }
  body_.resize(length);
  return true;
}

void OpenNetClient::clearBody() {
  if (receiveBuffer_ == nullptr) {
    body_.clear();
  }
}

bool OpenNetClient::isPendingAck(uint32_t messageId) const {
  for (size_t index = 0; index < pendingAckCount_; ++index) {
    if (pendingAcks_[index] == messageId) {
      return true;
    }
  }
  return false;
}

bool OpenNetClient::rememberPendingAck(uint32_t messageId) {
  if (pendingAckCount_ >= kAckWindowSize) {
    return false;
  }
  pendingAcks_[pendingAckCount_++] = messageId;
  return true;
}

bool OpenNetClient::rememberAcknowledged(uint32_t messageId) {
  bool wasPending = false;
  for (size_t index = 0; index < pendingAckCount_; ++index) {
    if (pendingAcks_[index] == messageId) {
      for (size_t move = index + 1; move < pendingAckCount_; ++move) {
        pendingAcks_[move - 1] = pendingAcks_[move];
      }
      --pendingAckCount_;
      wasPending = true;
      break;
    }
  }
  if (!wasPending) {
    return false;
  }
  if (acknowledgedCount_ < kAckWindowSize) {
    acknowledgedIds_[acknowledgedCount_++] = messageId;
    return true;
  }
  for (size_t index = 1; index < kAckWindowSize; ++index) {
    acknowledgedIds_[index - 1] = acknowledgedIds_[index];
  }
  acknowledgedIds_[kAckWindowSize - 1] = messageId;
  return true;
}

void OpenNetClient::resetAcknowledgements() {
  pendingAckCount_ = 0;
  acknowledgedCount_ = 0;
  lastAcknowledged_ = 0;
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
    case OpenNetError::WriteTimeout:
      return "write timeout";
    case OpenNetError::TooManyPendingAcks:
      return "too many pending acknowledgements";
    case OpenNetError::ReceiveBufferTooSmall:
      return "receive buffer too small";
  }
  return "unknown error";
}
