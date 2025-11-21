import cv2
import serial
import time
import sys
import requests # ¡La nueva importación!
# Ya no necesitamos postgrest ni asyncio

# --- 1. CONFIGURACIÓN DEL HARDWARE ---
PUERTO_SERIAL = 'COM3'         # ¡REEMPLAZA! Por el puerto de tu Arduino.
VELOCIDAD_SERIAL = 9600
COMANDO_ACTIVAR = 'A'          

# --- 2. CONFIGURACIÓN DE SUPABASE (¡COMPLETA URL Y KEY!) ---
# URL base de tu proyecto Supabase (NO necesita /rest/v1/ al final)
SUPABASE_URL_BASE = "https://hdmymeakubioetnvzzax.supabase.co" 
# Tu clave 'anon key' o clave de servicio.
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhkbXltZWFrdWJpb2V0bnZ6emF4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTE3ODc4NiwiZXhwIjoyMDc0NzU0Nzg2fQ.DQb8lFqrTqS826DSkol1v3uWCHmqhLcgML6M95mQyVw" 

# TABLA Y COLUMNAS (Confirmado: clientes, codigo_qr, fecha_fin)
TABLA_SOCIOS = "clientes" 
COLUMNA_ID = "codigo_qr"           
COLUMNA_VENCIMIENTO = "fecha_fin" 
COLUMNA_NOMBRE = "nombre"     

DELAY_ENTRE_ESCANEOS = 3       
last_status_message = "Sistema Listo - Escanee su QR"

# --- 3. INICIALIZACIÓN ---
# 1. Conexión Serial con Arduino Nano
try:
    ser = serial.Serial(PUERTO_SERIAL, VELOCIDAD_SERIAL, timeout=1)
    print(f"✅ Conexión serial con Arduino establecida en {PUERTO_SERIAL}")
except serial.SerialException as e:
    print(f"❌ ERROR: No se pudo conectar al Arduino. {e}")
    sys.exit()

# 2. Inicializa la webcam
cap = cv2.VideoCapture(0) 
if not cap.isOpened():
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) 
    if not cap.isOpened():
        print("❌ ERROR: No se pudo abrir la webcam.")
        sys.exit()

ultimo_escaneo_valido = 0

# --- 4. FUNCIONES ---

def enviar_pulso_arduino():
    """Envía el comando serial 'A' al Nano para que active el relé."""
    ser.write(COMANDO_ACTIVAR.encode('utf-8'))
    print(f"-> COMANDO ENVIADO: '{COMANDO_ACTIVAR}'")

def validar_membresia(qr_data):
    """Consulta Supabase usando peticiones HTTP simples (requests)."""
    global last_status_message
    
    # Obtener la fecha actual en formato ISO para la consulta
    now = time.strftime('%Y-%m-%dT%H:%M:%S')

    # URL completa de la API con los parámetros de consulta (PostgREST)
    # Filtro: codigo_qr = [QR] AND fecha_fin > [HOY]
    url = f"{SUPABASE_URL_BASE}/rest/v1/{TABLA_SOCIOS}"
    params_active = {
        COLUMNA_ID: f"eq.{qr_data}",
        COLUMNA_VENCIMIENTO: f"gt.{now}",
        "select": COLUMNA_NOMBRE
    }
    
    # Headers necesarios para la autenticación de Supabase
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }

    try:
        # Petición principal: Membresía activa
        response = requests.get(url, headers=headers, params=params_active)
        response.raise_for_status() # Lanza error si la respuesta es 4xx o 5xx
        
        response_data = response.json()

        if response_data and len(response_data) > 0:
            # ACCESO CONCEDIDO
            socio_nombre = response_data[0].get(COLUMNA_NOMBRE, 'Socio')
            last_status_message = f"ACCESO CONCEDIDO: Bienvenido {socio_nombre}"
            return True
        else:
            # Petición secundaria: ¿El QR existe, pero está vencido?
            params_check = {COLUMNA_ID: f"eq.{qr_data}", "select": COLUMNA_NOMBRE}
            response_check = requests.get(url, headers=headers, params=params_check)
            response_check.raise_for_status()
            response_check_data = response_check.json()
            
            if response_check_data and len(response_check_data) > 0:
                 last_status_message = "MEMBRESÍA EXPIRADA. Por favor, renueve."
            else:
                 last_status_message = "QR NO VÁLIDO. Contacte a recepción."

            return False
            
    except requests.exceptions.RequestException as e:
        last_status_message = "ERROR: Falló la conexión HTTP o credenciales."
        print(f"❌ ERROR de red/HTTP: {e}")
        return False
    except Exception as e:
        last_status_message = "ERROR interno de la aplicación."
        print(f"❌ ERROR General: {e}")
        return False

# --- 5. BUCLE PRINCIPAL Y VISUALIZACIÓN (Mismo código) ---

print("🖥️ KIOSCO INICIADO. Presione 'q' para salir.")
print("✅ Conexión con Supabase establecida (vía requests).")


while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame = cv2.flip(frame, 1)

    # Escaneo de QR
    qr_data, puntos_bbox, _ = cv2.QRCodeDetector().detectAndDecode(frame)
    
    if puntos_bbox is not None and qr_data:
        
        # Opcional: Dibujar el recuadro del QR detectado
        puntos = puntos_bbox.astype(int)[0]
        cv2.polylines(frame, [puntos], True, (0, 255, 0), 2)
        
        # Control de Anti-Spam
        if time.time() - ultimo_escaneo_valido >= DELAY_ENTRE_ESCANEOS:
            
            if validar_membresia(qr_data):
                enviar_pulso_arduino()
                
            ultimo_escaneo_valido = time.time()
                
    # --- 6. VISUALIZACIÓN ---
    
    color = (255, 255, 255)
    if "CONCEDIDO" in last_status_message:
        color = (0, 255, 0)
    elif "EXPIRADA" in last_status_message or "ERROR" in last_status_message or "NO VÁLIDO" in last_status_message:
        color = (0, 0, 255)
        
    cv2.putText(frame, last_status_message, (30, 70), 
                cv2.FONT_HERSHEY_SIMPLEX, 1, color, 3)
    
    cv2.imshow('Kiosco Gimnasio - Control de Acceso', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# --- 7. LIMPIEZA FINAL ---
cap.release()
cv2.destroyAllWindows()
ser.close()
print("Sistema de Kiosco apagado. Conexión serial cerrada.")