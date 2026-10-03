// Diagnostic: BLE only, WiFi/MQTT never started. Prints reads to serial.
#include <Arduino.h>
#include <NimBLEDevice.h>

static const char *kMacs[] = {
    "c0:d6:3c:5f:4e:08", "c0:d6:3c:5e:21:b0", "c0:d6:3c:5f:68:a9",
    "c0:d6:3c:5f:69:50", "c0:d6:3c:5e:20:50", "c0:d6:3c:5f:66:60",
};
static const char *kNames[] = {"bat01", "bat02", "bat03", "bat04", "bat05", "bat06"};
static const char *kChNotify = "0000fff1-0000-1000-8000-00805f9b34fb";
static const char *kChWrite = "0000fff2-0000-1000-8000-00805f9b34fb";
static const char *kChAuth = "0000fffa-0000-1000-8000-00805f9b34fb";

struct Asm { uint8_t buf[256]; size_t len, expected; bool complete;
  void reset(){len=0;expected=0;complete=false;}
  void feed(const uint8_t*d,size_t n){ if(complete||len+n>sizeof(buf))return;
    memcpy(buf+len,d,n); len+=n;
    if(!expected&&len>=8){expected=((buf[6]<<8)|buf[7])+11; if(expected>sizeof(buf))expected=sizeof(buf);}
    if(expected&&len>=expected)complete=true; } };
static Asm sAsm;
static void notifyCb(NimBLERemoteCharacteristic*,uint8_t*d,size_t l,bool){ sAsm.feed(d,l); }

static bool readDp(NimBLERemoteCharacteristic*w,uint16_t dp){
  uint8_t f[11]={0x7e,0,1,3,(uint8_t)(dp>>8),(uint8_t)dp,0,0,0,0,0x0d};
  uint16_t crc=0xffff;
  for(int i=0;i<8;i++){crc^=f[i];for(int b=0;b<8;b++)crc=(crc&1)?(crc>>1)^0xa001:crc>>1;}
  f[8]=crc>>8;f[9]=crc&0xff;
  sAsm.reset();
  w->writeValue(f,11,false);
  uint32_t until=millis()+3000;
  while(!sAsm.complete&&millis()<until)delay(20);
  return sAsm.complete;
}

static void probe(int idx){
  NimBLEClient*c=NimBLEDevice::createClient();
  c->setConnectTimeout(10);
  uint32_t t0=millis();
  bool ok=c->connect(NimBLEAddress(kMacs[idx]),BLE_ADDR_RANDOM);
  Serial.printf("%s connect=%d (%lums)\n",kNames[idx],ok,(unsigned long)(millis()-t0));
  if(!ok){NimBLEDevice::deleteClient(c);return;}
  auto*svcs=c->getServices(true);
  NimBLERemoteCharacteristic*n=nullptr,*w=nullptr,*a=nullptr;
  for(auto*s:*svcs)for(auto*ch:*s->getCharacteristics(true)){
    String u=String(ch->getUUID().toString().c_str());u.toUpperCase();
    if(u.indexOf("FFF1")!=-1)n=ch; if(u.indexOf("FFF2")!=-1)w=ch; if(u.indexOf("FFFA")!=-1)a=ch;
  }
  if(!n||!w||!a){Serial.printf("  %s chars missing\n",kNames[idx]);c->disconnect();NimBLEDevice::deleteClient(c);return;}
  n->subscribe(true,notifyCb,true);
  a->writeValue((const uint8_t*)"HiLink",6,true);
  delay(300);
  bool prod=readDp(w,0x0092), analog=readDp(w,0x008c);
  Serial.printf("  %s product=%d analog=%d len=%u\n",kNames[idx],prod,analog,
                analog?sAsm.len:0);
  if(analog&&sAsm.len>=8){
    uint8_t*p=sAsm.buf+8; int nc=p[0];
    Serial.printf("  %s cells=%d v=%.2f\n",kNames[idx],nc,nc>=1&&sAsm.len>=(size_t)(2+nc*2+14)?((p[2+nc*2+2+2+ (p[2+nc*2+1]-2)*2+2+2]*0)) :0);
    // crude: print raw payload head
    String hx;char b[3];
    for(size_t i=8;i<sAsm.len&&i<40;i++){snprintf(b,3,"%02x",sAsm.buf[i]);hx+=b;}
    Serial.printf("  payload: %s\n",hx.c_str());
  }
  n->subscribe(false,nullptr,true);
  c->disconnect();
  NimBLEDevice::deleteClient(c);
}

void setup(){
  Serial.begin(115200);delay(300);
  Serial.println("\nBLE-only probe (no wifi)");
  NimBLEDevice::init("bleonly");
}
void loop(){
  for(int i=0;i<6;i++){probe(i);delay(300);}
  Serial.println("--- cycle done, 5s ---");
  delay(5000);
}
