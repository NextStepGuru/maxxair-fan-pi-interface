// WattCycle BLE battery reader: 48V packs -> coach MQTT + Victron Cerbo JSON.
//
// Two boards load-balance the six packs (3 each, set via WATT_BATTERY_FIRST/
// WATT_BATTERY_LAST + WATT_BOARD_ID in platformio.ini). Boards connect
// directly by address (no scan round), poll their packs, and publish:
//   coach broker  N/wattcycle48ble/battery/<1..6>/<Path>  {"value": ...}
//                 .../System/Cells + System/CellTemps     {"value": [..]}
// (A relay on the Maxxair Pi republishes per-battery JSON to the Cerbo
// broker for venus-os_dbus-mqtt-battery; the ESP keeps a single MQTT
// connection so WiFi/BLE share the radio kindly.)
//
// Protocol (community RE of the WattCycle APK, XDZN TDT):
//   - write "HiLink" to FFFA after connecting
//   - TDT frames to FFF2 write-without-response:
//     [head][0x00][0x01][0x03][dp:2][0x0000][crc16-modbus BE][0x0d]
//     head 0x7E on current firmware (0x1E older batches, tried as fallback)
//   - responses on FFF1, total length = payload_len + 11, payload at offset 8

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <NimBLEDevice.h>

#include "secrets.h"

#ifndef WATT_BOARD_ID
#define WATT_BOARD_ID "a"
#endif
#ifndef WATT_BATTERY_FIRST
#define WATT_BATTERY_FIRST 1
#endif
#ifndef WATT_BATTERY_LAST
#define WATT_BATTERY_LAST 6
#endif

static const char *kBoard = WATT_BOARD_ID;
static const int kFirst = WATT_BATTERY_FIRST;  // 1-based, inclusive
static const int kLast = WATT_BATTERY_LAST;

static const char *kWifiSsid = WIFI_SSID;
static const char *kWifiPassword = WIFI_PASSWORD;
static const char *kCoachHost = "192.168.10.126";
static const uint16_t kBrokerPort = 1883;
static char kMqttClientId[48];
static const char *kTopicPrefix = "N/wattcycle48ble/battery/";
static const char *kCerboPrefix = "wattcycle48ble/bat0";

static const char *kBatteryMacs[] = {
    "c0:d6:3c:5f:4e:08",  // bat01
    "c0:d6:3c:5e:21:b0",  // bat02
    "c0:d6:3c:5f:68:a9",  // bat03
    "c0:d6:3c:5f:69:50",  // bat04
    "c0:d6:3c:5e:20:50",  // bat05
    "c0:d6:3c:5f:66:60",  // bat06
};
static const char *kBatteryNames[] = {"bat01", "bat02", "bat03",
                                      "bat04", "bat05", "bat06"};
static const int kBatteryCount = 6;

static const char *kChNotify = "0000fff1-0000-1000-8000-00805f9b34fb";
static const char *kChWrite = "0000fff2-0000-1000-8000-00805f9b34fb";
static const char *kChAuth = "0000fffa-0000-1000-8000-00805f9b34fb";

static const uint8_t kFrameTail = 0x0d;
static const uint16_t kDpAnalog = 0x008c;
static const uint16_t kDpProduct = 0x0092;
static const uint32_t kHeartbeatMs = 30000;
static const uint32_t kFrameTimeoutMs = 4000;

struct BatteryData {
  bool valid;
  float voltage;
  float current;
  float soc;
  float soh;
  bool hasSoh;
  float remainingAh;
  float totalAh;
  float designAh;
  uint16_t cycles;
  float cellV[16];
  int nCells;
  float mosTemp;
  float pcbTemp;
  float cellTemp[6];
  int nCellTemps;
  char model[21];
  char manufacturer[21];
  char serial[21];
  uint32_t updatedAt;
};
static BatteryData sData[kBatteryCount];

static WiFiClient sCoachWifi;
static PubSubClient sCoach(sCoachWifi);

// ---- TDT framing ---------------------------------------------------------

