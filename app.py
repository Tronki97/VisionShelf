from flask import Flask, render_template, send_file, request
from gpiozero import LED, Button
import os
import subprocess
import json
import requests
import sys
import socket
import threading
from datetime import datetime



app = Flask(__name__)
FILE_NOMI = 'nomi.json'
FILE_CONFIG = 'config.json'

def leggi_config():
    if os.path.exists(FILE_CONFIG):
        with open(FILE_CONFIG, 'r') as f:
            return json.load(f)
    # Se il file non esiste ancora, dà un IP di base
    return {"esp_ip": "http://192.168.43.50"}

def salva_config(config):
    with open(FILE_CONFIG, 'w') as f:
        json.dump(config, f, indent=4)


def ascoltatore_udp():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Permette di ascoltare i messaggi broadcast da chiunque
    sock.bind(("", 5555)) 
    print("inizio ascolto")

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            messaggio = data.decode('utf-8')
            
            if messaggio.startswith("VISIONSHELF_ESP:"):
                ip_ricevuto = messaggio.split(":")[1]
                print("messaggio ricevuto")

                config = leggi_config()
                # Salva solo se l'IP è effettivamente cambiato
                if config.get('esp_ip') != f"http://{ip_ricevuto}":
                    config['esp_ip'] = f"http://{ip_ricevuto}"
                    salva_config(config)
                    print(f"📡 AUTO-DISCOVERY UDP: Trovato ESP32 a {ip_ricevuto}!")
                sock.sendto(b"ACK_VISIONSHELF", addr)
        except Exception as e:
            pass


def leggi_nomi():
    if os.path.exists(FILE_NOMI):
        with open(FILE_NOMI, 'r') as f:
            return json.load(f)
    return {}


def salva_nomi(nomi):
    with open(FILE_NOMI, 'w') as f:
        json.dump(nomi, f, indent=4)

@app.route('/')
def index():
    config = leggi_config()
    intervallo = config.get("intervallo_scansione", 5)
    return render_template('index.html', intervallo = intervallo)

@app.route('/video_feed')
def video_feed():
    image_path = 'risultato_aruco.jpg'
    if os.path.exists(image_path):
        response = send_file(image_path, mimetype='image/jpeg')
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        return response
    else:
        return "Foto non ancora disponibile", 404

@app.route('/start_camera', methods=['POST'])
def start_camera():
    try:
        subprocess.run([sys.executable, "cam.py"], check = True)
        markers = []
        if os.path.exists("markers.json"):
            with open("markers.json", "r") as f:
                markers = json.load(f)
        return {"status": "success", "message": "Scansione completata", "markers": markers}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/markers')
def markers_page():
    markers_data = []
    if os.path.exists("markers.json"):
        try:
            with open("markers.json", "r") as f:
                markers_data = json.load(f)
                
            markers_data = sorted(markers_data, key=lambda k: k['id'])
        except json.JSONDecodeError:
            # Nel caso in cui il file sia temporaneamente vuoto
            markers_data = []
            
    nomi = leggi_nomi()
    for m in markers_data:
        m['nome'] = nomi.get(str(m['id']), "senza nome")

    config = leggi_config()
    esp_ip = config.get("esp_ip", "")

    # Invia i dati ordinati al nuovo file HTML
    return render_template('markers.html', markers=markers_data, esp_ip = esp_ip)


@app.route('/cerca_oggetto', methods=['POST'])
def cerca_oggetto():
    id_cercato = request.form.get('id_marker')
    config = leggi_config()
    esp_ip = config.get("esp_ip")

    if not id_cercato:
        return "Errore: Inserisci un ID marker", 400

    id_cercato = int(id_cercato)
    percorso_markers = os.path.join(os.path.dirname(os.path.abspath(__file__)), "markers.json")
    
    try:
        with open(percorso_markers, "r") as f:
            markers = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return "Errore: Nessuna scansione disponibile.", 400
        
    marker_trovato = None
    for m in markers:
        if m["id"] == id_cercato:
            marker_trovato = m
            break
            
    if not marker_trovato:
        print("marker mancante sullo scaffale")
        if esp_ip:
            try:
                requests.get(f"{esp_ip}/assente", timeout=4)
            except requests.exceptions.RequestException as e:
                print(f"Errore comando lampeggio: {e}")

        # Restituisce l'errore 404 a JavaScript
        return f"L'oggetto con ID {id_cercato} non è sullo scaffale!", 404        
    
    
    if not esp_ip:
        return "Errore: L'ESP32 non è ancora connesso.", 400
        
    led_target = marker_trovato["led_target"]
    
    url_chiamata = f"{esp_ip}/accendi?led={led_target}"
    
    try:
        print(f"🚀 Accendo il LED {led_target} per l'oggetto {id_cercato}")
        requests.get(url_chiamata, timeout=3)
        return f"✅ Oggetto {id_cercato} trovato vicino al LED {led_target}!"
    except requests.exceptions.RequestException as e:
        return f"Errore di comunicazione con ESP32: {e}", 500


