
import streamlit as st
import pandas as pd
import unicodedata
from datetime import datetime, time
from itertools import product
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import re

# ----- Helpers -----

def strip_accents(s: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )

MEETING_RE = re.compile(
    r"(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes)\s*"
    r"(\d{1,2}:\d{2}:?\d{0,2})\s*[-aA]\s*(\d{1,2}:\d{2}:?\d{0,2})"
)

def parse_meetings(raw: str):
    meetings = []
    for dia, t0, t1 in MEETING_RE.findall(raw):
        fmt = "%H:%M:%S" if t0.count(':')==2 else "%H:%M"
        h0 = datetime.strptime(t0, fmt).time()
        h1 = datetime.strptime(t1, fmt).time()
        meetings.append((dia, h0, h1))
    return meetings

class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid = cid
        self.course = course
        self.meetings = meetings
        self.teacher = teacher
    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for d,s,e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

# ----- Scheduling Logic -----

def build_courses(df):
    by_sec = defaultdict(list)
    for _, r in df.iterrows():
        by_sec[r['Sección']].append(r)
    courses = defaultdict(list)
    for sec_id, rows in by_sec.items():
        meetings = [ (d, s, e) for d,s,e in [parse_meetings(r['Cátedra'])[0] for r in rows] ]
        course  = rows[0]['Asignatura']
        teacher = rows[0]['Profesor']
        courses[course].append(Section(sec_id, course, meetings, teacher))
    return courses

# overlaps and compute functions same as CLI version

def overlaps(a: Section, b: Section) -> bool:
    for d1,s1,e1 in a.meetings:
        for d2,s2,e2 in b.meetings:
            if d1==d2 and s1<e2 and s2<e1:
                return True
    return False

# ----- Streamlit App -----

def main():
    st.title("Generador de Horarios con Prioridades")

    # 1) Cargar CSV desde GitHub
    csv_url = st.sidebar.text_input("URL raw de GitHub:", value="https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv")
    df = pd.read_csv(csv_url)

    # Mostrar columnas
    st.sidebar.write("Columnas detectadas:", df.columns.tolist())

    # 2) Selección múltiple de asignaturas
    sections = []
    df = df.rename(columns={'SSEC':'Sección','Asignatura':'Asignatura','Profesor':'Profesor','Cátedra':'Cátedra'})
    courses = build_courses(df)
    all_courses = sorted(courses.keys())
    sel_courses = st.sidebar.multiselect("Asignaturas:", all_courses, default=all_courses)
    courses = {c:courses[c] for c in sel_courses}

    # 3) Selección múltiple de profesores vetados
    all_teachers = sorted({sec.teacher for secs in courses.values() for sec in secs})
    banned = st.sidebar.multiselect("Vetar profesores:", all_teachers)

    # 4) Ranking de preferencia de profesores
    ranking = {}
    st.sidebar.markdown("### Ranking Docentes (orden de preferencia)")
    rank_selection = st.sidebar.multiselect("Orden de preferencia:", all_teachers, default=all_teachers)
    for idx, t in enumerate(rank_selection):
        ranking[t] = idx

    # 5) Franja y días libres mínimos
    slot = st.sidebar.selectbox("Franja (Mañana/Tarde/Ambos):", ['Ambos','Mañana','Tarde'])
    min_free = st.sidebar.slider("Mínimo días libres:", 0, 5, 1)

    # 6) Pesos
    weights = {
        'rank': st.sidebar.slider('Peso ranking',1,5,3),
        'win' : st.sidebar.slider('Peso ventana',1,5,3),
        'off' : st.sidebar.slider('Peso días libres',1,5,3),
        'ban' : st.sidebar.slider('Peso vetos',1,5,3),
        'slot': st.sidebar.slider('Peso franja',1,5,3)
    }

    # 7) Computar soluciones
    scored = compute_schedules(courses, ranking, slot, min_free, weights, set(banned))
    if not scored:
        st.warning("No se encontraron soluciones válidas.")
        return

    # 8) Mostrar top 3 soluciones
    st.subheader("Top 3 soluciones")
    for i, (sc, combo) in enumerate(scored[:3], 1):
        st.markdown(f"**Solución {i} (score: {sc:.2f})**")
        for sec in combo:
            st.write(str(sec))

    # 9) Visualizar mejor horario
    st.subheader("Horario óptimo")
    best = scored[0][1]
    visualize_streamlit(best)

# Visualización Streamlit

def visualize_streamlit(sections):
    DAY_ORDER = ['Lunes','Martes','Miércoles','Jueves','Viernes']
    DAY_IDX = {d:i for i,d in enumerate(DAY_ORDER)}
    fig, ax = plt.subplots(figsize=(10,6))
    ax.set_xticks([i+0.5 for i in range(len(DAY_ORDER))])
    ax.set_xticklabels(DAY_ORDER)
    ax.set_ylim(20,8); ax.set_xlim(0,5)
    ax.set_ylabel('Hora'); ax.grid(True,'both','--',0.5)

    colors = plt.cm.tab20.colors; cmap={}
    for sec in sections:
        if sec.course not in cmap:
            cmap[sec.course] = colors[len(cmap)%len(colors)]
        c = cmap[sec.course]
        for d,s,e in sec.meetings:
            x = DAY_IDX.get(d)
            if x is None: continue
            y0 = s.hour+s.minute/60
            h = (e.hour+e.minute/60)-y0
            rect = patches.Rectangle((x+0.05,y0),0.9,h,facecolor=c,edgecolor='black',alpha=0.6)
            ax.add_patch(rect)
            ax.text(x+0.5,y0+h/2,f"{sec.cid}\n{sec.course}",ha='center',va='center',fontsize=7)
    st.pyplot(fig)

if __name__=='__main__':
    main()

