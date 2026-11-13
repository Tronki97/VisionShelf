import cv2
import subprocess
import json
import os
import math
from datetime import datetime

# 1. PERCORSI ASSOLUTI: Il sistema saprà sempre esattamente dove salvare i file
DIR_BASE = os.path.dirname(os.path.abspath(__file__))
image_path = os.path.join(DIR_BASE, "test_foto.jpg")
output_path = os.path.join(DIR_BASE, "risultato_aruco.jpg")
json_path = os.path.join(DIR_BASE, "markers.json")


aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
parameters = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
MAX_LED = 40

comando = ["rpicam-jpeg", "-n", "-t", "1000", "-o", image_path, "--width", "2592", "--height", "1944"]


def aggiorna_restituzioni(id):
    #id: una lista semplice di numeri
    percorso_logs = "logs.json" 
    
    try:
        with open(percorso_logs, "r") as f:
            logs = json.load(f)
            
        salvataggio_necessario = False
        
        for log in logs:
            if log["data_restituzione"] is None and log["id"] in id:
                
                # Registra l'orario di rientro
                log["data_restituzione"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                salvataggio_necessario = True
                print(f"📷 Telecamera: Oggetto {log['nome']} (ID {log['id']}) tornato al suo posto!")
                
        if salvataggio_necessario:
            with open(percorso_logs, "w") as f:
                json.dump(logs, f, indent=4)
                
    except Exception as e:
        print(f"Errore durante l'aggiornamento dei log: {e}")





try:
    # Esegue il comando per scattare la foto
    subprocess.run(comando, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Controlla che il file esista e sia leggibile
    if not os.path.exists(image_path):
        raise FileNotFoundError("La fotocamera non ha salvato l'immagine.")

    with open("config.json", "r") as f:
        config = json.load(f)

    frame = cv2.imread(image_path)
    if frame is None:
        raise ValueError("Immagine corrotta o illeggibile.")
        
    lista_risultati = [] 
    
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gray)
        
    if ids is not None:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        
        # Separa i LED fissi (Ancore) dagli Oggetti Mobili
        ancore_led = {}  # Dizionario { id_led: (X, Y) }
        oggetti = []     # Lista di dizionari per gli oggetti
        id_oggetti = []

        for indice, angoli_marker in enumerate(corners):
            angoli = angoli_marker[0]
            id_corrente = int(ids[indice])
            
            # Calcolo del centro del marker
            cX = int(sum([a[0] for a in angoli]) / 4)
            cY = int(sum([a[1] for a in angoli]) / 4)
            
            cv2.circle(frame, (cX, cY), 5, (0, 0, 255), -1)
            
            if id_corrente <= MAX_LED: #id di un'ancora
                ancore_led[id_corrente] = (cX, cY)
                cv2.putText(frame, f"LED {id_corrente}", (cX - 40, cY - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
            else: #oggetto da cercare

                oggetti.append({
                    "id": id_corrente,
                    "x": cX,
                    "y": cY
                })
                id_oggetti.append(id_corrente)
                cv2.putText(frame, f"Obj {id_corrente}", (cX - 40, cY - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Per ogni oggetto, trova il LED più vicino fisicamente nella foto
        for obj in oggetti:
            led_piu_vicino = None
            distanza_minima = float('inf')
            
            for id_led, coordinate_led in ancore_led.items():
                distanza = math.dist((obj["x"], obj["y"]), coordinate_led)
                
                if distanza < distanza_minima:
                    distanza_minima = distanza
                    led_piu_vicino = id_led
            
            if led_piu_vicino is not None:
                obj["zona"] = f"Vicino a LED {led_piu_vicino}"
                obj["led_target"] = led_piu_vicino
                
                cv2.line(frame, (obj["x"], obj["y"]), ancore_led[led_piu_vicino], (0, 255, 0), 2)
                
                # Aggiunge l'oggetto abbinato alla lista finale da salvare nel JSON
                lista_risultati.append(obj)


    cv2.imwrite(output_path, frame)
    aggiorna_restituzioni(id_oggetti)
    
    with open(json_path, "w") as f:
        json.dump(lista_risultati, f, indent=4)
        
    print(f"✅ Scansione completata! Trovati {len(lista_risultati)} marker.")
    
except Exception as e:
    print(f"❌ Errore durante la scansione: {e}")
    # in caso di errore, salva un file vuoto per non bloccare il sito web
    with open(json_path, "w") as f:
        json.dump([], f)
