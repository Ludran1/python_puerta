import sys
import cv2
import serial
import time
import requests
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout, 
                             QHBoxLayout, QWidget, QFrame, QDialog, QGraphicsDropShadowEffect)
from PyQt5.QtGui import QImage, QPixmap, QFont, QColor
from PyQt5.QtCore import QTimer, Qt
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN
# ==========================================
PUERTO_SERIAL = 'COM3'
VELOCIDAD_SERIAL = 9600
COMANDO_ACTIVAR = 'A'

SUPABASE_URL_BASE = "https://hdmymeakubioetnvzzax.supabase.co" 
# Tu clave 'anon key' o clave de servicio.
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImhkbXltZWFrdWJpb2V0bnZ6emF4Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1OTE3ODc4NiwiZXhwIjoyMDc0NzU0Nzg2fQ.DQb8lFqrTqS826DSkol1v3uWCHmqhLcgML6M95mQyVw" 

TABLA_SOCIOS = "clientes"
COLUMNA_ID = "codigo_qr"
COLUMNA_VENCIMIENTO = "fecha_fin"
COLUMNA_NOMBRE = "nombre"

# *** IMPORTANTE: AJUSTA ESTE NOMBRE ***
# Esta debe ser la columna en la tabla 'clientes' que es la clave foránea a la tabla 'membresias'
COLUMNA_FK_MEMBRESIA = "membresia_id" # Cambia esto si tu columna se llama 'membresia_id', 'id_plan', etc.

DELAY_ENTRE_ESCANEOS = 3
TIEMPO_CIERRE_DIALOGO = 4 
# ... (El resto de la configuración de colores y estilos permanece igual)

# Colores
COLOR_BG_MAIN = "#121212"
COLOR_BG_CARD = "#1E1E24"
COLOR_ACCENT_BLUE = "#4CC9F0"
COLOR_SUCCESS = "#2A9D8F"
COLOR_DANGER = "#E76F51"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#A0A0A9"
COLOR_TEXT_ACCENT = "#FFD700" # Dorado para resaltar

ESTILO_GLOBAL = f"""
    QMainWindow {{ background-color: {COLOR_BG_MAIN}; }}
    QLabel {{ font-family: 'Segoe UI', sans-serif; color: {COLOR_TEXT_PRIMARY}; }}
"""

