// LUCI DI NATALE — striscia LED WS2812B (NeoPixel) con Arduino Uno / Nano
// Pulsante breve: effetto successivo. Pulsante lungo (1 s): accendi / spegni.
// L'ultimo effetto scelto resta in memoria anche staccando la corrente.
// Libreria necessaria: FastLED (Strumenti > Gestisci librerie > "FastLED").

#include <FastLED.h>
#include <EEPROM.h>

// ---- DA ADATTARE ALLA TUA STRISCIA ----
#define PIN_DATI       6        // filo dati della striscia (con resistenza da 330 ohm)
#define PIN_PULSANTE   2        // pulsante tra questo pin e GND
#define NUM_LED        50       // quanti LED ha la striscia
#define TIPO_LED       WS2812B
#define ORDINE_COLORI  GRB      // se il rosso esce verde, prova RGB
#define LUMINOSITA     120      // 0-255
#define VOLT           5
#define MILLIAMPERE    2000     // corrente massima dell'alimentatore: FastLED abbassa la luce per non superarla

CRGB led[NUM_LED];
const CRGB CALDO(255, 130, 30);
const CRGB COLORI_NATALE[] = { CRGB::Red, CRGB::Green, CALDO, CRGB::Blue, CRGB::White };

uint8_t effetto = 0;
bool acceso = true;

// ---- EFFETTI (chiamati ogni 20 ms) ----

// Bianco caldo che tremola piano, come le candele
void candele() {
  uint16_t t = millis() / 4;
  for (uint16_t i = 0; i < NUM_LED; i++) {
    CRGB c = CALDO;
    c.nscale8_video(150 + scale8(inoise8(i * 60, t), 105));
    led[i] = c;
  }
}

// LED colorati che si accendono a caso e si spengono piano
void scintillio() {
  fadeToBlackBy(led, NUM_LED, 10);
  if (random8() < 80) {
    led[random16(NUM_LED)] = COLORI_NATALE[random8(5)];
  }
}

// Gruppi rossi e verdi che scorrono
void rossoVerde() {
  uint16_t passo = millis() / 150;
  for (uint16_t i = 0; i < NUM_LED; i++) {
    led[i] = ((i + passo) / 3) % 2 ? CRGB::Red : CRGB::Green;
  }
}

// Strisce rosse e bianche, come il bastoncino di zucchero
void bastoncino() {
  uint16_t passo = millis() / 120;
  for (uint16_t i = 0; i < NUM_LED; i++) {
    led[i] = (i + passo) % 6 < 3 ? CRGB::Red : CRGB::White;
  }
}

// Arcobaleno che scorre
void arcobaleno() {
  fill_rainbow(led, NUM_LED, millis() / 20, 7);
}

// Fondo blu notte con fiocchi bianchi che si accendono e sfumano
void neve() {
  for (uint16_t i = 0; i < NUM_LED; i++) {
    nblend(led[i], CRGB(0, 0, 25), 8);
  }
  if (random8() < 40) {
    led[random16(NUM_LED)] = CRGB::White;
  }
}

typedef void (*Effetto)();
const Effetto EFFETTI[] = { candele, scintillio, rossoVerde, bastoncino, arcobaleno, neve };
const uint8_t NUM_EFFETTI = sizeof(EFFETTI) / sizeof(EFFETTI[0]);

// ---- PULSANTE (con antirimbalzo, senza bloccare gli effetti) ----

void leggiPulsante() {
  static bool letto = HIGH, stabile = HIGH, lungo = false;
  static unsigned long tCambio = 0, tPressione = 0;

  bool s = digitalRead(PIN_PULSANTE);
  if (s != letto) {
    letto = s;
    tCambio = millis();
  }
  if (millis() - tCambio < 30) return;

  if (letto != stabile) {
    stabile = letto;
    if (stabile == LOW) {
      tPressione = millis();
      lungo = false;
    } else if (!lungo && acceso) {
      effetto = (effetto + 1) % NUM_EFFETTI;
      EEPROM.update(0, effetto);
      FastLED.clear();
    }
  }

  if (stabile == LOW && !lungo && millis() - tPressione > 1000) {
    lungo = true;
    acceso = !acceso;
    FastLED.clear(true);
  }
}

void setup() {
  delay(500);  // lascia stabilizzare l'alimentazione
  pinMode(PIN_PULSANTE, INPUT_PULLUP);
  FastLED.addLeds<TIPO_LED, PIN_DATI, ORDINE_COLORI>(led, NUM_LED);
  FastLED.setBrightness(LUMINOSITA);
  FastLED.setMaxPowerInVoltsAndMilliamps(VOLT, MILLIAMPERE);
  random16_add_entropy(analogRead(A0));

  effetto = EEPROM.read(0);
  if (effetto >= NUM_EFFETTI) effetto = 0;  // EEPROM vuota (255) al primo avvio
}

void loop() {
  leggiPulsante();
  if (!acceso) return;
  EVERY_N_MILLISECONDS(20) {
    EFFETTI[effetto]();
    FastLED.show();
  }
}
