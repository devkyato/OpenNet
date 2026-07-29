#include <OpenNet.h>

#include <cassert>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

namespace {

struct SharedVector {
  const char* name;
  bool accepted;
  const char* hex;
};

const SharedVector kSharedVectors[] = {
#define ONP_VECTOR(name, accepted, hex) {#name, accepted, hex},
#include "../vectors/onp1_vectors.inc"
#undef ONP_VECTOR
};

std::vector<uint8_t> fromHex(const char* hex) {
  std::vector<uint8_t> result;
  for (std::size_t index = 0; hex[index] != '\0'; index += 2) {
    const std::string byte(hex + index, 2);
    result.push_back(static_cast<uint8_t>(std::stoul(byte, nullptr, 16)));
  }
  return result;
}

class FakeClient : public Client {
 public:
  int connect(const char* host, uint16_t port) override {
    isConnected = host != nullptr && host[0] != '\0' && port != 0;
    return isConnected ? 1 : 0;
  }

  std::size_t write(const uint8_t* data, std::size_t size) override {
    if (!isConnected) {
      return 0;
    }
    const std::size_t accepted =
        maxWrite == 0 ? size : std::min(size, maxWrite);
    outbound.insert(outbound.end(), data, data + accepted);
    return accepted;
  }

  int available() override { return static_cast<int>(inbound.size()); }

  int read() override {
    if (inbound.empty()) {
      return -1;
    }
    const uint8_t value = inbound.front();
    inbound.pop_front();
    return value;
  }

  void stop() override { isConnected = false; }
  uint8_t connected() override { return isConnected ? 1 : 0; }

  void receive(const std::vector<uint8_t>& bytes) {
    inbound.insert(inbound.end(), bytes.begin(), bytes.end());
  }

  bool isConnected = false;
  std::size_t maxWrite = 0;
  std::vector<uint8_t> outbound;
  std::deque<uint8_t> inbound;
};

void testSendProducesConformantFrame() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));

  const uint32_t messageId = client.sendText("status", String("online"));
  assert(messageId == 1);
  assert(transport.outbound.size() == 24 + 6 + 6);
  assert(transport.outbound[0] == 'O');
  assert(transport.outbound[1] == 'N');
  assert(transport.outbound[2] == 1);
  assert(transport.outbound[3] == 1);
  assert(transport.outbound[4] == 1);
  assert(transport.outbound[5] == 1);
  assert(transport.outbound[7] == 6);
  assert(std::memcmp(transport.outbound.data() + 24, "statusonline", 12) == 0);
}

void testPartialTransportWritesAreCompleted() {
  FakeClient transport;
  transport.maxWrite = 3;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  assert(client.sendText("status", String("online")) == 1);
  assert(transport.outbound.size() == 36);
  assert(std::memcmp(transport.outbound.data() + 24, "statusonline", 12) == 0);
}

void testWriteBudgetStopsTinyProgress() {
  FakeClient transport;
  transport.maxWrite = 1;
  OpenNetClient client(transport, OpenNetClient::kDefaultMaxPayload, 3);
  assert(client.connect("127.0.0.1", 8765));
  assert(client.sendText("status", String("online")) == 0);
  assert(client.lastError() == OpenNetError::WriteTimeout);
}

void testFragmentedAckIsRecognized() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  assert(client.sendNull("pending") == 1);
  transport.outbound.clear();
  transport.receive(
      fromHex("4f4e01020006000000000001000000000000000000000000"));

  while (transport.available() > 0) {
    client.poll(1);
  }
  assert(client.lastAcknowledgedMessage() == 1);
  assert(client.lastError() == OpenNetError::None);
}

void testIncomingDataIsDeliveredAndAcknowledged() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  int handled = 0;
  client.onMessage([&handled](const OpenNetMessage& message) {
    ++handled;
    assert(message.messageId == 9);
    assert(std::strcmp(message.topic.c_str(), "server") == 0);
    assert(std::strcmp(message.text().c_str(), "ok") == 0);
  });
  transport.outbound.clear();
  transport.receive(fromHex(
      "4f4e0101010100060000000900000002cd83e74a000000007365727665726f6b"));

  client.poll();
  assert(handled == 1);
  assert(transport.outbound ==
         fromHex("4f4e01020006000000000009000000000000000000000000"));

  transport.outbound.clear();
  transport.receive(fromHex(
      "4f4e0101010100060000000900000002cd83e74a000000007365727665726f6b"));
  client.poll();
  assert(handled == 2);
  assert(transport.outbound ==
         fromHex("4f4e01020006000000000009000000000000000000000000"));
}

void testPollByteBudgetYieldsBeforeWholeFrame() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  bool handled = false;
  client.onMessage([&handled](const OpenNetMessage&) { handled = true; });
  transport.receive(fromHex(
      "4f4e0101010100060000000900000002cd83e74a000000007365727665726f6b"));

  client.poll(24);
  assert(!handled);
  assert(transport.available() == 8);
  client.poll();
  assert(handled);
}

void testOversizedDeclarationClosesTransport() {
  FakeClient transport;
  OpenNetClient client(transport, 16);
  assert(client.connect("127.0.0.1", 8765));
  transport.receive(fromHex(
      "4f4e01010000000100000001000000110000000000000000"));

  client.poll();
  assert(!client.connected());
  assert(client.lastError() == OpenNetError::PayloadTooLarge);
}

