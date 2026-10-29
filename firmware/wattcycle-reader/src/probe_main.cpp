// BLE probe for the Wattcycle batteries, round 2.
// The GATT layout is FFF0 (fff1 notify / fff2 write) + vendor 02f00000-fe00
// (ff01 write / ff02 notify), not the classic JBD FF00 pipe. This probe
// subscribes to every notify characteristic, then sweeps every write
// characteristic with a JBD basic-info request to find the live pipe.
// Run via `pio run -e ble-probe`; build_src_filter keeps main.cpp out.

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEUtils.h>
#include <vector>

// bat01..bat06 from the Wattcycle app (user-confirmed MACs).
static const char *kMacs[] = {
    "c0:d6:3c:5f:4e:08",  // bat01
    "c0:d6:3c:5e:21:b0",  // bat02
    "c0:d6:3c:5f:68:a9",  // bat03
    "c0:d6:3c:5f:69:50",  // bat04
    "c0:d6:3c:5e:20:50",  // bat05
    "c0:d6:3c:5f:66:60",  // bat06
};
static const int kMacCount = sizeof(kMacs) / sizeof(kMacs[0]);

static BLEAdvertisedDevice *sFound[kMacCount];
static BLEClient *sClients[kMacCount];
static BLEScan *sScan;

static String hex(const uint8_t *d, size_t n) {
  String out;
  char buf[3];
  for (size_t i = 0; i < n; i++) {
    snprintf(buf, sizeof(buf), "%02x", d[i]);
    out += buf;
  }
  return out;
}

// CRC16-XMODEM (poly 0x1021, init 0) as used by JBD frames.
static uint16_t jbdCrc(const uint8_t *d, size_t n) {
  uint16_t crc = 0;
  for (size_t i = 0; i < n; i++) {
    crc ^= (uint16_t)d[i] << 8;
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : (crc << 1);
    }
  }
  return crc;
}

static size_t jbdFrame(uint8_t cmd, uint8_t *out) {
  out[0] = 0xA5;
  out[1] = 0x08;
  out[2] = cmd;
  memset(out + 3, 0, 9);
  uint16_t crc = jbdCrc(out, 12);
  out[12] = crc & 0xFF;
  out[13] = crc >> 8;
  return 14;
}

static volatile int sNotifyCount = 0;

static void shortUuid(BLERemoteCharacteristic *ch, char *out, size_t n) {
  String u = ch->getUUID().toString().c_str();
  u.toUpperCase();
  int fe = u.indexOf("FE00");  // vendor 128-bit base
  if (fe > 0) {
    snprintf(out, n, "v%s", u.substring(fe - 4, fe).c_str());
  } else if (u.length() >= 8) {
    snprintf(out, n, "%s", u.substring(4, 8).c_str());
  } else {
    snprintf(out, n, "%s", u.c_str());
  }
}

static void notifyCb(BLERemoteCharacteristic *ch, uint8_t *data, size_t len,
                     bool isNotify) {
  (void)isNotify;
  char tag[12];
  shortUuid(ch, tag, sizeof(tag));
  sNotifyCount++;
  Serial.printf("    [%s] <- %s\n", tag, hex(data, len).c_str());
  if (len >= 4 && data[0] == 0xA5) {
    Serial.printf("    [%s] frame: start=%02x len=0x%02x cmd=0x%02x\n", tag,
                  data[0], data[1], data[2]);
    if (data[2] == 0x03 && len >= 27) {
      uint16_t volts = data[4] | (data[5] << 8);
      int16_t amps = data[6] | (data[7] << 8);
      uint16_t residual = data[8] | (data[9] << 8);
      uint16_t nominal = data[10] | (data[11] << 8);
      uint16_t cycles = data[12] | (data[13] << 8);
      uint8_t soc = data[23];
      uint8_t fet = data[24];
      uint8_t cells = data[25];
      uint8_t ntc = data[26];
      Serial.printf("    [%s] parse: %.2fV %.1fA residual=%umAh nominal=%umAh "
                    "cycles=%u soc=%u%% fet=0x%02x cells=%u ntc=%u\n",
                    tag, volts / 100.0, amps / 10.0, residual * 10, nominal * 10,
                    cycles, soc, fet, cells, ntc);
    }
  }
}