static uint16_t modbusCrc(const uint8_t *buf, size_t n) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < n; i++) {
    crc ^= buf[i];
    for (int b = 0; b < 8; b++) {
      crc = (crc & 1) ? (crc >> 1) ^ 0xa001 : crc >> 1;
    }
  }
  return crc;
}

static size_t buildReadFrame(uint8_t head, uint16_t dp, uint8_t *out) {
  out[0] = head;
  out[1] = 0x00;
  out[2] = 0x01;
  out[3] = 0x03;
  out[4] = dp >> 8;
  out[5] = dp & 0xff;
  out[6] = 0x00;
  out[7] = 0x00;
  uint16_t crc = modbusCrc(out, 8);
  out[8] = crc >> 8;
  out[9] = crc & 0xff;
  out[10] = kFrameTail;
  return 11;
}

struct Assembler {
  uint8_t buf[256];
  size_t len;
  size_t expected;
  bool complete;

  void reset() {
    len = 0;
    expected = 0;
    complete = false;
  }

  void feed(const uint8_t *data, size_t n) {
    if (complete || len + n > sizeof(buf)) return;
    memcpy(buf + len, data, n);
    len += n;
    if (expected == 0 && len >= 8) {
      expected = ((buf[6] << 8) | buf[7]) + 11;
      if (expected > sizeof(buf)) expected = sizeof(buf);
    }
    if (expected && len >= expected) complete = true;
  }

  bool payload(uint8_t **out, size_t *outLen) {
    if (!complete || (buf[0] != 0x7e && buf[0] != 0x1e)) return false;
    size_t dataLen = expected - 11;
    if (buf[len - 1] != kFrameTail) return false;
    *out = buf + 8;
    *outLen = dataLen;
    return true;
  }
};

static Assembler sAssembler;

static void notifyCb(NimBLERemoteCharacteristic *ch, uint8_t *data, size_t len,
                     bool isNotify) {
  (void)ch;
  (void)isNotify;
  sAssembler.feed(data, len);
}

// ---- payload parsing -----------------------------------------------------

static float parseCurrent(const uint8_t *d) {
  bool neg = d[0] & 0x80;
  bool dec = d[0] & 0x40;
  float raw = d[1] | ((d[0] & 0x3f) << 8);
  float val = dec ? raw / 10.0f : raw;
  return neg ? -val : val;
}

static bool parseAnalog(const uint8_t *p, size_t n, BatteryData &out) {
  size_t o = 0;
  if (n < 2) return false;
  int nCells = p[o++];
  if (nCells < 1 || nCells > 16) return false;
  out.nCells = nCells;
  for (int i = 0; i < nCells; i++) {
    if (o + 2 > n) return false;
    out.cellV[i] = ((p[o] << 8) | p[o + 1]) / 1000.0f;
    o += 2;
  }
  if (o + 1 > n) return false;
  int nTemps = p[o++];
  if (o + 4 > n) return false;
  out.mosTemp = (((p[o] << 8) | p[o + 1]) - 2730) / 10.0f;
  o += 2;
  out.pcbTemp = (((p[o] << 8) | p[o + 1]) - 2730) / 10.0f;
  o += 2;
  out.nCellTemps = 0;
  for (int i = 0; i < nTemps - 2 && i < 6; i++) {
    if (o + 2 > n) return false;
    out.cellTemp[out.nCellTemps++] = (((p[o] << 8) | p[o + 1]) - 2730) / 10.0f;
    o += 2;
  }
  if (o + 14 > n) return false;
  out.current = parseCurrent(p + o);
  o += 2;
  out.voltage = ((p[o] << 8) | p[o + 1]) / 100.0f;
  o += 2;
  out.remainingAh = ((p[o] << 8) | p[o + 1]) / 10.0f;
  o += 2;
  out.totalAh = ((p[o] << 8) | p[o + 1]) / 10.0f;
  o += 2;
  out.cycles = (p[o] << 8) | p[o + 1];
  o += 2;
  out.designAh = ((p[o] << 8) | p[o + 1]) / 10.0f;
  o += 2;
  out.soc = (p[o] << 8) | p[o + 1];
  o += 2;
  if (n - o >= 18) {
    out.hasSoh = true;
    out.soh = ((p[o] << 8) | p[o + 1]);
  }
  return true;
}

