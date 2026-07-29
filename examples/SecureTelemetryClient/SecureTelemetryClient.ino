#include <OpenNet.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

const char* wifiName = "YOUR_WIFI_NAME";
const char* wifiPassword = "YOUR_WIFI_PASSWORD";
const char* serverHost = "opennet.example.net";
const uint16_t serverPort = 8765;

// Replace this example certificate with the CA that issued the server
// certificate. Never use setInsecure() in production.
const char* caCertificate = R"EOF(
-----BEGIN CERTIFICATE-----
REPLACE_WITH_YOUR_CA_CERTIFICATE
-----END CERTIFICATE-----
)EOF";

WiFiClientSecure transport;
OpenNetClient openNet(transport);
unsigned long lastSend = 0;

void setup() {
  Serial.begin(115200);
  WiFi.begin(wifiName, wifiPassword);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
  transport.setCACert(caCertificate);
}

void loop() {
  if (!openNet.connected()) {
    if (!openNet.connect(serverHost, serverPort)) {
      Serial.println(openNetErrorName(openNet.lastError()));
      delay(1000);
      return;
    }
  }

  openNet.poll();
  if (millis() - lastSend >= 5000) {
    lastSend = millis();
    const uint32_t id = openNet.sendDouble("lab/temperature", 24.7);
    if (id == 0) {
      Serial.println(openNetErrorName(openNet.lastError()));
    }
  }
}
