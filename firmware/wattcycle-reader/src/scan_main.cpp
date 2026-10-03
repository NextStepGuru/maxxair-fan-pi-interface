// BLE presence timeline: which packs advertise in each 4s window.
// Gaps while a pack is otherwise healthy = something is holding a link.

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEScan.h>
#include <BLEAdvertisedDevice.h>

static const char *kMacs[] = {
    "c0:d6:3c:5f:4e:08", "c0:d6:3c:5e:21:b0", "c0:d6:3c:5f:68:a9",
    "c0:d6:3c:5f:69:50", "c0:d6:3c:5e:20:50", "c0:d6:3c:5f:66:60",
};
static const char *kNames[] = {"1", "2", "3", "4", "5", "6"};
static bool sSeen[6];
static uint32_t sStart;
static BLEScan *sScan;

class ScanCb : public BLEAdvertisedDeviceCallbacks {
  void onResult(BLEAdvertisedDevice dev) override {
    String mac = dev.getAddress().toString().c_str();
    for (int i = 0; i < 6; i++) {
      if (mac.equalsIgnoreCase(kMacs[i])) {
        sSeen[i] = true;
      }
    }
  }
};

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\npresence timeline up");
  BLEDevice::init("wc-presence");
  sScan = BLEDevice::getScan();
  sScan->setAdvertisedDeviceCallbacks(new ScanCb(), false);
  sScan->setActiveScan(true);
  sScan->setInterval(100);
  sScan->setWindow(100);
  sStart = millis();
}

void loop() {
  for (int i = 0; i < 6; i++) sSeen[i] = false;
  sScan->start(4, false);
  delay(4000);
  sScan->stop();
  String line = "";
  for (int i = 0; i < 6; i++) {
    if (sSeen[i]) line += kNames[i];
  }
  Serial.printf("t+%3lus seen: %s\n", (unsigned long)((millis() - sStart) / 1000),
                line.length() ? line.c_str() : "NONE");
}