static void trimCopy(char *dst, size_t dstSize, const uint8_t *src, size_t m) {
  size_t k = 0;
  for (size_t i = 0; i < m && k < dstSize - 1; i++) {
    if (src[i] == 0 || src[i] == ' ') break;
    dst[k++] = (char)src[i];
  }
  dst[k] = 0;
}

static bool parseProduct(const uint8_t *p, size_t n, BatteryData &out) {
  if (n != 60) return false;
  trimCopy(out.model, sizeof(out.model), p, 20);
  trimCopy(out.manufacturer, sizeof(out.manufacturer), p + 20, 20);
  trimCopy(out.serial, sizeof(out.serial), p + 40, 20);
  return true;
}

// ---- BLE read ------------------------------------------------------------

struct FoundDevice {
  NimBLEAddress addr;
  uint8_t type;
  bool seen;
};
static FoundDevice sFound[kBatteryCount];

class ScanCb : public NimBLEAdvertisedDeviceCallbacks {
  void onResult(NimBLEAdvertisedDevice *dev) override {
    String mac = dev->getAddress().toString().c_str();
    for (int i = 0; i < kBatteryCount; i++) {
      if (mac.equalsIgnoreCase(kBatteryMacs[i]) && !sFound[i].seen) {
        sFound[i].addr = dev->getAddress();
        sFound[i].type = dev->getAddressType();
        sFound[i].seen = true;
        Serial.printf("scan: %s rssi=%d\n", kBatteryNames[i], dev->getRSSI());
      }
    }
  }
};

// Blocks up to timeoutMs waiting for one notification frame.
static bool waitFrame(uint32_t timeoutMs) {
  uint32_t until = millis() + timeoutMs;
  while (!sAssembler.complete && millis() < until) {
    sCoach.loop();
    delay(20);
  }
  return sAssembler.complete;
}

static bool readDp(NimBLERemoteCharacteristic *writeCh, uint8_t head,
                   uint16_t dp, BatteryData &out, bool product) {
  uint8_t frame[11];
  buildReadFrame(head, dp, frame);
  sAssembler.reset();
  if (!writeCh->writeValue(frame, 11, false)) return false;
  if (!waitFrame(kFrameTimeoutMs)) return false;
  uint8_t *payload;
  size_t payloadLen;
  if (!sAssembler.payload(&payload, &payloadLen)) return false;
  return product ? parseProduct(payload, payloadLen, out)
                 : parseAnalog(payload, payloadLen, out);
}

class ClientCb : public NimBLEClientCallbacks {
  void onDisconnect(NimBLEClient *c) override {
    Serial.printf("    link lost, reason=%d\n", c->getLastError());
  }
};

