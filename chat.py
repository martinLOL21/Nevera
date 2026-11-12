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
    if not api_key:
        st.warning("Ingresa tu clave de OpenAI en la barra lateral.")
    else:
        st.session_state.mensajes.append({"rol": "user", "texto": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        try:
            with st.spinner("Pensando..."):
                resultado = consultar_agente(pregunta, api_key)
            st.session_state.pendiente = resultado["articulo"]
            st.session_state.mensajes.append(
                {"rol": "assistant", "texto": resultado["respuesta"]}
            )
            with st.chat_message("assistant"):
                st.markdown(resultado["respuesta"])
        except Exception as e:
            st.error(f"Error al consultar el agente: {e}")

pendiente = st.session_state.pendiente
if pendiente:
    if st.button(f"🔓 Abrir nevera para sacar: {pendiente}", type="primary"):
        if nevera.publicar("abrir", articulo=pendiente):
            st.success("Comando enviado. La nevera se cerrará sola cuando la temperatura baje.")
            st.session_state.pendiente = None
        else:
            st.error("No se pudo enviar el comando al broker.")
