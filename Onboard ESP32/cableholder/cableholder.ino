#include <WiFi.h>

#define CONNECTION_LED 26
#define HOST_LED 2
const char* ssid     = "CableHolder Network";   // Network name
const char* password = "ObamaHamburgerSussyBalls";        // Min 8 chars, or "" for open
const int port = 5005;
const int MAX_CONNECTIONS = 4;

bool isHost = false;
int node_count; // Only modifiable by host node

WiFiServer* server = nullptr;
WiFiClient hostConnection;
WiFiClient clients[MAX_CONNECTIONS]; // Only used for host node


bool networkExists(){
  delay(500);
  int n = WiFi.scanNetworks();
  for(int i = 0; i < n; i++){
    if(WiFi.SSID(i) == ssid){
      return true;
    }
  }
  return false;
}

void startAsHost(){
    isHost = true;
    server = new WiFiServer(port);
    WiFi.softAP(ssid, password, 1, false, 4);
      
    server->begin();
    pinMode(HOST_LED, OUTPUT);
    digitalWrite(HOST_LED, HIGH);
}

void startAsClient(){
  isHost = false;
  WiFi.mode(WIFI_STA);
  delay(100);
  WiFi.begin(ssid, password);
  pinMode(CONNECTION_LED, OUTPUT);
  Serial.println("Attempting to connect to network");
  while(WiFi.status() != WL_CONNECTED){
    Serial.println("Failed to connect");
    delay(1000);
  }
  Serial.println("Connected to network");
  digitalWrite(CONNECTION_LED, HIGH);
}

void updateConnectionCount(){
  int count = 0;
  for(auto client : clients){
    if(client && client.connected()){
      count += 1;
    }
  }
  node_count = count + 1;
}

void broadcastNodeCount(){
  String msg = "NUM NODES: " + String(node_count) + "\n";
  for(auto client : clients){
    if(client && client.connected()){
      client.print(msg);
      Serial.println(msg);
    }
  }
}

void broadcastMessage(String msg, int senderIndex) {
  for (int i = 0; i < MAX_CONNECTIONS; i++) {
    if (i != senderIndex && clients[i] && clients[i].connected()) {
      clients[i].println(msg);
    }
  }
}

void loopHost(){
  // Accept new connection if none active
  WiFiClient newClient = server->available();
  if(newClient){
    for(int i = 0; i < 4; i++){
      digitalWrite(CONNECTION_LED, HIGH);
      delay(250);
      digitalWrite(CONNECTION_LED, LOW);
      delay(250);
    }
    for(int i  = 0; i < MAX_CONNECTIONS; i++){
      if(!clients[i] || !clients[i].connected()){
        clients[i] = newClient;
        updateConnectionCount();
        broadcastNodeCount();
        break;
      }
    }
  }

  for(int i = 0; i < MAX_CONNECTIONS; i++){
    if(clients[i] && clients[i].connected() && clients[i].available()){
      String msg = clients[i].readStringUntil('\n');
      msg.trim();

      if(msg != "NODE" && msg != "HEARTBEAT"){
        broadcastMessage(msg, i);
      }
    }

    if(clients[i] && !clients[i].connected()){
      clients[i].stop();
      updateConnectionCount();
      broadcastNodeCount();
    }

    static unsigned long lastBroadcast = 0;
    if (millis() - lastBroadcast > 5000) {
      updateConnectionCount();
      broadcastNodeCount();
      lastBroadcast = millis();
    }

  }

}

void loopClient() {
  // Reconnect if dropped
  if (!hostConnection.connected()) {
    Serial.println("Lost connection to host, retrying...");
    hostConnection.connect("192.168.4.1", port);
    delay(1000);
    return;
  }

  static unsigned long lastSend = 0;
  if (millis() - lastSend > 5000) {
    hostConnection.println("HEARTBEAT");
    lastSend = millis();
  }
}

void setup() {
  Serial.begin(9600);
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  Serial.println("About to scan for network...");
  if(networkExists()){
    Serial.println("Found network");
    startAsClient();  
    Serial.println("Connected to network");
  }else{
    WiFi.mode(WIFI_MODE_APSTA);
    startAsHost();
  }
}

void loop() {
  if(isHost){
    loopHost();
  }else{
    loopClient();
  }
}


