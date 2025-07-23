import streamlit as st
import pandas as pd
from datetime import datetime, time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from collections import defaultdict
import re

# 1) Configuración de la página
st.set_page_config(layout="wide", page_title="Generador de Horario")

# 2) URL raw de tu CSV en GitHub (ya verificado)
CSV_URL = "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv"

@st.cache_data
def load_data(url: str) -> pd.DataFrame:
    return pd.read_csv(url)

# 3) Carga datos y muestra columnas
df = load_data(CSV_URL)
st.write("📋 Columnas detectadas:", df.columns.tolist())

# 4) Renombrar columnas a nombres internos
df = df.rename(columns={
    "SSEC":        "section_id",
    "Asignatura":  "course_name",
    "Profesor":    "teacher",
    "Cátedra":     "meetings_raw"
})

# 5) Función para parsear la cadena de reuniones
MEETING_RE = re.compile(
    r"(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes)\s*"
    r"(\d{1,2}:\d{2})\s*a\s*(\d{1,2}:\d{2})"
)

def parse_meetings(raw: str):
    """Devuelve lista de tuplas (día, time_inicio, time_fin)."""
    meetings = []
    for dia, t0, t1 in MEETING_RE.findall(raw):
        h0 = datetime.strptime(t0, "%H:%M").time()
        h1 = datetime.strptime(t1, "%H:%M").time()
        meetings.append((dia, h0, h1))
    return meetings

# 6) Construir lista de sections
class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid      = cid
        self.course   = course
        self.meetings = meetings  # [(día, inicio, fin), ...]
        self.teacher  = teacher

    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                          for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

sections = []
for _, row in df.iterrows():
    mts = parse_meetings(row["meetings_raw"])
    if not mts:
        continue
    sections.append(Section(
        cid      = row["section_id"],
        course   = row["course_name"],
        meetings = mts,
        teacher  = row["teacher"]
    ))

# 7) Parámetros del gráfico
DAY_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_SHORT = {d: d[:2] for d in DAY_ORDER}

fig, ax = plt.subplots(figsize=(12, 6))
ax.set_xticks(range(len(DAY_ORDER)))
ax.set_xticklabels([DAY_SHORT[d] for d in DAY_ORDER])
ax.set_ylim(7, 22)
ax.set_xlim(-0.5, len(DAY_ORDER)-0.5)
ax.set_ylabel("Hora del día")
ax.set_title("Horario de Clases")
ax.grid(axis="y", linestyle="--", alpha=0.5)

# 8) Dibujar cada sección
for sec in sections:
    for dia, start, end in sec.meetings:
        if dia not in DAY_ORDER:
            continue
        x = DAY_ORDER.index(dia)
        y1 = start.hour + start.minute/60
        y2 = end.hour   + end.minute/60
        rect = patches.Rectangle(
            (x - 0.4, y1),
            0.8,
            y2 - y1,
            edgecolor="black",
            facecolor="skyblue",
            alpha=0.7
        )
        ax.add_patch(rect)
        ax.text(
            x, y1 + (y2 - y1)/2,
            sec.course,
            ha="center",
            va="center",
            fontsize=9,
            wrap=True
        )

# 9) Mostrar en Streamlit
st.pyplot(fig)