static bool readBattery(int idx) {
  NimBLEClient *client = NimBLEDevice::createClient();
  static ClientCb sClientCb;
  client->setClientCallbacks(&sClientCb, false);
  client->setConnectTimeout(10);
  bool connected = false;
  for (int attempt = 0; attempt < 2 && !connected; attempt++) {
    if (attempt > 0) delay(400);
    if (sFound[idx].seen) {
      // Connecting via the advertised device (right address type, actively
      // advertising now) succeeds far more often than a blind connect.
      connected = client->connect(sFound[idx].addr, sFound[idx].type);
    }
    if (!connected) {
      connected = client->connect(NimBLEAddress(kBatteryMacs[idx]),
                                  BLE_ADDR_RANDOM);
    }
  }
  if (!connected) {
    Serial.printf("  %s connect failed (lastError=%d)\n", kBatteryNames[idx],
                  client->getLastError());
  }
  bool ok = false;
  if (connected) {
    // NOTE: do not request a shorter connection interval here — these packs
    // drop the link when the central asks for 10-12.5ms post-connect.
    delay(100);
    std::vector<NimBLERemoteService *> *services = client->getServices(true);
    NimBLERemoteCharacteristic *notifyCh = nullptr, *writeCh = nullptr,
                               *authCh = nullptr;
    for (NimBLERemoteService *s : *services) {
      for (NimBLERemoteCharacteristic *c : *s->getCharacteristics(true)) {
        String u = String(c->getUUID().toString().c_str());
        u.toUpperCase();
        if (u.indexOf("FFF1") != -1) notifyCh = c;
        if (u.indexOf("FFF2") != -1) writeCh = c;
        if (u.indexOf("FFFA") != -1) authCh = c;
      }
    }
    if (!notifyCh || !writeCh || !authCh) {
      Serial.printf("  %s fff1/fff2/fffa missing\n", kBatteryNames[idx]);
    } else if (!notifyCh->subscribe(true, notifyCb, true)) {
      Serial.printf("  %s subscribe failed\n", kBatteryNames[idx]);
    } else {
      authCh->writeValue((const uint8_t *)"HiLink", 6, true);
      delay(300);
      BatteryData &d = sData[idx];
      memset(&d, 0, sizeof(d));
      d.nCells = -1;
      bool product = readDp(writeCh, 0x7e, kDpProduct, d, true);
      if (!product) product = readDp(writeCh, 0x1e, kDpProduct, d, true);
      d.nCells = -1;
      bool analog = readDp(writeCh, 0x7e, kDpAnalog, d, false);
      if (!analog) analog = readDp(writeCh, 0x1e, kDpAnalog, d, false);
      if (analog && d.nCells > 0) {
        d.valid = true;
        d.updatedAt = millis();
        ok = true;
      }
      notifyCh->subscribe(false, nullptr, true);
    }
  }
  if (client->isConnected()) client->disconnect();
  NimBLEDevice::deleteClient(client);
  return ok;
}

// ---- MQTT ----------------------------------------------------------------

static bool coachPublishChanged(const char *topic, const String &json,
                                String &last, bool heartbeat) {
  if (json == last && !heartbeat) return true;
  char payload[192];
  snprintf(payload, sizeof(payload), "{\"value\":%s}", json.c_str());
  bool ok = sCoach.publish(topic, payload, true);
  last = json;
  return ok;
}

static void publishBattery(int idx) {
  static String last[kBatteryCount][17];
  static uint32_t lastPublish[kBatteryCount] = {0};
  BatteryData &d = sData[idx];
  if (!d.valid) return;
  bool changed = last[idx][0] != String(d.voltage, 2);
  uint32_t now = millis();
  bool heartbeat = lastPublish[idx] != 0 && now - lastPublish[idx] >= kHeartbeatMs;
  if (!changed && !heartbeat && lastPublish[idx] != 0) return;

  char base[64];
  snprintf(base, sizeof(base), "%s%d/", kTopicPrefix, idx + 1);
  char topic[112];

  struct Val {
    const char *path;
    String json;
  } vals[13] = {
      {"Dc/0/Voltage", String(d.voltage, 2)},
      {"Dc/0/Current", String(d.current, 1)},
      {"Soc", String((int)d.soc)},
      {"Capacity", String(d.totalAh, 1)},
      {"DesignCapacity", String(d.designAh, 1)},
      {"RemainingCapacity", String(d.remainingAh, 1)},
      {"Cycles", String(d.cycles)},
      {"Dc/0/Temperature", String(d.mosTemp, 1)},
      {"PcbTemperature", String(d.pcbTemp, 1)},
      {"ProductName", String("\"") + d.model + "\""},
      {"CustomName", String("\"") + kBatteryNames[idx] + "\""},
      {"Serial", String("\"") + d.serial + "\""},
      {"Connected", "1"},
  };
  int n = 0;
  for (int i = 0; i < 13; i++) {
    snprintf(topic, sizeof(topic), "%s%s", base, vals[i].path);
    if (coachPublishChanged(topic, vals[i].json, last[idx][i], heartbeat)) n++;
  }
  if (d.hasSoh) {
    snprintf(topic, sizeof(topic), "%sSoh", base);
    coachPublishChanged(topic, String((int)d.soh), last[idx][13], heartbeat);
  }

  if (d.nCells > 0) {
    float mn = d.cellV[0], mx = d.cellV[0];
    for (int i = 1; i < d.nCells; i++) {
      mn = min(mn, d.cellV[i]);
      mx = max(mx, d.cellV[i]);
    }
    String cells = "[";
    for (int i = 0; i < d.nCells; i++) {
      cells += String(d.cellV[i], 3);
      if (i < d.nCells - 1) cells += ",";
    }
    cells += "]";
    snprintf(topic, sizeof(topic), "%sSystem/Cells", base);
    static String lastCells[kBatteryCount];
    coachPublishChanged(topic, cells, lastCells[idx], heartbeat);

    snprintf(topic, sizeof(topic), "%sSystem/MinCellVoltage", base);
    coachPublishChanged(topic, String(mn, 3), last[idx][14], heartbeat);
    snprintf(topic, sizeof(topic), "%sSystem/MaxCellVoltage", base);
    coachPublishChanged(topic, String(mx, 3), last[idx][15], heartbeat);
    snprintf(topic, sizeof(topic), "%sInfo/ModuleCount", base);
    coachPublishChanged(topic, String(d.nCells), last[idx][16], heartbeat);
    if (d.nCellTemps > 0) {
      String temps = "[";
      for (int i = 0; i < d.nCellTemps; i++) {
        temps += String(d.cellTemp[i], 1);
        if (i < d.nCellTemps - 1) temps += ",";
      }
      temps += "]";
      snprintf(topic, sizeof(topic), "%sSystem/CellTemps", base);
      static String lastTemps[kBatteryCount];
      coachPublishChanged(topic, temps, lastTemps[idx], heartbeat);
    }
  }
  lastPublish[idx] = now;
}

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  char hostname[32];
  snprintf(hostname, sizeof(hostname), "wattcycle-reader-%s", kBoard);
  WiFi.setHostname(hostname);
  WiFi.mode(WIFI_STA);
  WiFi.begin(kWifiSsid, kWifiPassword);
  Serial.printf("wifi connecting to %s", kWifiSsid);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("wifi up: %s rssi %d\n", WiFi.localIP().toString().c_str(),
                  WiFi.RSSI());
  }
}

