#include <OpenNet.h>

#include <cassert>
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <deque>
#include <string>
#include <vector>

namespace {

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

void testFragmentedAckIsRecognized() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  transport.receive(
      fromHex("4f4e01020006000000000001000000000000000000000000"));

  while (transport.available() > 0) {
    client.poll();
  }
  assert(client.lastAcknowledgedMessage() == 1);
  assert(client.lastError() == OpenNetError::None);
}

void testIncomingDataIsDeliveredAndAcknowledged() {
  FakeClient transport;
  OpenNetClient client(transport);
  assert(client.connect("127.0.0.1", 8765));
  bool handled = false;
  client.onMessage([&handled](const OpenNetMessage& message) {
    handled = true;
    assert(message.messageId == 9);
    assert(std::strcmp(message.topic.c_str(), "server") == 0);
    assert(std::strcmp(message.text().c_str(), "ok") == 0);
  });
  transport.outbound.clear();
  transport.receive(fromHex(
      "4f4e0101010100060000000900000002cd83e74a000000007365727665726f6b"));

  client.poll();
  assert(handled);
  assert(transport.outbound ==
         fromHex("4f4e01020006000000000009000000000000000000000000"));
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

}  // namespace

int main() {
  testSendProducesConformantFrame();
  testPartialTransportWritesAreCompleted();
  testFragmentedAckIsRecognized();
  testIncomingDataIsDeliveredAndAcknowledged();
  testOversizedDeclarationClosesTransport();
  testTypedMessageAccessors();
  testMalformedTypedPayloadClosesTransport();
  return 0;
}
