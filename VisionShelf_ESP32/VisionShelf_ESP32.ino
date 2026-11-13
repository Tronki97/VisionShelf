#include <WiFi.h>
#include <WiFiMulti.h>
#include <WebServer.h>
#include <FastLED.h>
#include <WiFiUdp.h>
#include <WiFiManager.h>

// Crea l'oggetto UDP e un timer
WiFiUDP udp;
unsigned long lastBroadcast = 0;


// costanti FastLED
#define LED_PIN     13    // pin dati collegato alla striscia LED
#define NUM_LEDS    40    // numero MASSIMO dei LED 
#define BRIGHTNESS  200 
#define LED_TYPE    WS2812B 
#define COLOR_ORDER GRB

CRGB leds[NUM_LEDS];

//configurazioni di rete
WiFiMulti wifiMulti;
WebServer server(80);


const int ledPin = 2; //LED integrato dell'ESP32
bool ledState = false;

// Variabili per il timer non bloccante
unsigned long timerPrecedente = 0;
const long intervallo = 15000; // 15 secondi

bool connesso = false;


void setup() {
  Serial.begin(115200);

  WiFiManager wifiManager;
  
  bool connesso = wifiManager.autoConnect("VisionShelf_Setup");

  FastLED.addLeds<LED_TYPE, LED_PIN, COLOR_ORDER>(leds, NUM_LEDS).setCorrection(TypicalLEDStrip);
  FastLED.setBrightness(BRIGHTNESS);
  
  // Parte tutto spento
  FastLED.clear();
  FastLED.show();

  pinMode(ledPin, OUTPUT);
  
  Serial.println("\n--- Avvio ESP32 ---");


  if (!connesso) {
    Serial.println("Connessione fallita. Riavvio in corso...");
    delay(3000);
    ESP.restart(); // Si riavvia e riprova
  }

  Serial.println("\nConnesso con successo!");
  Serial.print("SSID Rete attuale: ");
  Serial.println(WiFi.SSID()); // stampa a quale rete si è collegato
  Serial.print("Indirizzo IP: ");
  Serial.println(WiFi.localIP());
  udp.begin(5555);

  server.on("/accendi", []() {
    // SBLOCCO CORS: Autorizza il browser a comunicare direttamente con l'ESP32
    server.sendHeader("Access-Control-Allow-Origin", "*");
    
    if (!server.hasArg("led")) {
      server.send(400, "text/plain", "Errore: parametri mancanti");
      return;
    }

    //prende il numero del LED
    int targetLED = server.arg("led").toInt(); 
    FastLED.clear();

    //assegna a quel LED il colore Verde
    leds[targetLED] = CRGB::Green;

    //accende quel LED
    FastLED.show();
    server.send(200, "text/plain", "OK: LED " + String(targetLED) + " acceso");
  });

  server.on("/spegni", []() {
    //Spegne tutti i LED
    FastLED.clear();
    FastLED.show();
    server.send(200, "text/plain", "luci spente");
  });


  server.on("/assente", []() {
    Serial.println("❌ Oggetto non trovato: Lampeggio rosso attivato");
  
    // Fa lampeggiare tutti i LED per 3 volte
    for (int i = 0; i < 5; i++) {
      // Accende tutto di rosso
      for (int j = 0; j < NUM_LEDS; j++) {
        leds[j] = CRGB::Red; 
      } 
      FastLED.show();
      delay(300);
      
      // Spegne tutto
      FastLED.clear();
      FastLED.show();
      delay(300);
    }
  
    server.send(200, "text/plain", "OK: Segnale di errore eseguito");
  });

  server.begin();
}

void loop() {

  //fintanto che non è connesso manda in broadcast la "richiesta"
  if (!connesso && (millis() - lastBroadcast > 10000)) {
    udp.beginPacket("255.255.255.255", 5555);
    udp.print("VISIONSHELF_ESP:" + WiFi.localIP().toString());
    udp.endPacket();
    
    lastBroadcast = millis();
    Serial.println("Invio broadcast UDP...");
    digitalWrite(ledPin, LOW);
  }

  //Ascolta se arriva la risposta dal Raspberry
  int packetSize = udp.parsePacket();
  if (packetSize) {
    char bufferDiRicezione[255];
    int len = udp.read(bufferDiRicezione, 255);
    if (len > 0) {
      bufferDiRicezione[len] = 0; // Chiude correttamente il testo
    }
    String risposta = String(bufferDiRicezione);
    
    // Se è il messaggio giusto, smette di urlare!
    if (risposta == "ACK_VISIONSHELF") {
      connesso = true;
      Serial.println("Conferma ricevuta dal Raspberry!");
      digitalWrite(ledPin, HIGH);
    }
  }
  //Ascolta continuamente se arrivano comandi dal Raspberry
  server.handleClient(); 
}