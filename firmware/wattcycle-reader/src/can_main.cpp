// WattCycle pack reader: Pylontech-CAN (500 kbps) -> coach MQTT.//
// Mirrors maxxair_fan/wattcycle.py's coach feed: decodes the PY frame set and
// publishes retained {"value": ...} JSON under N/wattcycle48/battery/1/<Path>.
// Receive-only, so it can share the bus with the Pi's CANable publisher; the
// Cerbo feed stays on the Pi.

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <driver/twai.h>

#include "secrets.h"

#ifndef WATT_CAN_TX_PIN
#define WATT_CAN_TX_PIN 4
#endif
#ifndef WATT_CAN_RX_PIN
#define WATT_CAN_RX_PIN 5
#endif

static const char *kHostname = WATT_HOSTNAME;
static const char *kWifiSsid = WIFI_SSID;
static const char *kWifiPassword = WIFI_PASSWORD;
static const char *kBrokerHost = "192.168.10.126";
static const uint16_t kBrokerPort = 1883;
static const char *kMqttClientId = "wattcycle48-esp32";
static const char *kTopicPrefix = "N/wattcycle48/battery/1/";

static const uint32_t kHeartbeatMs = 30000;   // republish held values like the Pi
static const uint32_t kSummaryMs = 5000;      // serial status cadence
static const uint32_t kDecodeMs = 1000;       // decode/publish cadence

// Pylontech frame IDs the Pi listens for.
static const uint16_t kPyIds[] = {0x351, 0x355, 0x356, 0x359, 0x35A,
                                  0x35C, 0x35E, 0x370, 0x371, 0x373, 0x379};
static const size_t kPyIdCount = sizeof(kPyIds) / sizeof(kPyIds[0]);

struct PyFrame {
  uint8_t data[8];
  uint8_t len;
  bool seen;
};

static PyFrame sFrames[kPyIdCount];
static uint32_t sFramesSeen = 0;

static WiFiClient sWifi;
static PubSubClient sMqtt(sWifi);

static int pyIndex(uint16_t id) {
  for (size_t i = 0; i < kPyIdCount; i++) {
    if (kPyIds[i] == id) return (int)i;
  }
  return -1;
}

static uint16_t u16(const uint8_t *d, int i) {
  return (uint16_t)(d[i] | (d[i + 1] << 8));
}

static int16_t s16(const uint8_t *d, int i) { return (int16_t)u16(d, i); }

// One decoded value: topic path + JSON payload body (the "value" field).
struct Value {
  const char *path;
  String json;  // e.g. "53.28", "100", "\"PYLO\""
};

static void addName(Value *out, int *n, const char *path, const char *text) {
  out[*n].path = path;
  out[*n].json = String("\"") + text + "\"";
  (*n)++;
}

static String num(double v, int decimals) {
  return String(v, decimals);
}

