#include <WiFi.h>
#include <OpenNet.h>

const char* WIFI_NAME = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* OPENNET_HOST = "192.168.1.50";
const uint16_t OPENNET_PORT = 8765;

WiFiClient transport;
OpenNetClient client(transport);

unsigned long nextSend = 0;
unsigned long nextReconnect = 0;

void connectNetwork() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  Serial.println(WiFi.localIP());
}

void setup() {
  Serial.begin(115200);
  connectNetwork();
  client.onMessage([](const OpenNetMessage& message) {
    Serial.printf("received id=%lu topic=%s bytes=%u\n",
                  static_cast<unsigned long>(message.messageId),
                  message.topic.c_str(),
                  static_cast<unsigned>(message.payload.size()));
  });
}

void loop() {
  client.poll();

  const unsigned long now = millis();
  if (!client.connected() && now >= nextReconnect) {
    Serial.println("Connecting to OpenNet...");
    if (client.connect(OPENNET_HOST, OPENNET_PORT)) {
      Serial.println("OpenNet connected");
    }
    nextReconnect = now + 2000;
  }

  if (client.connected() && now >= nextSend) {
    const float temperature = 20.0f + static_cast<float>(esp_random() % 1000) / 100.0f;
    const String json =
        "{\"device\":\"esp32-example\",\"temperature_c\":" +
        String(temperature, 2) + "}";
    const uint32_t id = client.sendJson("lab/telemetry", json);
    Serial.printf("sent message %lu\n", static_cast<unsigned long>(id));
    nextSend = now + 2000;
  }
}
