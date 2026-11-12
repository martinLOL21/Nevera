import json
import unicodedata

import streamlit as st
from langchain_openai import ChatOpenAI

from mqtt_nevera import get_nevera

# Inventario simulado de la nevera (artículo -> cantidad)
INVENTARIO = {
    "leche": 2,
    "huevos": 12,
    "queso": 1,
    "jugo de naranja": 1,
    "yogur": 4,
    "mantequilla": 1,
    "gaseosa": 0,
    "pollo": 0,
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", str(texto).lower().strip())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def buscar_en_inventario(nombre):
    """Devuelve la clave real del inventario o None. Esta es la validación que
    manda: el modelo puede equivocarse, el inventario no."""
    if not nombre:
        return None
    n = normalizar(nombre)
    for clave in INVENTARIO:
        if normalizar(clave) == n:
            return clave
    return None


def consultar_local(pregunta: str) -> dict:
    """Modo sin IA: busca por palabras clave el artículo en el inventario."""
    texto = normalizar(pregunta)
    for clave, cantidad in INVENTARIO.items():
        k = normalizar(clave)
        # coincide con singular/plural simple (huevo/huevos, yogur/yogures)
        raiz = k[:-1] if k.endswith("s") else k
        if raiz in texto:
            if cantidad > 0:
                return {"respuesta": f"Sí, tienes {cantidad} unidad(es) de {clave}.", "articulo": clave}
            return {"respuesta": f"No te queda {clave}.", "articulo": None}
    return {"respuesta": "No encontré ese artículo en la nevera.", "articulo": None}


def consultar_agente(pregunta: str, api_key: str) -> dict:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=api_key).bind(
        response_format={"type": "json_object"}
    )
    mensajes = [
        (
            "system",
            "Eres el asistente de una nevera inteligente. Usando únicamente el inventario "
            "dado, responde SOLO con un objeto JSON con estas claves: "
            "'existe' (booleano: hay al menos una unidad del artículo preguntado), "
            "'articulo' (nombre EXACTO como aparece en el inventario, o null si no está), "
            "'respuesta' (texto corto y amable en español). "
            "Si el usuario no pregunta por un artículo, existe=false y articulo=null.",
        ),
        (
            "human",
            f"Inventario: {json.dumps(INVENTARIO, ensure_ascii=False)}\n\nPregunta: {pregunta}",
        ),
    ]
    datos = json.loads(llm.invoke(mensajes).content)

    # Validación en Python: solo se ofrece abrir si el artículo existe y hay stock.
    clave = buscar_en_inventario(datos.get("articulo"))
    hay = bool(datos.get("existe")) and clave is not None and INVENTARIO[clave] > 0
    return {
        "respuesta": datos.get("respuesta", ""),
        "articulo": clave if hay else None,
    }


# ------------------------- Interfaz -------------------------
st.title("🧊 Nevera inteligente")
st.caption("Pregunta si tienes un artículo. Solo si existe podrás abrir la nevera.")

nevera = get_nevera()
api_key = st.session_state.get("api_key", "")

st.session_state.setdefault("mensajes", [])
st.session_state.setdefault("pendiente", None)

with st.expander("Inventario actual"):
    st.json(INVENTARIO)

for m in st.session_state.mensajes:
    with st.chat_message(m["rol"]):
        st.markdown(m["texto"])

pregunta = st.chat_input("Ej: ¿tengo leche?")
if pregunta:
    st.session_state.mensajes.append({"rol": "user", "texto": pregunta})
    with st.chat_message("user"):
        st.markdown(pregunta)

    modo = "IA"
    if api_key:
        try:
            with st.spinner("Pensando..."):
                resultado = consultar_agente(pregunta, api_key)
        except Exception as e:
            st.warning(f"La IA no respondió ({type(e).__name__}). Uso el modo sin IA.")
            resultado = consultar_local(pregunta)
            modo = "sin IA"
    else:
        resultado = consultar_local(pregunta)
        modo = "sin IA"

    st.session_state.pendiente = resultado["articulo"]
    texto = resultado["respuesta"] + (f"\n\n*(modo {modo})*" if modo != "IA" else "")
    st.session_state.mensajes.append({"rol": "assistant", "texto": texto})
    with st.chat_message("assistant"):
        st.markdown(texto)

pendiente = st.session_state.pendiente
bloqueada = nevera.snapshot()[0].get("bloqueada") is True
if pendiente:
    if bloqueada:
        st.warning(
            "La nevera está bloqueada por temperatura alta. "
            "Podrás abrirla cuando vuelva a un nivel seguro."
        )
    if st.button(
        f"🔓 Abrir nevera para sacar: {pendiente}", type="primary", disabled=bloqueada
    ):
        if nevera.publicar("abrir", articulo=pendiente):
            st.success("Comando enviado.")
            st.session_state.pendiente = None
        else:
            st.error("No se pudo enviar el comando al broker.")