// Mirror of wattcycle.py decode_pack: missing frames stay omitted.
static int decodePack(Value *out) {
  int n = 0;
  addName(out, &n, "ProductName", "PYLO");
  addName(out, &n, "CustomName", "WattCycle");
  out[n].path = "Connected";
  out[n++].json = "1";

  const PyFrame &limits = sFrames[pyIndex(0x351)];
  if (limits.seen && limits.len >= 8) {
    out[n].path = "Info/MaxChargeVoltage";    out[n++].json = num(u16(limits.data, 0) / 10.0, 1);
    out[n].path = "Info/MaxChargeCurrent";    out[n++].json = num(u16(limits.data, 2) / 10.0, 1);
    out[n].path = "Info/MaxDischargeCurrent"; out[n++].json = num(u16(limits.data, 4) / 10.0, 1);
    out[n].path = "Info/BatteryLowVoltage";   out[n++].json = num(u16(limits.data, 6) / 10.0, 1);
  }
  const PyFrame &soc = sFrames[pyIndex(0x355)];
  if (soc.seen && soc.len >= 4) {
    out[n].path = "Soc"; out[n++].json = String(u16(soc.data, 0));
    out[n].path = "Soh"; out[n++].json = String(u16(soc.data, 2));
  }
  const PyFrame &meas = sFrames[pyIndex(0x356)];
  if (meas.seen && meas.len >= 6) {
    out[n].path = "Dc/0/Voltage";     out[n++].json = num(u16(meas.data, 0) / 100.0, 2);
    out[n].path = "Dc/0/Current";     out[n++].json = num(s16(meas.data, 2) / 10.0, 1);
    out[n].path = "Dc/0/Temperature"; out[n++].json = num(s16(meas.data, 4) / 10.0, 1);
  }
  const PyFrame &status = sFrames[pyIndex(0x359)];
  if (status.seen && status.len >= 5) {
    out[n].path = "Info/ModuleCount";
    out[n++].json = String(status.data[4]);
    bool alarm = status.data[0] || status.data[1] || status.data[2] || status.data[3];
    out[n].path = "Alarms/Alarm"; out[n++].json = alarm ? "1" : "0";
  }
  const PyFrame &flags = sFrames[pyIndex(0x35C)];
  if (flags.seen && flags.len >= 1) {
    out[n].path = "Info/ChargeRequest";    out[n++].json = (flags.data[0] & 0x80) ? "1" : "0";
    out[n].path = "Info/DischargeRequest"; out[n++].json = (flags.data[0] & 0x40) ? "1" : "0";
  }
  // 0x370 holds the first name half, 0x371 the second; python concatenates
  // both then stops at the first NUL.
  const PyFrame &n0 = sFrames[pyIndex(0x370)];
  const PyFrame &n1 = sFrames[pyIndex(0x371)];
  if (n0.seen || n1.seen) {
    char full[17] = {0};
    size_t f = 0;
    for (int i = 0; i < 8 && f < sizeof(full) - 1 && n0.seen; i++) {
      if (n0.data[i] == 0) break;
      full[f++] = (char)n0.data[i];
    }
    for (int i = 0; i < 8 && f < sizeof(full) - 1 && n1.seen; i++) {
      if (n1.data[i] == 0) break;
      full[f++] = (char)n1.data[i];
    }
    if (f > 0) {
      addName(out, &n, "ProductName", full);
      addName(out, &n, "CustomName", full);
    }
  }
  const PyFrame &name = sFrames[pyIndex(0x35E)];
  if (name.seen) {
    char text[9] = {0};
    for (int i = 0; i < 8; i++) {
      if (name.data[i] == 0) break;
      text[i] = (char)name.data[i];
    }
    if (text[0]) addName(out, &n, "ProductName", text);
  }
  const PyFrame &cells = sFrames[pyIndex(0x373)];
  if (cells.seen && cells.len >= 8 && (u16(cells.data, 0) || u16(cells.data, 2))) {
    out[n].path = "System/MinCellVoltage";    out[n++].json = num(u16(cells.data, 0) / 1000.0, 3);
    out[n].path = "System/MaxCellVoltage";    out[n++].json = num(u16(cells.data, 2) / 1000.0, 3);
    out[n].path = "System/MinCellTemperature"; out[n++].json = String((int)u16(cells.data, 4) - 273);
    out[n].path = "System/MaxCellTemperature"; out[n++].json = String((int)u16(cells.data, 6) - 273);
  }
  const PyFrame &cap = sFrames[pyIndex(0x379)];
  if (cap.seen && cap.len >= 2) {
    out[n].path = "Capacity"; out[n++].json = String(u16(cap.data, 0));
  }
  return n;
}

static bool publishValues(const Value *values, int count) {
  static String lastPayload[32];
  static const char *lastPath[32];
  static int lastCount = 0;
  static uint32_t lastPublishMs = 0;

  bool changed = count != lastCount;
  if (!changed) {
    for (int i = 0; i < count; i++) {
      if (strcmp(values[i].path, lastPath[i]) != 0 || values[i].json != lastPayload[i]) {
        changed = true;
        break;
      }
    }
  }
  uint32_t now = millis();
  if (!changed && lastCount > 0 && now - lastPublishMs < kHeartbeatMs) {
    return true;
  }

  char topic[96];
  char payload[64];
  int ok = 0;
  for (int i = 0; i < count; i++) {
    snprintf(topic, sizeof(topic), "%s%s", kTopicPrefix, values[i].path);
    snprintf(payload, sizeof(payload), "{\"value\":%s}", values[i].json.c_str());
    if (sMqtt.publish(topic, payload, true)) {
      ok++;
    } else {
      Serial.printf("publish failed: %s\n", topic);
    }
  }
  for (int i = 0; i < count; i++) {
    lastPath[i] = values[i].path;
    lastPayload[i] = values[i].json;
  }
  lastCount = count;
  lastPublishMs = now;
  Serial.printf("published %d/%d topics (%s)\n", ok, count,
                changed ? "changed" : "heartbeat");
  return ok == count;
}

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.setHostname(kHostname);
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
  } else {
    Serial.println("wifi failed, retrying");
  }
}

