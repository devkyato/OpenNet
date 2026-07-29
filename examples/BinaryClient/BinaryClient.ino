#include <WiFi.h>
#include <OpenNet.h>

const char* WIFI_NAME = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* OPENNET_HOST = "192.168.1.50";

WiFiClient transport;
OpenNetClient client(transport);

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
  if (!client.connect(OPENNET_HOST, 8765)) {
    Serial.println("OpenNet connection failed");
    return;
  }

  const uint8_t sample[] = {0x00, 0x01, 0x7f, 0x80, 0xfe, 0xff};
  client.sendBinary("device/sample", sample, sizeof(sample));
}

void loop() {
  client.poll();
  delay(1);
}
