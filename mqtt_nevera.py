"""Cliente MQTT compartido entre las páginas de Streamlit.

Streamlit reejecuta el script en cada interacción, por eso el cliente se crea
UNA sola vez con @st.cache_resource y guarda los datos recibidos en memoria.
"""
import json
import threading
import time
from collections import deque
from datetime import datetime

import paho.mqtt.client as paho
import streamlit as st

BROKER = "157.230.214.127"
PORT = 1883

# CAMBIA "CAMBIAME" por tu apellido. Debe ser IGUAL en sketch.ino
TOPIC_BASE = "nevera_CAMBIAME"
TOPIC_CMD = f"{TOPIC_BASE}/cmd"        # Streamlit -> ESP32
TOPIC_ESTADO = f"{TOPIC_BASE}/estado"  # ESP32 -> Streamlit


class NeveraMQTT:
    def __init__(self):
        self.lock = threading.Lock()
        self.estado = {"temp": None, "hum": None, "puerta": "desconocido", "bloqueada": None, "ultimo": None}
        self.historial = deque(maxlen=300)  # (datetime, temperatura)
        self.eventos = deque(maxlen=50)     # (hora, descripcion)
        self.conectado = False

        self.client = paho.Client(
            callback_api_version=paho.CallbackAPIVersion.VERSION2,
            client_id=f"nevera-streamlit-{int(time.time())}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    # ---------- ciclo de vida ----------
    def start(self):
        self.client.connect_async(BROKER, PORT, keepalive=30)
        self.client.loop_start()

    # ---------- callbacks (corren en otro hilo) ----------
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            client.subscribe(TOPIC_ESTADO)
            with self.lock:
                self.conectado = True
                self._evento("Conectado al broker MQTT")

    def _on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        with self.lock:
            self.conectado = False
            self._evento("Desconectado del broker")

    def _on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        ahora = datetime.now()
        with self.lock:
            if data.get("temp") is not None:
                self.estado["temp"] = float(data["temp"])
                self.historial.append((ahora, float(data["temp"])))
            if data.get("hum") is not None:
                self.estado["hum"] = float(data["hum"])
            if data.get("puerta"):
                self.estado["puerta"] = data["puerta"]
            if "bloqueada" in data:
                self.estado["bloqueada"] = bool(data["bloqueada"])
            self.estado["ultimo"] = ahora
            if data.get("evento"):
                texto = data["evento"].replace("_", " ")
                if data.get("articulo"):
                    texto += f" ({data['articulo']})"
                self._evento(texto)

    def _evento(self, texto):
        # Se llama con el lock ya tomado
        self.eventos.appendleft((datetime.now().strftime("%H:%M:%S"), texto))

    # ---------- API para las páginas ----------
    def publicar(self, cmd, **extra):
        payload = json.dumps({"cmd": cmd, **extra})
        info = self.client.publish(TOPIC_CMD, payload)
        with self.lock:
            self._evento(f"Comando enviado: {cmd}")
        return info.rc == 0

    def snapshot(self):
        with self.lock:
            return (
                dict(self.estado),
                list(self.historial),
                list(self.eventos),
                self.conectado,
            )


@st.cache_resource
def get_nevera() -> NeveraMQTT:
    nevera = NeveraMQTT()
    nevera.start()
    return nevera
