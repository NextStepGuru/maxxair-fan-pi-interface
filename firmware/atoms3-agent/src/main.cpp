#define DISABLE_CODE_FOR_RECEIVER
#define NO_LED_FEEDBACK_CODE
#define NO_LED_SEND_FEEDBACK_CODE
#define SEND_PWM_BY_TIMER
#ifndef IR_SEND_PIN
#define IR_SEND_PIN 4
#endif

#include <Adafruit_NeoPixel.h>
#include <Arduino.h>
#include <DallasTemperature.h>
#include <ESPmDNS.h>
#include <IRremote.hpp>
#include <M5Unified.h>
#include <OneWire.h>
#include <WebServer.h>
#include <WiFi.h>

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Copy src/secrets.h.example to src/secrets.h and set Wi-Fi plus AGENT_TOKEN"
#endif

#include "ir_timings.h"

#ifndef FAN_HOSTNAME
#define FAN_HOSTNAME "maxxair-fan1"
#endif

#ifndef AGENT_PORT
#define AGENT_PORT 8765
#endif

static const int kOneWirePin = 5;
static const int kLedPin = 35;
static const int kLedCount = 4;
static const int kSensorRetries = 3;
static const uint8_t kLedBrightness = 32;

static const uint32_t kColorBoot = 0x202020;
static const uint32_t kColorWifi = 0x402000;
static const uint32_t kColorIdle = 0x002000;
static const uint32_t kColorIr = 0x000040;
static const uint32_t kColorError = 0x400000;

static WebServer server(AGENT_PORT);
static OneWire oneWire(kOneWirePin);
static DallasTemperature sensors(&oneWire);
static Adafruit_NeoPixel statusLed(kLedCount, kLedPin, NEO_GRB + NEO_KHZ800);

static uint32_t currentLedColor = 0;
static bool sensorOk = false;

static void setLed(uint32_t color) {
  if (color == currentLedColor) {
    return;
  }
  currentLedColor = color;
  for (int i = 0; i < kLedCount; i++) {
    statusLed.setPixelColor(i, color);
  }
  statusLed.show();
}

static bool authorized() {
  if (strlen(AGENT_TOKEN) == 0) {
    return true;
  }
  if (!server.hasHeader("Authorization")) {
    return false;
  }
  String expected = String("Bearer ") + AGENT_TOKEN;
  return server.header("Authorization") == expected;
}

static void sendJson(int status, const String &body) {
  server.send(status, "application/json", body);
}

static bool extractFilename(const String &body, String &filename) {
  int key = body.indexOf("\"filename\"");
  if (key < 0) {
    return false;
  }
  int colon = body.indexOf(':', key);
  if (colon < 0) {
    return false;
  }
  int quote1 = body.indexOf('"', colon);
  if (quote1 < 0) {
    return false;
  }
  int quote2 = body.indexOf('"', quote1 + 1);
  if (quote2 < 0) {
    return false;
  }
  filename = body.substring(quote1 + 1, quote2);
  return filename.length() > 0;
}

static const IrCode *findIrCode(const String &filename) {
  for (size_t i = 0; i < IR_CODE_COUNT; i++) {
    if (filename == IR_CODES[i].filename) {
      return &IR_CODES[i];
    }
  }
  return nullptr;
}

static bool sendIrCode(const IrCode *code) {
  if (code == nullptr || code->length == 0 || code->length > IR_MAX_TIMINGS) {
    return false;
  }
  setLed(kColorIr);
  delay(15);
  uint16_t buffer[IR_MAX_TIMINGS];
  memcpy_P(buffer, code->timings, code->length * sizeof(uint16_t));
  IrSender.sendRaw(buffer, code->length, IR_CARRIER_KHZ);
  delay(15);
  setLed(sensorOk ? kColorIdle : kColorError);
  return true;
}

static bool readTempF(float *outTempF) {
  for (int attempt = 0; attempt < kSensorRetries; attempt++) {
    sensors.requestTemperatures();
    float tempF = sensors.getTempFByIndex(0);
    if (tempF != DEVICE_DISCONNECTED_F && tempF > -50.0f && tempF < 185.0f) {
      *outTempF = tempF;
      return true;
    }
    delay(50);
  }
  return false;
}

