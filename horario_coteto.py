import streamlit as st
import pandas as pd
from datetime import datetime, time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import defaultdict

# 1) Configuración de la página
st.set_page_config(layout="wide", page_title="Generador de Horario")

# 2) URL “raw” de tu CSV en GitHub
CSV_URL = (
    "https://raw.githubusercontent.com/"
    "federico-pereira/horario_25-2/main/data/horario.csv"
)

@st.cache_data
def load_data(url: str) -> pd.DataFrame:
    return pd.read_csv(url)

# 3) Carga y muestra columnas para que verifiques nombres
df = load_data(CSV_URL)
st.write("📋 Columnas detectadas en tu CSV:", df.columns.tolist())

# 4) Mapea nombres reales a “section_id”, “course_name”, etc.
#    **AJUSTA** este diccionario según las columnas que mostró arriba
COLUMN_MAP = {
    # Ejemplo para un CSV en español:
    # 'SSEC':        'section_id',
    # 'Asignatura':  'course_name',
    # 'Día':         'day',
    # 'Hora Inicio': 'start_time',
    # 'Hora Fin':    'end_time',
    # 'Docente':     'teacher',
}
if COLUMN_MAP:
    df = df.rename(columns=COLUMN_MAP)

# 5) Define aquí los nombres internos que usaremos
SECTION_COL = "section_id"
COURSE_COL  = "course_name"
DAY_COL     = "day"
START_COL   = "start_time"
END_COL     = "end_time"
TEACHER_COL = "teacher"

# 6) Convertir “HH:MM” → datetime.time
df[START_COL] = df[START_COL].apply(lambda t: datetime.strptime(t, "%H:%M").time())
df[END_COL]   = df[END_COL].apply(lambda t: datetime.strptime(t, "%H:%M").time())

# 7) Clase Section (igual que antes)
class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid      = cid
        self.course   = course
        self.meetings = meetings  # [(day, start, end), ...]
        self.teacher  = teacher

    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                          for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

# 8) Orden de días para el gráfico
DAY_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_SHORT = {d: d[:2] for d in DAY_ORDER}

# 9) Construir lista de secciones
sections = []
for _, row in df.iterrows():
    meetings = [(row[DAY_COL], row[START_COL], row[END_COL])]
    sections.append(Section(
        cid     = row[SECTION_COL],
        course  = row[COURSE_COL],
        meetings= meetings,
        teacher = row[TEACHER_COL]
    ))

# 10) Dibujo del horario con matplotlib
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
        if day not in DAY_ORDER:
            continue
        x = DAY_ORDER.index(day)
        y1 = start.hour + start.minute/60
        y2 = end.hour   + end.minute/60
        rect = patches.Rectangle(
            (x-0.4, y1), 0.8, y2-y1,
            edgecolor="black", facecolor="skyblue", alpha=0.7
        )
        ax.add_patch(rect)
        ax.text(
            x, y1 + (y2-y1)/2, sec.course,
            ha="center", va="center", fontsize=9, wrap=True
        )

# 11) Mostrar el plot en Streamlit
st.pyplot(fig)