@app.route('/spegni_luci', methods=['POST'])
def spegni_luci():
    config = leggi_config()
    esp_ip = config.get("esp_ip")
    
    if esp_ip:
        try:
            # Chiama la rotta di spegnimento dell'ESP32
            requests.get(f"{esp_ip}/spegni", timeout=3)
            print("💡 Inviato comando di spegnimento generale")
            return "luci Spente", 200
        except requests.exceptions.RequestException as e:
            print(f"Errore nello spegnimento: {e}")
            return f"errore di comunicazione: {e}", 500


@app.route('/gestione')
def gestione_page():
    markers_data = []
    if os.path.exists("markers.json"):
        try:
            with open("markers.json", "r") as f:
                markers_data = json.load(f)
                
            markers_data = sorted(markers_data, key=lambda k: k['id'])
        except json.JSONDecodeError:
            # Nel caso in cui il file sia temporaneamente vuoto
            markers_data = []

    nomi = leggi_nomi()
    for m in markers_data:
        m['nome'] = nomi.get(str(m['id']), "") # Qui lasciamo vuoto se non c'è

    config = leggi_config()
    esp_ip = config.get("esp_ip", "")
    intervallo = config.get("intervallo_scansione", 5)

    return render_template('gestione.html', markers = markers_data, esp_ip = esp_ip, intervallo = intervallo)

@app.route('/salva_nome', methods=['POST'])
def salva_nome():
    dati = request.get_json()
    m_id = str(dati.get('id'))
    nuovo_nome = dati.get('nome')
    
    nomi = leggi_nomi()
    nomi[m_id] = nuovo_nome
    salva_nomi(nomi)
    
    return {"status": "success"}

@app.route('/salva_tutti_nomi', methods=['POST'])
def salva_tutti_nomi():
    try:
        nuovi_nomi = request.get_json()
        salva_nomi(nuovi_nomi)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/salva_ip', methods=['POST'])
def salva_ip():
    try:
        dati = request.get_json()
        nuovo_ip = dati.get('ip')
        
        config = leggi_config()
        config['esp_ip'] = nuovo_ip
        salva_config(config)
        
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/salva_intervallo', methods=['POST'])
def salva_intervallo():
    try:
        dati = request.get_json()
        nuovo_intervallo = int(dati.get('intervallo', 5))
        
        config = leggi_config()
        config['intervallo_scansione'] = nuovo_intervallo
        salva_config(config)
        
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500


@app.route('/preleva_oggetto', methods=['POST'])
def preleva_oggetto():
    id_marker = request.form.get('id_marker')
    nome_marker = request.form.get('nome_marker')

    if not id_marker:
        return "Dati mancanti", 400

    percorso_logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs.json")
    
    # 1. Legge i log esistenti (se il file non esiste, crea una lista vuota)
    try:
        with open(percorso_logs, "r") as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []

    # 2. Crea il nuovo record. La restituzione per ora è "None" (Null)
    nuovo_log = {
        "id": int(id_marker),
        "nome": nome_marker,
        "data_prelievo": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "data_restituzione": None
    }
    logs.insert(0, nuovo_log) # Lo inserisce in cima alla lista (il più recente per primo)

    # 3. Salva sul file
    with open(percorso_logs, "w") as f:
        json.dump(logs, f, indent=4)

    return "Registrato", 200


@app.route('/log')
def pagina_log():
    percorso_logs = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs.json")
    try:
        with open(percorso_logs, "r") as f:
            logs = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        logs = []
        
    return render_template('log.html', logs=logs)



def spegni_sistema():
    print("Pulsante premuto: Spegnimento del sistema in corso...")
    # Fa lampeggiare il LED per confermare che ha ricevuto il comando
    if led_stato:
        led_stato.blink(on_time=0.2, off_time=0.2)
    os.system("sudo poweroff")

try:
    led_stato = LED(17)
    tasto_power = Button(3, hold_time=2)
except Exception as e:
    print(f"Attenzione: Impossibile configurare i GPIO ({e})")
    led_stato = None 
    tasto_power = None

if tasto_power:
    tasto_power.when_held = spegni_sistema
    print("🔌 Tasto Power configurato sul GPIO 3")


if __name__ == '__main__':
    threading.Thread(target=ascoltatore_udp, daemon=True).start()

    print("Avvio del server Flask VisionShelf...")

    if led_stato:
        led_stato.on()
        print("💡 LED di stato acceso")

    app.run(host='0.0.0.0', port=5000, debug = False)
