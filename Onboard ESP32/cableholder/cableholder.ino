// Self-organizing mesh: the first ESP32 to boot becomes the host (softAP),
// every later board joins as a client. Host tracks node count and rebroadcasts
// it so each board knows how many peers are alive.
#include <WiFi.h>

#define CONNECTION_LED 26   // Lit on a client once it has joined the host AP
#define HOST_LED 27         // Lit on the board that ended up as host
const char* ssid     = "CableHolder Network";
const char* password = "ObamaHamburgerSussyBalls";   // Min 8 chars, or "" for open
const int port = 5005;
const int MAX_CONNECTIONS = 4;   // ESP32 softAP hard cap is 4 stations

bool isHost = false;
int node_count;   // Live peer count (host-authoritative); clients receive it via broadcast

WiFiServer* server = nullptr;            // Host-only listening socket
WiFiClient hostConnection;               // Client-only outbound link to the host
WiFiClient clients[MAX_CONNECTIONS];     // Host's accepted-client slots
bool isNode[MAX_CONNECTIONS];            // True = peer ESP32, False = generic script (e.g. Python tool)
unsigned long lastHeartbeat[MAX_CONNECTIONS];   // ms timestamp of the last message from each slot

// Probe nearby SSIDs to decide whether to host a new mesh or join an existing one.
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
    // channel 1, hidden=false, max 4 stations — matches MAX_CONNECTIONS
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
  // Block until associated — the rest of the firmware assumes a live link.
  while(WiFi.status() != WL_CONNECTED){
    Serial.println("Failed to connect");
    delay(1000);
  }
  Serial.println("Connected to network");
  digitalWrite(CONNECTION_LED, HIGH);
}

// Recount only slots that explicitly identified themselves as NODE.
// +1 accounts for the host itself, which never appears in the clients array.
void updateConnectionCount(){
  int count = 0;
  for(int i = 0; i < MAX_CONNECTIONS; i++){
    if(clients[i] && clients[i].connected() && isNode[i]){
      count += 1;
    }
  }
  node_count = count + 1;
}

// Push the current node_count to every connected client (nodes and scripts alike).
void broadcastNodeCount(){
  String msg = String(node_count) + "\n";
  for(auto client : clients){
    if(client && client.connected()){
      client.print(msg);
      Serial.println(msg);
    }
  }
}

// Tear down a slot and refresh the network's view of node_count.
void dropClient(int i) {
  Serial.printf("Dropping client %d (%s)\n", i, isNode[i] ? "NODE" : "SCRIPT");
  clients[i].stop();
  isNode[i] = false;
  lastHeartbeat[i] = 0;
  updateConnectionCount();
  broadcastNodeCount();
}

// Relay a message to every client except the originator.
void broadcastMessage(String msg, int senderIndex) {
  for (int i = 0; i < MAX_CONNECTIONS; i++) {
    if (i != senderIndex && clients[i] && clients[i].connected()) {
      clients[i].println(msg);
    }
  }
}

void loopHost(){
  unsigned long now = millis();

  // Accept a pending connection into the first free slot.
  WiFiClient newClient = server->available();
  if(newClient){
    for(int i  = 0; i < MAX_CONNECTIONS; i++){
      if(!clients[i] || !clients[i].connected()){
        clients[i] = newClient;
        updateConnectionCount();
        broadcastNodeCount();
        lastHeartbeat[i] = now;
        isNode[i] = false;   // Stays false until the peer announces "NODE"
        break;
      }
    }
  }

  // Service every active slot: enforce timeout, then drain whatever it sent us.
  for(int i = 0; i < MAX_CONNECTIONS; i++){

    if(!clients[i]) continue;

    // 10s without traffic = dead. Heartbeat cadence is 3s, so this allows ~3 misses.
    if (lastHeartbeat[i] > 0 && (now - lastHeartbeat[i]) > 10000) {
      Serial.printf("Client %d timed out\n", i);
      dropClient(i);
      continue;
    }

    while(clients[i].available()){
      String msg = clients[i].readStringUntil('\n');
      msg.trim();
      lastHeartbeat[i] = now;   // Any line counts as proof of life

      if(msg == "NODE"){
        // Peer self-identified as a mesh node — include it in node_count.
        isNode[i] = true;
        updateConnectionCount();
        broadcastNodeCount();
      }else if (msg == "HEARTBEAT"){
        continue;
      }else{
        // Anything else => treat as a generic script, not a mesh peer.
        isNode[i] = false;
      }

    }

  }

  // Periodic refresh so freshly-attached clients learn the count even if nothing changed.
  static unsigned long lastBroadcast = 0;
  if (millis() - lastBroadcast > 5000) {
    updateConnectionCount();
    broadcastNodeCount();
    lastBroadcast = millis();
  }

}



void loopClient() {
  // Reconnect on drop. 192.168.4.1 is the ESP32 softAP's default gateway.
  if (!hostConnection.connected()) {
    Serial.println("Lost connection to host, retrying...");
    if (hostConnection.connect("192.168.4.1", port)) {
      hostConnection.println("NODE");  // Re-announce identity on every (re)connect
    }
    delay(1000);
    return;
  }

  // Heartbeat every 3s — host's timeout is 10s.
  static unsigned long lastSend = 0;
  if (millis() - lastSend > 3000) {
    hostConnection.println("HEARTBEAT");
    lastSend = millis();
  }
}

void setup() {
  Serial.begin(9600);
  // Reset radio to a clean STA state before scanning, otherwise stale config can
  // make WiFi.scanNetworks() miss the AP we're looking for.
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  Serial.println("About to scan for network...");
  if(networkExists()){
    Serial.println("Found network");
    startAsClient();
    Serial.println("Connected to network");
  }else{
    // No host out there — become one. APSTA so we could still scan if needed later.
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


