import streamlit as st

st.set_page_config(page_title="Nevera inteligente", page_icon="🧊", layout="wide")

# La clave se pide una sola vez y queda disponible para todas las páginas.
# No la escribas en el código ni la subas al repositorio.
with st.sidebar:
    st.text_input("Clave de OpenAI", type="password", key="api_key")

pagina = st.navigation(
    [
        st.Page("chat.py", title="Asistente", icon="💬"),
        st.Page("panel.py", title="Panel de la nevera", icon="🌡️"),
    ]
)
pagina.run()
