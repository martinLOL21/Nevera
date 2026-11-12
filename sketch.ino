#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <DHT.h>

// ================= CONFIGURACION =================
const char* WIFI_SSID   = "Wokwi-GUEST";
const char* WIFI_PASS   = "";
const char* MQTT_SERVER = "157.230.214.127";   // broker del profesor
const int   MQTT_PORT   = 1883;

const char* TOPIC_CMD    = "nevera_Florez/cmd";     // Streamlit -> ESP32
const char* TOPIC_ESTADO = "nevera_Florez/estado";  // ESP32 -> Streamlit

const int PIN_DHT   = 15;
const int PIN_SERVO = 13;
const int PIN_LED   = 2;

const int ANGULO_CERRADA = 0;
const int ANGULO_ABIERTA = 90;

const float UMBRAL_CIERRE = 5.0;              // se cierra cuando la temp baja de este valor (C)
const unsigned long MIN_ABIERTA_MS = 5000;    // tiempo minimo abierta antes de evaluar el cierre
const unsigned long MAX_ABIERTA_MS = 60000;   // seguridad: cierra aunque la temp no baje
const unsigned long INTERVALO_MS   = 2000;    // lectura DHT22 y publicacion de telemetria

// ================= OBJETOS Y ESTADO =================
WiFiClient espClient;
PubSubClient client(espClient);
Servo puerta;
DHT dht(PIN_DHT, DHT22);

bool puertaAbierta = false;
unsigned long tAbierta = 0;
unsigned long tUltimaLectura = 0;
unsigned long tUltimoIntento = 0;
float temp = NAN;
float hum = NAN;
String articuloActual = "";

// ================= WIFI =================
void setup_wifi() {
  Serial.print("Conectando a ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi conectado, IP: ");
  Serial.println(WiFi.localIP());
}

// ================= PUBLICACION =================
void publicarEstado(const char* evento) {
  StaticJsonDocument<256> doc;
  if (!isnan(temp)) doc["temp"] = temp;
  if (!isnan(hum))  doc["hum"] = hum;
  doc["puerta"] = puertaAbierta ? "abierta" : "cerrada";
  if (evento != nullptr && evento[0] != '\0') doc["evento"] = evento;
  if (articuloActual.length() > 0) doc["articulo"] = articuloActual;

  char buf[256];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  if (client.connected()) {
    client.publish(TOPIC_ESTADO, buf, n);
  }
  Serial.print("PUB: ");
  Serial.println(buf);
}

// ================= PUERTA =================
void abrirPuerta(const String& articulo) {
  if (puertaAbierta) return;
  puertaAbierta = true;
  tAbierta = millis();
  articuloActual = articulo;
  puerta.write(ANGULO_ABIERTA);
  digitalWrite(PIN_LED, HIGH);
  publicarEstado("puerta_abierta");
}

void cerrarPuerta(const char* motivo) {
  if (!puertaAbierta) return;
  puertaAbierta = false;
  puerta.write(ANGULO_CERRADA);
  digitalWrite(PIN_LED, LOW);
  publicarEstado(motivo);
  articuloActual = "";
}

// ================= MQTT =================
void callback(char* topic, byte* payload, unsigned int length) {
  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.print("JSON invalido: ");
    Serial.println(error.f_str());
    return;
  }

  const char* cmd = doc["cmd"];
  if (cmd == nullptr) return;

  if (strcmp(cmd, "abrir") == 0) {
    String articulo = String((const char*)(doc["articulo"] | ""));
    abrirPuerta(articulo);
  } else if (strcmp(cmd, "cerrar") == 0) {
    cerrarPuerta("cierre_manual");
  }
}

void mantenerMQTT() {
  if (client.connected()) return;
  if (millis() - tUltimoIntento < 5000) return;
  tUltimoIntento = millis();

  String id = "nevera-esp32-" + String((uint32_t)esp_random(), HEX);
  Serial.print("Conectando MQTT...");
  if (client.connect(id.c_str())) {
    Serial.println(" conectado");
    client.subscribe(TOPIC_CMD);
    publicarEstado("esp32_en_linea");
  } else {
    Serial.print(" fallo, rc=");
    Serial.println(client.state());
  }
}

// ================= SETUP / LOOP =================
void setup() {
  Serial.begin(115200);
  pinMode(PIN_LED, OUTPUT);
  digitalWrite(PIN_LED, LOW);

  dht.begin();
  puerta.setPeriodHertz(50);
  puerta.attach(PIN_SERVO, 500, 2400);
  puerta.write(ANGULO_CERRADA);

  setup_wifi();
  client.setServer(MQTT_SERVER, MQTT_PORT);
  client.setCallback(callback);
  client.setBufferSize(512);
}

void loop() {
  mantenerMQTT();
  client.loop();

  unsigned long ahora = millis();
  if (ahora - tUltimaLectura >= INTERVALO_MS) {
    tUltimaLectura = ahora;

    float t = dht.readTemperature();
    float h = dht.readHumidity();
    if (!isnan(t)) temp = t;
    if (!isnan(h)) hum = h;

    publicarEstado("");
  }

  // Cierre automatico
  if (puertaAbierta) {
    unsigned long abierta = millis() - tAbierta;
    if (abierta >= MIN_ABIERTA_MS && !isnan(temp) && temp <= UMBRAL_CIERRE) {
      cerrarPuerta("cierre_auto_temperatura");
    } else if (abierta >= MAX_ABIERTA_MS) {
      cerrarPuerta("cierre_auto_tiempo");
    }
  }
}