static void probeOne(int idx) {
  Serial.printf("\n===== bat%02d %s =====\n", idx + 1, kMacs[idx]);
  BLEClient *client = sClients[idx];
  if (client == nullptr) {
    client = sClients[idx] = BLEDevice::createClient();
  }
  Serial.printf("  connecting (addrType=%d)...\n", sFound[idx]->getAddressType());
  if (!client->connect(sFound[idx])) {
    Serial.println("  connect FAILED");
    return;
  }
  Serial.println("  connected, discovering GATT...");
  // Only touch vendor/BMS pipes: never write to GAP (2A00 is the device name).
  std::vector<BLERemoteCharacteristic *> notifyChars;
  std::vector<BLERemoteCharacteristic *> writeChars;
  for (auto svc : *client->getServices()) {
    String svcId = svc.first.c_str();
    bool stdSvc = svcId.startsWith("00001800") || svcId.startsWith("00001801");
    Serial.printf("  svc %s\n", svc.first.c_str());
    for (auto ch : *svc.second->getCharacteristics()) {
      char tag[12];
      shortUuid(ch.second, tag, sizeof(tag));
      Serial.printf("    ch %s handle=%u%s%s%s%s\n", tag,
                    ch.second->getHandle(), ch.second->canRead() ? " read" : "",
                    ch.second->canWriteNoResponse() ? " writeNR" : "",
                    ch.second->canWrite() ? " write" : "",
                    ch.second->canNotify() ? " notify" : "");
      if (stdSvc) continue;
      if (ch.second->canNotify()) notifyChars.push_back(ch.second);
      if (ch.second->canWrite() || ch.second->canWriteNoResponse())
        writeChars.push_back(ch.second);
    }
  }

  for (auto ch : notifyChars) {
    ch->registerForNotify(notifyCb);
  }

  // Sweep every write pipe with a JBD basic-info request.
  for (auto ch : writeChars) {
    char tag[12];
    shortUuid(ch, tag, sizeof(tag));
    uint8_t frame[14];
    jbdFrame(0x03, frame);
    Serial.printf("  -> [%s] cmd 0x03: %s\n", tag, hex(frame, 14).c_str());
    sNotifyCount = 0;
    ch->writeValue(frame, 14, false);
    uint32_t waitUntil = millis() + 1500;
    while (sNotifyCount == 0 && millis() < waitUntil) delay(50);
    if (sNotifyCount == 0) Serial.printf("    [%s] no response\n", tag);
    delay(200);
  }

  delay(1000);

  // Single readValue() per readable vendor characteristic, last so a flaky
  // read can't block the write sweep.
  for (auto svc : *client->getServices()) {
    String svcId = svc.first.c_str();
    if (svcId.startsWith("00001800") || svcId.startsWith("00001801")) continue;
    for (auto ch : *svc.second->getCharacteristics()) {
      if (!ch.second->canRead()) continue;
      char tag[12];
      shortUuid(ch.second, tag, sizeof(tag));
      std::string v = ch.second->readValue();
      delay(150);
      Serial.printf("    read [%s] = %s\n", tag,
                    hex((const uint8_t *)v.data(), v.size()).c_str());
    }
  }

  for (auto ch : notifyChars) ch->registerForNotify(nullptr);
  client->disconnect();
  Serial.println("  done");
}

class ScanCb : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice dev) override {
    String mac = dev.getAddress().toString().c_str();
    for (int i = 0; i < kMacCount; i++) {
      if (mac.equalsIgnoreCase(kMacs[i]) && sFound[i] == nullptr) {
        sFound[i] = new BLEAdvertisedDevice(dev);
        Serial.printf("found bat%02d %s rssi=%d name=%s\n", i + 1, kMacs[i],
                      dev.getRSSI(), dev.haveName() ? dev.getName().c_str() : "");
      }
    }
  }
};

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nble probe up");
  BLEDevice::init("wattcycle-probe");
  sScan = BLEDevice::getScan();
  sScan->setAdvertisedDeviceCallbacks(new ScanCb(), false);
  sScan->setActiveScan(true);
  sScan->setInterval(100);
  sScan->setWindow(100);
}

void loop() {
  for (int i = 0; i < kMacCount; i++) sFound[i] = nullptr;
  Serial.println("\nscanning 10s for batteries...");
  sScan->start(15, false);
  int hits = 0;
  for (int i = 0; i < kMacCount; i++) {
    if (sFound[i] != nullptr) {
      hits++;
      probeOne(i);
      delete sFound[i];
      sFound[i] = nullptr;
      delay(500);
    }
  }
  if (hits == 0) Serial.println("no batteries advertising this pass");
  Serial.printf("===== pass done, %d battery(ies) probed =====\n", hits);
  delay(10000);
}
