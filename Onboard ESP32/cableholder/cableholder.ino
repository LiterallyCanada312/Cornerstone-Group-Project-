#include <WiFi.h>

#define LED 26

const char* ssid     = "CableHolder Network";   // Network name
const char* password = "ObamaHamburgerSussyBalls";        // Min 8 chars, or "" for open
bool isHost = false;
int node_count = 1;

WiFiServer server(5005);
WiFiClient client;

bool networkExists(){
  int n = WiFi.scanNetworks();
  for (i = 0; i < n; i++){
    if(WiFi.SSID(i) == ssid){
      return true;
    }
  }
  return false;
}

void startAsHost(){
    isHost = true;
    WiFi.softAP(ssid, password);
  //Serial.print("AP IP address: ");
  //Serial.println(WiFi.softAPIP());  // Usually 192.168.4.1
    server.begin();
}

void startAsClient(){
  isHost = false;
  WiFi.begin(ssid, password);
  while(WiFi.status() !=  )
}

void loopHost(){}

void loopClient(){}

void setup() {
  //Serial.begin(9600);
  //Serial.print("Server started");
  // Start Access Point
  if(!networkExists()){
    startAsHost();
  }
  
  pinMode(LED, OUTPUT);
  //digitalWrite(LED, HIGH);
}

void loop() {
  // Accept new connection if none active
  if (!client || !client.connected()) {
    client = server.available();
    if (client) {
      //Serial.println("PC connected!");
      digitalWrite(LED, HIGH);
    }
    else {
      digitalWrite(LED, LOW);
    }
  }

  // Send a trigger every half second
  if (client && client.connected()) {
    client.write(byte(node_count));
    delay(500);
  }
}