void testTypedMessageAccessors() {
  OpenNetMessage message{};
  message.valueType = OpenNetValueType::Int64;
  message.payload = fromHex("ffffffffffffffd6");
  int64_t integer = 0;
  assert(message.asInt(integer));
  assert(integer == -42);

  message.valueType = OpenNetValueType::Bool;
  message.payload = {1};
  bool boolean = false;
  assert(message.asBool(boolean));
  assert(boolean);

  message.valueType = OpenNetValueType::Null;
  message.payload.clear();
  assert(message.isNull());
}

void testOutboundTypedPayloadsAreValidated() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  const uint8_t invalidBool = 2;
  const uint8_t invalidNull = 1;
  const uint8_t invalidUtf8[] = {0xFF};
  const uint8_t nonFinite[] = {0x7F, 0xF8, 0, 0, 0, 0, 0, 0};

  assert(client.send("value", OpenNetValueType::Bool, &invalidBool, 1) == 0);
  assert(client.send("value", OpenNetValueType::Null, &invalidNull, 1) == 0);
  assert(client.send("value", OpenNetValueType::Utf8, invalidUtf8,
                     sizeof(invalidUtf8)) == 0);
  assert(client.send("value", OpenNetValueType::Float64, nonFinite,
                     sizeof(nonFinite)) == 0);
  assert(client.sendJson("value", String("{\"x\":1,}")) == 0);
  assert(transport.outbound.empty());
}

void testJsonNestingIsBoundedOnSend() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  const std::string valid =
      std::string(32, '[') + "0" + std::string(32, ']');
  const std::string invalid =
      std::string(33, '[') + "0" + std::string(33, ']');
  assert(client.sendJson("json", String(valid.c_str()), false) == 1);
  assert(client.sendJson("json", String(invalid.c_str()), false) == 0);
}

void testBoundedPendingAndAcknowledgementHistory() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  for (uint32_t id = 1; id <= OpenNetClient::kAckWindowSize; ++id) {
    assert(client.sendNull("pending") == id);
  }
  assert(client.sendNull("pending") == 0);
  assert(client.lastError() == OpenNetError::TooManyPendingAcks);

  transport.receive(
      fromHex("4f4e010200060000000003e7000000000000000000000000"));
  transport.receive(
      fromHex("4f4e01020006000000000001000000000000000000000000"));
  transport.receive(
      fromHex("4f4e01020006000000000002000000000000000000000000"));
  client.poll();
  assert(!client.acknowledged(999));
  assert(client.acknowledged(1));
  assert(client.acknowledged(2));
  assert(client.sendNull("pending") == 9);
}

struct ViewObservation {
  bool handled = false;
};

void observeMessageView(const OpenNetMessageView& message, void* context) {
  auto* observation = static_cast<ViewObservation*>(context);
  observation->handled = true;
  assert(message.topicLength == 6);
  assert(std::memcmp(message.topic, "server", 6) == 0);
  assert(message.payloadLength == 2);
  assert(std::memcmp(message.payload, "ok", 2) == 0);
}

void testCallerOwnedReceiveBufferAndView() {
  FakeClient transport;
  uint8_t receiveBuffer[8] = {};
  OpenNetClient client(transport, receiveBuffer, sizeof(receiveBuffer), 16);
  assert(client.connect("127.0.0.1", 8765));
  ViewObservation observation;
  client.onMessageView(observeMessageView, &observation);
  transport.receive(fromHex(
      "4f4e0101010100060000000900000002cd83e74a000000007365727665726f6b"));
  client.poll();
  assert(observation.handled);

  FakeClient smallTransport;
  uint8_t smallBuffer[7] = {};
  OpenNetClient smallClient(smallTransport, smallBuffer, sizeof(smallBuffer),
                            16);
  assert(smallClient.connect("127.0.0.1", 8765));
  smallTransport.receive(fromHex(
      "4f4e0101010100060000000900000002cd83e74a000000007365727665726f6b"));
  smallClient.poll();
  assert(!smallClient.connected());
  assert(smallClient.lastError() == OpenNetError::ReceiveBufferTooSmall);
}

void testMalformedTypedPayloadClosesTransport() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  transport.receive(fromHex(
      "4f4e0101000500040000000b000000012c07001000000000666c616702"));
  client.poll();
  assert(!client.connected());
  assert(client.lastError() == OpenNetError::InvalidFrame);
}

void testSharedConformanceVectors() {
  for (const SharedVector& vector : kSharedVectors) {
    FakeClient transport;
    OpenNetClient client(transport);
    assert(client.connect("127.0.0.1", 8765));
    bool handled = false;
    client.onMessage([&handled](const OpenNetMessage&) { handled = true; });
    transport.receive(fromHex(vector.hex));
    client.poll();
    assert(client.connected() == vector.accepted);
    assert(handled == vector.accepted);
  }
}

}  // namespace

int main() {
  testSendProducesConformantFrame();
  testPartialTransportWritesAreCompleted();
  testWriteBudgetStopsTinyProgress();
  testFragmentedAckIsRecognized();
  testIncomingDataIsDeliveredAndAcknowledged();
  testPollByteBudgetYieldsBeforeWholeFrame();
  testOversizedDeclarationClosesTransport();
  testTypedMessageAccessors();
  testOutboundTypedPayloadsAreValidated();
  testJsonNestingIsBoundedOnSend();
  testBoundedPendingAndAcknowledgementHistory();
  testCallerOwnedReceiveBufferAndView();
  testMalformedTypedPayloadClosesTransport();
  testSharedConformanceVectors();
  return 0;
}
