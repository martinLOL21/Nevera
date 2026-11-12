import pandas as pd
import streamlit as st

from mqtt_nevera import get_nevera

st.title("🌡️ Panel de la nevera")

nevera = get_nevera()

col1, col2, _ = st.columns([1, 1, 4])
if col1.button("🔓 Abrir (manual)"):
    nevera.publicar("abrir", articulo="manual")
if col2.button("🔒 Cerrar (manual)"):
    nevera.publicar("cerrar")


@st.fragment(run_every=2)
def en_vivo():
    estado, historial, eventos, conectado = nevera.snapshot()

    c1, c2, c3 = st.columns(3)
    temp = estado["temp"]
    c1.metric("Temperatura", f"{temp:.1f} °C" if temp is not None else "—")
    c2.metric(
        "Puerta",
        {"abierta": "🔓 Abierta", "cerrada": "🔒 Cerrada"}.get(estado["puerta"], "Sin datos"),
    )
    c3.metric("Broker MQTT", "Conectado" if conectado else "Desconectado")

    if not historial:
        st.info("Esperando datos del ESP32 en Wokwi. ¿Ya iniciaste la simulación?")
    else:
        df = pd.DataFrame(historial, columns=["hora", "Temperatura (°C)"]).set_index("hora")
        st.line_chart(df)

    st.subheader("Registro de eventos")
    if eventos:
        st.dataframe(
            pd.DataFrame(eventos, columns=["Hora", "Evento"]),
            hide_index=True,
            use_container_width=True,
        )


en_vivo()