static void handleHealth() {
  sendJson(200, "{\"ok\":true}");
}

static void handleTemp() {
  if (!authorized()) {
    sendJson(401, "{\"error\":\"unauthorized\"}");
    return;
  }
  float tempF = 0;
  if (!readTempF(&tempF)) {
    sensorOk = false;
    setLed(kColorError);
    sendJson(503, "{\"error\":\"sensor read failed\"}");
    return;
  }
  sensorOk = true;
  setLed(kColorIdle);
  char body[48];
  snprintf(body, sizeof(body), "{\"temp_f\":%.2f}", tempF);
  sendJson(200, body);
}

static void handleIr() {
  if (!authorized()) {
    sendJson(401, "{\"error\":\"unauthorized\"}");
    return;
  }
  String body = server.arg("plain");
  body.trim();
  if (body.length() > 0 && body[0] != '{') {
    sendJson(400, "{\"error\":\"invalid JSON body\"}");
    return;
  }
  String filename;
  if (!extractFilename(body, filename)) {
    sendJson(400, "{\"error\":\"filename required\"}");
    return;
  }
  const IrCode *code = findIrCode(filename);
  if (code == nullptr) {
    sendJson(400, "{\"error\":\"unknown IR filename\"}");
    return;
  }
  if (!sendIrCode(code)) {
    String error = "{\"error\":\"IR send failed for ";
    error += filename;
    error += "\"}";
    sendJson(500, error);
    return;
  }
  String ok = "{\"ok\":true,\"filename\":\"";
  ok += filename;
  ok += "\"}";
  sendJson(200, ok);
}

static void handleNotFound() {
  sendJson(404, "{\"error\":\"not found\"}");
}

static void handleButton() {
  if (!M5.BtnA.wasClicked()) {
    return;
  }
  const IrCode *code = findIrCode("fan_off.ir");
  if (code != nullptr) {
    Serial.println("Button: sending fan_off.ir");
    sendIrCode(code);
  }
}

static void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setHostname(FAN_HOSTNAME);
  setLed(kColorWifi);
  Serial.printf("Connecting to Wi-Fi as %s\n", FAN_HOSTNAME);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t lastDot = 0;
  while (WiFi.status() != WL_CONNECTED) {
    M5.update();
    if (millis() - lastDot > 500) {
      Serial.print(".");
      lastDot = millis();
    }
    delay(50);
  }
  Serial.printf("\nWi-Fi connected, IP %s\n", WiFi.localIP().toString().c_str());
  setLed(kColorIdle);
}

static void startMdns() {
  if (!MDNS.begin(FAN_HOSTNAME)) {
    Serial.println("mDNS failed");
    return;
  }
  MDNS.addService("http", "tcp", AGENT_PORT);
  Serial.printf("mDNS http://%s.local:%d\n", FAN_HOSTNAME, AGENT_PORT);
}

static void startHttp() {
  const char *headers[] = {"Authorization"};
  server.collectHeaders(headers, 1);
  server.on("/health", HTTP_GET, handleHealth);
  server.on("/temp", HTTP_GET, handleTemp);
  server.on("/ir", HTTP_POST, handleIr);
  server.onNotFound(handleNotFound);
  server.begin();
  Serial.printf("Agent listening on :%d\n", AGENT_PORT);
}

void setup() {
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;
  M5.begin(cfg);

  statusLed.begin();
  statusLed.setBrightness(kLedBrightness);
  setLed(kColorBoot);

  pinMode(IR_SEND_PIN, OUTPUT);
  IrSender.begin(DISABLE_LED_FEEDBACK);
  IrSender.setSendPin(IR_SEND_PIN);

  pinMode(kOneWirePin, INPUT);
  sensors.begin();
  sensors.setWaitForConversion(true);

  connectWifi();
  startMdns();
  startHttp();
}

void loop() {
  M5.update();
  handleButton();
  if (WiFi.status() != WL_CONNECTED) {
    setLed(kColorWifi);
    WiFi.reconnect();
  }
  server.handleClient();
}