static void connectBrokers() {
  static uint32_t lastAttempt = 0;
  if (sCoach.connected() || millis() - lastAttempt < 5000) return;
  lastAttempt = millis();
  sCoach.setServer(kCoachHost, kBrokerPort);
  if (sCoach.connect(kMqttClientId)) {
    Serial.println("coach mqtt connected");
  } else {
    Serial.printf("coach mqtt failed rc=%d\n", sCoach.state());
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  uint64_t mac = ESP.getEfuseMac();
  Serial.printf("\nwattcycle-reader board %s (esp32-s3 %02x%08x) packs %d-%d\n",
                kBoard, (uint16_t)(mac >> 32), (uint32_t)mac, kFirst, kLast);
  snprintf(kMqttClientId, sizeof(kMqttClientId), "wattcycle48ble-%s", kBoard);
  connectWifi();
  connectBrokers();
  NimBLEDevice::init(kMqttClientId);
  NimBLEScan *scan = NimBLEDevice::getScan();
  scan->setAdvertisedDeviceCallbacks(new ScanCb(), true);
  scan->setActiveScan(true);
  scan->setInterval(100);
  scan->setWindow(100);
#if WATT_STAGGER_MS > 0
  Serial.printf("staggering start by %d ms\n", WATT_STAGGER_MS);
  delay(WATT_STAGGER_MS);
#endif
  Serial.println("nimble ready");
}

void loop() {
  connectWifi();
  connectBrokers();

  for (int i = 0; i < kBatteryCount; i++) sFound[i] = {};
  NimBLEScan *scan = NimBLEDevice::getScan();
  scan->start(8, false);
  uint32_t scanEnd = millis() + 8000;
  while (millis() < scanEnd) {
    sCoach.loop();
    delay(40);
  }
  scan->stop();

  for (int idx = kFirst - 1; idx <= kLast - 1; idx++) {
    sCoach.loop();
    if (readBattery(idx)) {
      publishBattery(idx);
    }
    sCoach.loop();
    delay(200);
  }
  delay(1000);
}
