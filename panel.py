import pandas as pd
import streamlit as st

from mqtt_nevera import get_nevera

st.title("🌡️ Panel de la nevera")

nevera = get_nevera()


@st.fragment(run_every=2)
def en_vivo():
    estado, historial, eventos, conectado = nevera.snapshot()
    bloqueada = estado.get("bloqueada") is True

    c1, c2, c3, c4 = st.columns(4)
    temp = estado["temp"]
    c1.metric("Temperatura", f"{temp:.1f} °C" if temp is not None else "—")
    c2.metric(
        "Puerta",
        {"abierta": "🔓 Abierta", "cerrada": "🔒 Cerrada"}.get(estado["puerta"], "Sin datos"),
    )
    c3.metric(
        "Seguro térmico",
        "🚫 Bloqueada" if bloqueada else ("✅ Disponible" if estado.get("bloqueada") is False else "—"),
    )
    c4.metric("Broker MQTT", "Conectado" if conectado else "Desconectado")

    if bloqueada:
        st.error(
            "Temperatura alta: la nevera se cerró y no se puede abrir "
            "hasta que la temperatura vuelva a un nivel seguro."
        )

    b1, b2, _ = st.columns([1, 1, 4])
    if b1.button("🔓 Abrir (manual)", disabled=bloqueada, key="abrir_manual"):
        nevera.publicar("abrir", articulo="manual")
    if b2.button("🔒 Cerrar (manual)", key="cerrar_manual"):
        nevera.publicar("cerrar")

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
