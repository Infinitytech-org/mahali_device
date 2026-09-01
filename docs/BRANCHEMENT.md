# Guide de branchement — Contrôleur Mahali (Raspberry Pi)

Guide pas-à-pas pour brancher **capteurs**, **relais** et **écran** sur le
Raspberry Pi. Pensé pour débuter : suis les sections dans l'ordre.

> ⚠️ **Sécurité** : débranche TOUJOURS le Pi de l'alimentation avant de câbler.
> Ne branche jamais un moteur/pompe 220 V directement sur le Pi — ça passe par
> la **carte relais** (côté « COM/NO »). Le Pi ne pilote que la partie
> commande (3,3 V) de la carte relais.

Les numéros de broches ci-dessous sont issus de `config.py` (modifiables par
variables d'environnement). On note `GPIOxx` (numéro logique BCM) **et**
`pin N` (numéro physique sur la barrette de 40 broches).

## Rappel : la barrette 40 broches

```
        3V3  (1) (2)  5V
      GPIO2  (3) (4)  5V         ← SDA (I2C)
      GPIO3  (5) (6)  GND        ← SCL (I2C)
      GPIO4  (7) (8)  GPIO14
        GND  (9)(10)  GPIO15
     GPIO17 (11)(12)  GPIO18     ← Relais 1
     GPIO27 (13)(14)  GND        ← Relais 2
     GPIO22 (15)(16)  GPIO23     ← Relais 3 / HC-SR04 TRIG
        3V3 (17)(18)  GPIO24     ← HC-SR04 ECHO
     GPIO10 (19)(20)  GND        ← Relais 4 (SPI MOSI)
      GPIO9 (21)(22)  GPIO25     ← Relais 5 (SPI MISO)
     GPIO11 (23)(24)  GPIO8      ← Relais 6 (SPI SCLK)
        GND (25)(26)  GPIO7
      GPIO0 (27)(28)  GPIO1
      GPIO5 (29)(30)  GND        ← Relais 7
      GPIO6 (31)(32)  GPIO12     ← Relais 8
     GPIO13 (33)(34)  GND
     GPIO19 (35)(36)  GPIO16
     GPIO26 (37)(38)  GPIO20
        GND (39)(40)  GPIO21
```

---

## 1) Capteurs I2C — température / humidité / pH

Tous les capteurs I2C partagent **2 fils de bus** + alimentation :

| Signal | Broche Pi | Va vers |
|---|---|---|
| **3V3** | pin 1 | VCC des modules I2C |
| **GND** | pin 6 | GND des modules I2C |
| **SDA** (GPIO2) | pin 3 | SDA du multiplexeur/capteurs |
| **SCL** (GPIO3) | pin 5 | SCL du multiplexeur/capteurs |

Détail des composants (adresses dans `config.py`) :
- **Multiplexeur TCA9548A** (`0x70`) : permet de brancher **3 BME280** (temp/hum
  des 3 zones) qui ont tous la même adresse `0x76`. Branche SDA/SCL/VCC/GND du
  TCA9548A au Pi, puis chaque BME280 sur un canal du TCA (SD0/SC0, SD1/SC1, …).
- **BME280** ×3 (`0x76`) : température + humidité (zones entrée / centre / sortie).
- **ADS1115** (`0x48`) : convertisseur analogique→numérique pour la **sonde pH**
  (la sonde pH se branche sur l'entrée **A0** de l'ADS1115).

✅ **Vérifier** : après `./install.sh`, lance `i2cdetect -y 1` — tu dois voir
`70`, `76`, `48`.

---

## 2) Niveau d'eau — capteur ultrason HC-SR04

| Signal | Broche Pi | Note |
|---|---|---|
| **VCC** | pin 2 (5V) | le HC-SR04 s'alimente en 5 V |
| **GND** | pin 9 (GND) | |
| **TRIG** (GPIO23) | pin 16 | sortie déclenchement |
| **ECHO** (GPIO24) | pin 18 | ⚠️ **pont diviseur requis** (voir ci-dessous) |

> ⚠️ Le pin **ECHO** sort en **5 V** mais le Pi n'accepte que **3,3 V**.
> Mets un **pont diviseur** : ECHO → résistance **1 kΩ** → pin 18, et de ce point
> une résistance **2 kΩ** → GND. (Sinon tu risques d'abîmer le Pi.)

---

## 3) Carte relais 8 canaux

Alimentation de la carte relais :

| Signal | Broche Pi |
|---|---|
| **VCC** | pin 4 (5V) |
| **GND** | pin 20 (GND) |

Commandes (une broche par canal). La carte est **active à l'état bas**
(`RELAY_ACTIVE_LOW=true`) — c'est le cas le plus courant.

| Relais | GPIO | pin | Équipement (défaut) |
|---|---|---|---|
| IN1 | GPIO17 | **11** | Pompe principale |
| IN2 | GPIO27 | **13** | Ventilateur bas est — gauche |
| IN3 | GPIO22 | **15** | Ventilateur bas est — droite |
| IN4 | GPIO10 | **19** | Ventilateur haut est |
| IN5 | GPIO9  | **21** | Ventilateur ouest 1 |
| IN6 | GPIO11 | **23** | Ventilateur ouest 2 |
| IN7 | GPIO5  | **29** | Ventilateur ouest 3 |
| IN8 | GPIO6  | **31** | Pompes canari |

Côté puissance (moteurs/pompes) : passe par **COM** + **NO** de chaque relais,
avec l'alimentation dédiée de l'équipement — **jamais** sur le Pi.

---

## 4) Écran 3 pouces — deux cas

> ⚠️ **Conflit à connaître** : les relais **4, 5, 6** utilisent GPIO **10/9/11**,
> qui sont AUSSI les broches **SPI0** (MOSI/MISO/SCLK). Un écran **3,5″ SPI**
> (le type « chapeau » qui se pose sur les 40 broches) utilise ces mêmes
> broches → **conflit** avec les relais 4/5/6.

**Cas A — écran HDMI ou DSI (recommandé, zéro conflit).**
Branche-le sur le port **HDMI** (mini-HDMI + adaptateur) ou sur le connecteur
**DSI** (nappe). Rien à faire côté GPIO : les 8 relais gardent leurs broches.

**Cas B — écran 3,5″ SPI (chapeau GPIO).**
Il faut **libérer le SPI** en déplaçant les relais 4/5/6/7/8 sur d'autres
broches. Mets ces variables dans `~/mahali/raspberry/.env` (ou l'environnement
du service) :

```bash
MAHALI_RELAY4_PIN=12   # pin 32
MAHALI_RELAY5_PIN=16   # pin 36
MAHALI_RELAY6_PIN=20   # pin 38
MAHALI_RELAY7_PIN=21   # pin 40
MAHALI_RELAY8_PIN=26   # pin 37
```
…puis re-câble selon le bloc « ÉCRAN 3,5" SPI » de `.env.example`
(IN1→GPIO12, IN4→GPIO13, IN5→GPIO16, IN6→GPIO19, ECHO→GPIO20).
L'écran SPI garde alors GPIO 8/9/10/11 + 24/25 pour lui.

**Physique** : l'écran étant un chapeau qui couvre les 40 broches, utilise un
**connecteur empilable (stacking header)** ou une **nappe GPIO de dérivation**
pour accéder aux broches restantes (relais/capteurs).

**Pilote de l'écran** (pour qu'il s'allume) : la plupart des 3,5" SPI ont besoin
d'un overlay. Pour un « RPi 3.5 inch » générique :
```bash
# Option simple : ajouter l'overlay dans /boot/firmware/config.txt
sudo bash -c 'echo "dtoverlay=piscreen,speed=16000000,rotate=90" >> /boot/firmware/config.txt'
sudo reboot
```
Si l'écran reste blanc, installe le pilote du fabricant (ex. dépôt `LCD-show`
de ton modèle) — indique-moi la marque exacte et je te donne les commandes.

---

## 5) Écran : afficher le tableau de bord (kiosque)

Une fois l'écran branché et le Pi démarré, l'interface locale tourne sur
`http://localhost:8090`. Pour l'afficher en plein écran automatiquement :
```bash
sudo apt-get install -y chromium-browser
# lancer manuellement pour tester :
./display/kiosk.sh
```
(Le retour automatique au tableau de bord après 3 min d'inactivité est intégré.)

---

## Récapitulatif — ordre de branchement conseillé

1. Pi **éteint**.
2. Bus I2C (TCA9548A + BME280 ×3 + ADS1115 + sonde pH).
3. HC-SR04 (avec le pont diviseur sur ECHO).
4. Carte relais (VCC/GND + IN1…IN8).
5. Écran (HDMI/DSI de préférence ; sinon SPI + remap relais).
6. Rebrancher l'alimentation, puis passer au **logiciel** (`README.md`).