static void connectMqtt() {
  static uint32_t lastAttempt = 0;
  if (sMqtt.connected() || millis() - lastAttempt < 5000) return;
  lastAttempt = millis();
  sMqtt.setServer(kBrokerHost, kBrokerPort);
  Serial.printf("mqtt connecting to %s:%u\n", kBrokerHost, kBrokerPort);
  if (sMqtt.connect(kMqttClientId)) {
    Serial.println("mqtt connected");
  } else {
    Serial.printf("mqtt failed rc=%d\n", sMqtt.state());
  }
}

static void printSummary(uint32_t framesSeen) {
  Value values[32];
  int n = decodePack(values);
  Serial.printf("[%lu frames] ", (unsigned long)framesSeen);
  for (int i = 0; i < n; i++) {
    Serial.printf("%s=%s ", values[i].path, values[i].json.c_str());
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(300);
  uint64_t mac = ESP.getEfuseMac();
  Serial.printf("\nwattcycle-reader up (esp32-s3 %02x%08x)\n",
                (uint16_t)(mac >> 32), (uint32_t)mac);
  Serial.printf("can: twai rx=%d tx=%d @500kbps, receive-only\n",
                WATT_CAN_RX_PIN, WATT_CAN_TX_PIN);
  Serial.println("wire an SN65HVD230: TXD->GPIO4, RXD->GPIO5, CANH/CANL to pack");

  twai_general_config_t g_config = TWAI_GENERAL_CONFIG_DEFAULT(
      (gpio_num_t)WATT_CAN_TX_PIN, (gpio_num_t)WATT_CAN_RX_PIN,
      TWAI_MODE_NORMAL);
  twai_timing_config_t t_config = TWAI_TIMING_CONFIG_500KBITS();
  twai_filter_config_t f_config = TWAI_FILTER_CONFIG_ACCEPT_ALL();
  if (twai_driver_install(&g_config, &t_config, &f_config) == ESP_OK &&
      twai_start() == ESP_OK) {
    Serial.println("twai started");
  } else {
    Serial.println("twai install/start FAILED");
  }
  twai_reconfigure_alerts(TWAI_ALERT_RX_DATA | TWAI_ALERT_TX_FAILED |
                              TWAI_ALERT_BUS_OFF | TWAI_ALERT_ERR_PASS |
                              TWAI_ALERT_ABOVE_ERR_WARN,
                          nullptr);
}

void loop() {
  static uint32_t lastDecode = 0, lastSummary = 0, lastNotice = 0;
  static uint32_t lastAlerts = 0;

  connectWifi();
  connectMqtt();

  twai_message_t message;
  if (twai_receive(&message, pdMS_TO_TICKS(10)) == ESP_OK) {
    int idx = pyIndex(message.identifier & 0x7FF);
    if (idx >= 0) {
      PyFrame &f = sFrames[idx];
      f.len = message.data_length_code > 8 ? 8 : message.data_length_code;
      memcpy(f.data, message.data, f.len);
      if (!f.seen) {
        f.seen = true;
        sFramesSeen++;
        Serial.printf("first PY frame 0x%03X (dlc=%u)\n", message.identifier,
                      message.data_length_code);
      }
    }
  }

  uint32_t now = millis();
  if (now - lastAlerts >= 5000) {
    uint32_t alerts = 0;
    twai_read_alerts(&alerts, 0);
    if (alerts) Serial.printf("twai alerts: 0x%08lX\n", (unsigned long)alerts);
    lastAlerts = now;
  }
  if (sFramesSeen == 0 && now - lastNotice >= 10000) {
    Serial.println("no PY frames yet - check CANH/CANL wiring and pack power");
    lastNotice = now;
  }
  // Stay silent on MQTT until the bus has produced a PY frame: publishing
  // Connected=1 with no data would make Abbey treat the pack as fresh.
  if (sFramesSeen > 0 && now - lastDecode >= kDecodeMs && sMqtt.connected()) {
    Value values[32];
    int n = decodePack(values);
    if (n > 0) publishValues(values, n);
    lastDecode = now;
  }
  if (now - lastSummary >= kSummaryMs) {
    printSummary(sFramesSeen);
    lastSummary = now;
  }
}
