import streamlit as st
import pandas as pd
from datetime import datetime, time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import defaultdict
import urllib.error

# 1) Configuración de la página
st.set_page_config(layout="wide", page_title="Generador de Horario")

# 2) URL “raw” de tu CSV en GitHub (ajusta si tu CSV está en otra ruta o en otra rama)
CSV_URL = "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv"


@st.cache_data
def load_data_remote(url: str) -> pd.DataFrame:
    try:
        return pd.read_csv(url)
    except Exception as e:
        # Propaga la excepción para manejarla afuera
        raise urllib.error.URLError(e)

# 3) Intentamos cargar remotamente
df: pd.DataFrame
try:
    df = load_data_remote(CSV_URL)
    st.success(f"✅ CSV cargado desde GitHub: {CSV_URL}")
except Exception as err:
    st.error(f"❌ No se pudo cargar el CSV remoto:\n{err}")
    st.info("Por favor, verifica que la URL apunte al archivo RAW correcto o súbelo manualmente:")
    uploaded = st.file_uploader("Sube tu CSV aquí", type="csv")
    if uploaded is not None:
        df = pd.read_csv(uploaded)
    else:
        st.stop()  # Detiene la ejecución si no hay CSV

# 4) Muestra las columnas para que ajustes tu mapeo
st.write("📋 Columnas detectadas en tu CSV:", df.columns.tolist())

# 5) Mapea nombres reales a nombres internos estándar
COLUMN_MAP = {
    # Ejemplo: 'SSEC': 'section_id',
    #          'Asignatura': 'course_name',
    #          'Día': 'day',
    #          'Hora Inicio': 'start_time',
    #          'Hora Fin': 'end_time',
    #          'Docente': 'teacher',
}
if COLUMN_MAP:
    df = df.rename(columns=COLUMN_MAP)

# 6) Define aquí tus nombres internos
SECTION_COL = "section_id"
COURSE_COL  = "course_name"
DAY_COL     = "day"
START_COL   = "start_time"
END_COL     = "end_time"
TEACHER_COL = "teacher"

# 7) Convierte “HH:MM” → datetime.time
df[START_COL] = df[START_COL].apply(lambda t: datetime.strptime(t, "%H:%M").time())
df[END_COL]   = df[END_COL].apply(lambda t: datetime.strptime(t, "%H:%M").time())

# 8) Clase Section
class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid      = cid
        self.course   = course
        self.meetings = meetings
        self.teacher  = teacher

    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                          for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

# 9) Orden de días
DAY_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_SHORT = {d: d[:2] for d in DAY_ORDER}

# 10) Construir secciones
sections = []
for _, row in df.iterrows():
    day = row[DAY_COL]
    if day not in DAY_ORDER:
        continue
    meetings = [(day, row[START_COL], row[END_COL])]
    sections.append(Section(
        cid     = row[SECTION_COL],
        course  = row[COURSE_COL],
        meetings= meetings,
        teacher = row[TEACHER_COL]
    ))

# 11) Dibujo con matplotlib
fig, ax = plt.subplots(figsize=(12, 6))
ax.set_xticks(range(len(DAY_ORDER)))
ax.set_xticklabels([DAY_SHORT[d] for d in DAY_ORDER])
ax.set_ylim(7, 22)
ax.set_xlim(-0.5, len(DAY_ORDER)-0.5)
ax.set_ylabel("Hora del día")
ax.set_title("Horario de Clases")
ax.grid(axis="y", linestyle="--", alpha=0.5)

for sec in sections:
    for day, start, end in sec.meetings:
        x = DAY_ORDER.index(day)
        y1 = start.hour + start.minute/60
        y2 = end.hour   + end.minute/60
        rect = patches.Rectangle((x-0.4, y1), 0.8, y2-y1,
                                 edgecolor="black", facecolor="skyblue", alpha=0.7)
        ax.add_patch(rect)
        ax.text(x, y1 + (y2-y1)/2, sec.course,
                ha="center", va="center", fontsize=9, wrap=True)

st.pyplot(fig)
