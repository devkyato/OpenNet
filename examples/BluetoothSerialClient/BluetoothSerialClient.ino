#include <BluetoothSerial.h>
#include <OpenNet.h>

#if !defined(CONFIG_BT_SPP_ENABLED)
#error Bluetooth Classic SPP is unavailable on this ESP32 target
#endif

BluetoothSerial radio;
OpenNetClient openNet(radio);
unsigned long lastSend = 0;

void setup() {
  Serial.begin(115200);
  radio.begin("OpenNet-ESP32");
  openNet.onMessage([](const OpenNetMessage& message) {
    Serial.print(message.topic);
    Serial.print(": ");
    Serial.println(message.text());
  });
}

void loop() {
  openNet.poll();
  if (radio.hasClient() && millis() - lastSend >= 5000) {
    lastSend = millis();
    if (openNet.sendText("device/status", "online") == 0) {
      Serial.println(openNetErrorName(openNet.lastError()));
    }
  }
}
