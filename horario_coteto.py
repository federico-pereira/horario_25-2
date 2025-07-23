import streamlit as st
import pandas as pd
from datetime import datetime, time
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from itertools import product
from collections import defaultdict

# Configuración de la página
st.set_page_config(layout="wide", page_title="Generador de Horario")

# URL raw de tu CSV en GitHub
CSV_URL = "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario%20UAI%2025-2.csv"

@st.cache_data
def load_data(url: str) -> pd.DataFrame:
    """Descarga y retorna el DataFrame del CSV."""
    return pd.read_csv(url)

# Carga de datos
df = load_data(CSV_URL)

# --- Ajusta según tus nombres de columna ---
# Convierte cadenas "HH:MM" a objetos datetime.time
df['start_time'] = df['start_time'].apply(lambda t: datetime.strptime(t, "%H:%M").time())
df['end_time']   = df['end_time'].apply(lambda t: datetime.strptime(t, "%H:%M").time())

# Clase Section idéntica a la tuya
class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid      = cid
        self.course   = course
        self.meetings = meetings   # lista de tuplas (día, inicio, fin)
        self.teacher  = teacher

    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                          for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

# Orden y abreviatura de días para el eje X
DAY_ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
DAY_SHORT = {d: d[:2] for d in DAY_ORDER}

# Construcción de la lista de secciones
sections = []
for _, row in df.iterrows():
    cid     = row['section_id']
    course  = row['course_name']
    teacher = row['teacher']
    meetings= [(row['day'], row['start_time'], row['end_time'])]
    sections.append(Section(cid, course, meetings, teacher))

# --- Dibujo del horario ---
fig, ax = plt.subplots(figsize=(12, 6))

# Configuración de ejes
ax.set_xticks(range(len(DAY_ORDER)))
ax.set_xticklabels([DAY_SHORT[d] for d in DAY_ORDER])
ax.set_ylim(7, 22)  # horario desde 7:00 hasta 22:00
ax.set_xlim(-0.5, len(DAY_ORDER)-0.5)
ax.set_ylabel("Hora del día")
ax.set_title("Horario de Clases")
ax.grid(axis='y', linestyle='--', alpha=0.5)

# Dibujar cada sección como un rectángulo
for sec in sections:
    for day, start, end in sec.meetings:
        if day not in DAY_ORDER:
            continue
        x = DAY_ORDER.index(day)
        y1 = start.hour + start.minute/60
        y2 = end.hour   + end.minute/60
        height = y2 - y1

        rect = patches.Rectangle(
            (x - 0.4, y1),    # (x, y)
            0.8,              # ancho
            height,           # alto
            edgecolor='black',
            facecolor='skyblue',
            alpha=0.7
        )
        ax.add_patch(rect)
        ax.text(
            x, 
            y1 + height/2, 
            sec.course, 
            ha='center', 
            va='center', 
            fontsize=9,
            wrap=True
        )

# Mostrar con Streamlit
st.pyplot(fig)
