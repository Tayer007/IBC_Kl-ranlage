# IBC Kläranlagensteuerung

Steuerungssystem für eine IBC-basierte Versuchskläranlage (Sequencing Batch Reactor) zur biologischen Stickstoffelimination.

## Funktionen

- 12-Phasen SBR-Prozess mit stufenweiser Beschickung
- Echtzeit-Überwachung über Web-Dashboard
- Fernzugriff über Cloudflare Tunnel
- Manuelle und automatische Steuerung
- Datenprotokollierung und Verlaufsanzeige

## Technologie

- **Backend:** Python / Flask / SocketIO
- **Frontend:** React / Vite
- **Hardware:** Raspberry Pi / RPi.GPIO
- **Hosting:** Cloudflare Tunnel

## Einrichtung

Siehe [SETUP_ANLEITUNG.md](SETUP_ANLEITUNG.md) für die vollständige Installationsanleitung.

## GPIO-Pinbelegung

| BCM-Pin | Komponente       | Funktion                        |
|---------|------------------|---------------------------------|
| GPIO 17 | Zulaufpumpe      | Befüllt den Tank                |
| GPIO 22 | Verdichter       | Belüftung                       |
| GPIO 23 | Sensor LEER      | Stoppt Ablauf bei leerem Tank   |
| GPIO 24 | Sensor VOLL      | Stoppt Zulauf bei vollem Tank   |
| GPIO 27 | Ablaufventil     | Ablassen des Klarwassers        |
