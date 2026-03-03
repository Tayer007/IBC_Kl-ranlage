# IBC Kläranlagensteuerung – Einrichtungsanleitung

---

## 1. System aktualisieren

```bash
sudo apt-get update && sudo apt-get upgrade -y
```

---

## 2. Python 3 installieren

```bash
sudo apt-get install -y python3 python3-pip python3-venv
```

---

## 3. Node.js 20 installieren

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
```

---

## 4. Git installieren und Projekt herunterladen

```bash
sudo apt-get install -y git
git clone https://github.com/Tayer007/IBC ~/IBC_Siedlungswasser_2
cd ~/IBC_Siedlungswasser_2
```

---

## 5. Python-Bibliotheken installieren

```bash
cd ~/IBC_Siedlungswasser_2/backend
python3 -m venv venv
source venv/bin/activate
pip install flask==3.0.0 flask-cors==4.0.0 flask-socketio==5.3.5 python-socketio==5.10.0 \
            pydantic==2.5.0 pyyaml==6.0.1 sqlalchemy==2.0.23 alembic==1.13.0 \
            python-dotenv==1.0.0 eventlet==0.33.3 RPi.GPIO
deactivate
```

---

## 6. Frontend erstellen

```bash
cd ~/IBC_Siedlungswasser_2/frontend
npm install
npm run build
```

---

## 7. Cloudflared installieren

```bash
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64 -o /tmp/cloudflared
sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared
```

---

## 8. Dienste installieren und starten

```bash
cd ~/IBC_Siedlungswasser_2
sudo bash manage_services.sh install
```

---

## 9. Öffentliche URL abrufen

```bash
bash manage_services.sh url
```

Die angezeigte URL im Browser öffnen – die Anwendung ist jetzt erreichbar.

> **Hinweis:** Die URL ändert sich bei jedem Neustart des Raspberry Pi. Einfach diesen Befehl erneut ausführen, um die neue URL zu erhalten.

---

## Tägliche Nutzung

```bash
# Aktuelle URL abrufen
bash ~/IBC_Siedlungswasser_2/manage_services.sh url

# Alles neu starten (z.B. nach Problemen)
sudo bash ~/IBC_Siedlungswasser_2/manage_services.sh restart

# Status prüfen
bash ~/IBC_Siedlungswasser_2/manage_services.sh status
```
