#include <WiFi.h>

#define LED 2

const char* ssid     = "CableHolder Network";   // Network name
const char* password = "ObamaHamburgerSussyBalls";        // Min 8 chars, or "" for open

int node_count = 1;

WiFiServer server(5005);
WiFiClient client;

void setup() {
  Serial.begin(9600);
  Serial.print("Server started");
  // Start Access Point
  WiFi.softAP(ssid, password);
  Serial.print("AP IP address: ");
  Serial.println(WiFi.softAPIP());  // Usually 192.168.4.1
  server.begin();

  pinMode(LED, OUTPUT);
  // digitalWrite(LED, HIGH);


}

void loop() {
  // Accept new connection if none active
  if (!client || !client.connected()) {
    client = server.available();
    if (client) {
      Serial.println("PC connected!");
      writeDigital(LED, HIGH)
    }
  }

  // Send a trigger every 5 seconds
  if (client && client.connected()) {
    client.println("TRIGGER");
    delay(5000);
  }
}