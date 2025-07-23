import streamlit as st
import pandas as pd
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import re

# 1) Configuración de la página
st.set_page_config(layout="wide", page_title="Generador de Horario")

# 2) URL raw de tu CSV en GitHub
CSV_URL = "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv"

@st.cache_data
def load_data(url: str) -> pd.DataFrame:
    return pd.read_csv(url)

# 3) Carga el DataFrame y renombra columnas
df = load_data(CSV_URL)
df = df.rename(columns={
    "SSEC":                "section_id",
    "Asignatura":          "course_name",
    "Profesor":            "teacher",
    "Cátedra":             "meetings_raw",
    "Fecha Inicio Clases": "start_date"
})

# 4) Regex para extraer los bloques “Día HH:MM a HH:MM”
MEETING_RE = re.compile(
    r"(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes)\s*"
    r"(\d{1,2}:\d{2})\s*a\s*(\d{1,2}:\d{2})"
)

def parse_meetings(raw: str):
    meetings = []
    for dia, t0, t1 in MEETING_RE.findall(raw):
        h0 = datetime.strptime(t0, "%H:%M").time()
        h1 = datetime.strptime(t1, "%H:%M").time()
        meetings.append((dia, h0, h1))
    return meetings

# 5) Construye lista de objetos Section
class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid      = cid
        self.course   = course
        self.meetings = meetings  # [(día, inicio, fin), ...]
        self.teacher  = teacher

sections = []
for _, row in df.iterrows():
    mts = parse_meetings(row["meetings_raw"])
    if mts:
        sections.append(Section(
            cid      = row["section_id"],
            course   = row["course_name"],
            meetings = mts,
            teacher  = row["teacher"]
        ))

# 6) Sidebar: selección de cursos
all_courses = sorted({sec.course for sec in sections})
selected = st.sidebar.multiselect(
    "Selecciona asignaturas a incluir", all_courses,
    default=all_courses
)

# 7) Sidebar: prioridad (1–5) por curso
st.sidebar.markdown("### Prioridades")
priorities = {}
for course in selected:
    priorities[course] = st.sidebar.slider(
        f"{course}", 1, 5, 3
    )

# 8) Filtra secciones según selección
sections = [sec for sec in sections if sec.course in selected]

# 9) Define orden y abreviaturas de días
DAY_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_SHORT = {d: d[:2] for d in DAY_ORDER}

# 10) Dibujo del horario
fig, ax = plt.subplots(figsize=(12, 6))
ax.set_xticks(range(len(DAY_ORDER)))
ax.set_xticklabels([DAY_SHORT[d] for d in DAY_ORDER])
ax.set_ylim(7, 22)
ax.set_xlim(-0.5, len(DAY_ORDER)-0.5)
ax.set_ylabel("Hora del día")
ax.set_title("Horario de Clases")
ax.grid(axis="y", linestyle="--", alpha=0.5)

# Lleva cuenta de qué días tienen al menos una clase
occupied_days = set()

for sec in sections:
    weight = priorities.get(sec.course, 3)
    color  = "tomato" if weight == 5 else "skyblue"
    lw     = 2.5 if weight == 5 else 1.0

    for dia, start, end in sec.meetings:
        if dia not in DAY_ORDER:
            continue
        occupied_days.add(dia)
        x  = DAY_ORDER.index(dia)
        y1 = start.hour + start.minute/60
        y2 = end.hour   + end.minute/60
        rect = patches.Rectangle(
            (x-0.4, y1), 0.8, y2-y1,
            edgecolor="black", facecolor=color,
            linewidth=lw, alpha=0.7
        )
        ax.add_patch(rect)
        ax.text(
            x, y1+(y2-y1)/2, sec.course,
            ha="center", va="center", fontsize=9, wrap=True
        )

# 11) Contar y mostrar días libres
free_days = [d for d in DAY_ORDER if d not in occupied_days]
st.sidebar.markdown(f"**Días libres:** {len(free_days)}  \n"
                    f"{', '.join(free_days) or '—'}")

# 12) Renderiza el gráfico
st.pyplot(fig)