# ==========================================
# CLASE: VENTANA EMERGENTE
# ==========================================
class ModernDeniedDialog(QDialog):
    def __init__(self, motivo, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True) 
        self.resize(550, 450)

        layout_main = QVBoxLayout()
        layout_main.setAlignment(Qt.AlignCenter)
        self.setLayout(layout_main)

        # Tarjeta
        self.card_frame = QFrame()
        self.card_frame.setFixedSize(500, 400)
        self.card_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1E1E24;
                border-radius: 24px;
                border: 3px solid {COLOR_DANGER};
            }}
        """)
        
        layout_card = QVBoxLayout(self.card_frame)
        layout_card.setContentsMargins(40, 50, 40, 40)
        layout_card.setSpacing(15)

        lbl_icon = QLabel("✕")
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(f"color: {COLOR_DANGER}; font-size: 80px; border: none; background: transparent;")
        layout_card.addWidget(lbl_icon)

        lbl_titulo = QLabel("Acceso Denegado")
        lbl_titulo.setAlignment(Qt.AlignCenter)
        lbl_titulo.setFont(QFont("Segoe UI", 22, QFont.Bold))
        lbl_titulo.setStyleSheet(f"color: {COLOR_DANGER}; border: none; background: transparent;")
        layout_card.addWidget(lbl_titulo)

        lbl_motivo = QLabel(motivo)
        lbl_motivo.setAlignment(Qt.AlignCenter)
        lbl_motivo.setFont(QFont("Segoe UI", 13))
        lbl_motivo.setWordWrap(True)
        lbl_motivo.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; margin: 20px 0; border: none; background: transparent;")
        layout_card.addWidget(lbl_motivo)

        self.countdown = TIEMPO_CIERRE_DIALOGO
        self.lbl_timer = QLabel(f"Cerrando en {self.countdown}...")
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        self.lbl_timer.setFont(QFont("Segoe UI", 10))
        self.lbl_timer.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; border: none; background: transparent;")
        layout_card.addWidget(self.lbl_timer)

        layout_main.addWidget(self.card_frame)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.actualizar_timer)
        self.timer.start(1000)

    def actualizar_timer(self):
        self.countdown -= 1
        if self.countdown > 0:
             self.lbl_timer.setText(f"Cerrando en {self.countdown}...")
        else:
             self.timer.stop()
             self.accept()

# ==========================================
# 2. LÓGICA (BACKEND) - CORRECCIÓN DE ERRORES DE PARSEO
# ==========================================
class GymLogic:
    def __init__(self):
        self.ser = None
        self.ultimo_escaneo = 0
        self.conectar_arduino()

    def conectar_arduino(self):
        try:
            self.ser = serial.Serial(PUERTO_SERIAL, VELOCIDAD_SERIAL, timeout=1)
            print(f"✅ Arduino conectado en {PUERTO_SERIAL}")
        except:
            print(f"⚠️ MODO SIMULACIÓN")

    def abrir_puerta(self):
        if self.ser:
            try:
                self.ser.write(COMANDO_ACTIVAR.encode('utf-8')) 
            except: pass
        else:
            print("-> [SIM] Puerta Abierta")

    def validar_acceso(self, qr_data):
        # Evita escanear demasiado rápido
        if time.time() - self.ultimo_escaneo < DELAY_ENTRE_ESCANEOS: return None, None, None, None
        self.ultimo_escaneo = time.time()
        
        url = f"{SUPABASE_URL_BASE}/rest/v1/{TABLA_SOCIOS}"
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
        
        try:
            # La sintaxis de selección con JOIN implícito (e.g., id_membresia(nombre))
            select_cols = f"{COLUMNA_NOMBRE},{COLUMNA_VENCIMIENTO},{COLUMNA_FK_MEMBRESIA}(nombre)"
            params_full = {COLUMNA_ID: f"eq.{qr_data}", "select": select_cols}
            
            r = requests.get(url, headers=headers, params=params_full)
            r.raise_for_status() # Lanza error si la consulta HTTP falló (4xx o 5xx)
            data = r.json()
            
            if not data:
                return False, "Código No Registrado", None, None

            socio_info = data[0]
            nombre = socio_info.get(COLUMNA_NOMBRE, 'Socio')
            fecha_vencimiento_str = socio_info.get(COLUMNA_VENCIMIENTO)
            
            # -----------------------------------------------------------------
            # *** CÓDIGO CORREGIDO PARA EXTRACCIÓN DE MEMBRESÍA ***
            # -----------------------------------------------------------------
            membresia_obj = socio_info.get(COLUMNA_FK_MEMBRESIA)
            membresia = "Desconocida"
            
            if membresia_obj and isinstance(membresia_obj, dict):
                # Si el objeto existe y es un diccionario (como se espera con el JOIN)
                membresia = membresia_obj.get("nombre", "Desconocida")
            
            # -----------------------------------------------------------------

            if not fecha_vencimiento_str:
                 return True, nombre, "Fecha no definida", membresia

            fecha_vencimiento = datetime.strptime(fecha_vencimiento_str.split('T')[0], '%Y-%m-%d')
            fecha_actual = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            
            fecha_vencimiento_formato = fecha_vencimiento.strftime('%d/%m/%Y')
            
            if fecha_vencimiento >= fecha_actual:
                return True, nombre, fecha_vencimiento_formato, membresia
            else:
                return False, f"Membresía Vencida el {fecha_vencimiento_formato}", None, membresia
                
        except requests.exceptions.RequestException as e:
            # Captura errores de red o del servidor (e.g., 401, 404, 500)
            print(f"Error HTTP o de Conexión: {e}")
            return False, "Error de Conexión o Servidor", None, None
        except Exception as e:
            # Captura cualquier otro error, como un fallo en el parseo del JSON si no es válido.
            print(f"Error inesperado durante la validación o parseo de datos: {e}")
            return False, "Error interno del sistema", None, None

# ==========================================
# 3. INTERFAZ PRINCIPAL
# ==========================================
class ModernFitGymKiosk(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logic = GymLogic()
        self.setWindowTitle("FitGym OS")
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        layout_H = QHBoxLayout()
        layout_H.setContentsMargins(40, 40, 40, 40)
        layout_H.setSpacing(40)
        main_widget.setLayout(layout_H)

        # === PANEL IZQUIERDO (VIDEO + CONTACTO + HORA) ===
        left_panel = QWidget()
        layout_left = QVBoxLayout(left_panel)
        layout_left.setContentsMargins(0, 0, 0, 0)
        layout_left.setSpacing(20) # Espacio entre video y contacto

        # A. VIDEO CONTAINER
        video_container = QFrame()
        video_container.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 24px; }}")
        
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20); shadow.setColor(QColor(0,0,0,80))
        video_container.setGraphicsEffect(shadow)
        
        layout_video = QVBoxLayout(video_container)
        layout_video.setContentsMargins(0, 0, 0, 0)
        layout_video.setAlignment(Qt.AlignCenter)
        
        self.video_label = QLabel("Iniciando...")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet(f"background-color: #000; border-radius: 24px;")
        self.video_label.setMinimumSize(800, 600)
        
        layout_video.addWidget(self.video_label)
        layout_left.addWidget(video_container, stretch=1) # El video ocupa la mayor parte verticalmente

        # B. CONTACTO Y HORA (AHORA DEBAJO DEL VIDEO)
        bottom_row = QFrame()
        bottom_row.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 24px; }}")
        
        layout_bottom_row = QHBoxLayout(bottom_row)
        layout_bottom_row.setContentsMargins(30, 15, 30, 15)
        
        # HORA (GRANDE)
        self.lbl_clock = QLabel("--:--")
        self.lbl_clock.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # *** HORA MÁS GRANDE ***
        self.lbl_clock.setFont(QFont("Segoe UI", 36, QFont.Bold))
        self.lbl_clock.setStyleSheet(f"color: {COLOR_ACCENT_BLUE};")
        layout_bottom_row.addWidget(self.lbl_clock)
        
        layout_bottom_row.addStretch()

        # NÚMERO DE CONTACTO
        lbl_contact = QLabel("Consultas: 960 930 024")
        lbl_contact.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lbl_contact.setFont(QFont("Segoe UI", 14, QFont.Bold))
        lbl_contact.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        layout_bottom_row.addWidget(lbl_contact)
        
        layout_left.addWidget(bottom_row, stretch=0) # La fila de abajo no se estira verticalmente

        # Panel Izquierdo (Cámara y Contacto) ocupa stretch=6
        layout_H.addWidget(left_panel, stretch=6)


        # === SIDEBAR (PANEL DERECHO) ===
        sidebar_container = QFrame()
        sidebar_container.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 24px; }}")
        
        shadow2 = QGraphicsDropShadowEffect()
        shadow2.setBlurRadius(20); shadow2.setColor(QColor(0,0,0,80))
        sidebar_container.setGraphicsEffect(shadow2)

        layout_sidebar = QVBoxLayout(sidebar_container)
        layout_sidebar.setContentsMargins(30, 50, 30, 50)
        
        # 1. Título del Gimnasio (FITGYM)
        lbl_brand = QLabel("FITGYM")
        lbl_brand.setFont(QFont("Segoe UI", 48, QFont.Bold))
        lbl_brand.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; letter-spacing: 3px;")
        lbl_brand.setAlignment(Qt.AlignCenter)
        layout_sidebar.addWidget(lbl_brand)

        # 2. Subtítulo (Slogan)
        lbl_sub = QLabel("Acceso Inteligente")
        lbl_sub.setFont(QFont("Segoe UI", 14))
        lbl_sub.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; margin-bottom: 40px;")
        lbl_sub.setAlignment(Qt.AlignCenter)
        layout_sidebar.addWidget(lbl_sub)
        
        # --- ESTADO DE ESCANEO ---
        self.status_card = QLabel("Listo para escanear")
        self.status_card.setAlignment(Qt.AlignCenter)
        self.status_card.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.status_card.setWordWrap(True)
        self.estilo_neutro = f"background-color: rgba(255,255,255,0.05); color: {COLOR_TEXT_SECONDARY}; border-radius: 18px; padding: 40px 20px;"
        self.status_card.setStyleSheet(self.estilo_neutro)
        layout_sidebar.addWidget(self.status_card)

        # --- INFO DEL CLIENTE ---
        lbl_socio = QLabel("MIEMBRO")
        lbl_socio.setFont(QFont("Segoe UI", 11, QFont.Bold))
        lbl_socio.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; margin-top: 50px;")
        lbl_socio.setAlignment(Qt.AlignCenter)
        layout_sidebar.addWidget(lbl_socio)

        self.lbl_socio_name = QLabel("---")
        self.lbl_socio_name.setFont(QFont("Segoe UI", 24))
        self.lbl_socio_name.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; margin-bottom: 10px;")
        self.lbl_socio_name.setAlignment(Qt.AlignCenter)
        layout_sidebar.addWidget(self.lbl_socio_name)
        
        # *** NUEVO LABEL PARA LA MEMBRESÍA ***
        self.lbl_membresia = QLabel("")
        self.lbl_membresia.setFont(QFont("Segoe UI", 18, QFont.Bold))
        self.lbl_membresia.setStyleSheet(f"color: {COLOR_ACCENT_BLUE}; margin-bottom: 20px;")
        self.lbl_membresia.setAlignment(Qt.AlignCenter)
        layout_sidebar.addWidget(self.lbl_membresia)

        # Label para la fecha de vencimiento (MÁS VISIBLE)
        self.lbl_vencimiento = QLabel("")
        # *** FECHA DE VENCIMIENTO MÁS GRANDE Y EN NEGRITA ***
        self.lbl_vencimiento.setFont(QFont("Segoe UI", 20, QFont.Bold))
        self.lbl_vencimiento.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; margin-bottom: 30px;")
        self.lbl_vencimiento.setAlignment(Qt.AlignCenter)
        layout_sidebar.addWidget(self.lbl_vencimiento)

        layout_sidebar.addStretch()

        # La hora ya no está aquí, ahora está debajo de la cámara
        
        # El panel derecho (Sidebar) mantiene stretch=2
        layout_H.addWidget(sidebar_container, stretch=2) 

        # --- INIT ---
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        if not self.cap.isOpened(): self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        self.detector = cv2.QRCodeDetector()
        
        self.timer_vid = QTimer(); self.timer_vid.timeout.connect(self.update_frame); self.timer_vid.start(30)
        self.timer_reset = QTimer(); self.timer_reset.setSingleShot(True); self.timer_reset.timeout.connect(self.reset_ui)
        self.timer_clock = QTimer(); self.timer_clock.timeout.connect(self.update_clock); self.timer_clock.start(1000)
        
        self.dialog_open = False

    def update_clock(self): self.lbl_clock.setText(time.strftime("%H:%M"))

    def update_frame(self):
        if self.dialog_open: return
        ret, frame = self.cap.read()
        if ret:
            frame = cv2.flip(frame, 1)
            data, bbox, _ = self.detector.detectAndDecode(frame)
            if bbox is not None and data:
                pts = bbox.astype(int)[0]
                cv2.polylines(frame, [pts], True, (76, 201, 240), 4) 
                
                # Acceso, Mensaje, Vencimiento, Membresía
                acceso, msg, vencimiento, membresia = self.logic.validar_acceso(data)
                if acceso is not None: 
                    self.show_result(acceso, msg, vencimiento, membresia)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qt_img = QImage(rgb.data, w, h, ch*w, QImage.Format_RGB888)
            
            pixmap = QPixmap.fromImage(qt_img)
            
            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            ))

    def show_result(self, valid, msg, vencimiento=None, membresia=None):
        self.lbl_socio_name.setText(msg.split("Membresía Vencida")[0].strip() if "Vencida" in msg else msg)
        
        if valid:
            self.status_card.setText("¡Bienvenido!")
            self.status_card.setStyleSheet(f"background-color: {COLOR_SUCCESS}; color: white; border-radius: 18px; padding: 40px 20px;")
            
            if membresia:
                 self.lbl_membresia.setText(membresia.upper())
            
            if vencimiento:
                 self.lbl_vencimiento.setText(f"VENCE: {vencimiento}")
            else:
                 self.lbl_vencimiento.setText("")
                 
            self.logic.abrir_puerta()
            self.timer_reset.start(4000)
        else:
            self.dialog_open = True
            
            overlay = QWidget(self)
            overlay.setStyleSheet("background-color: rgba(0, 0, 0, 200);")
            overlay.resize(self.size())
            overlay.show()
            
            dialog = ModernDeniedDialog(msg, self)
            dialog.exec_()
            
            overlay.close()
            self.dialog_open = False
            self.reset_ui()

    def reset_ui(self):
        self.status_card.setText("Listo para escanear")
        self.status_card.setStyleSheet(self.estilo_neutro)
        self.lbl_socio_name.setText("---")
        self.lbl_vencimiento.setText("")
        self.lbl_membresia.setText("")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, e): self.cap.release(); e.accept()

if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 12))
    app.setStyleSheet(ESTILO_GLOBAL)
    window = ModernFitGymKiosk()
    window.showFullScreen()
    sys.exit(app.exec_())