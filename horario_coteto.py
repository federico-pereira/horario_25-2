# streamlit_schedule_similarity.py

import streamlit as st
import pandas as pd
import re
import math
from datetime import datetime, time
from itertools import product
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as patches

st.set_page_config(layout="wide")
st.title("Generador de Horarios - UAI")

# -------------------
# Helpers & Parsers
# -------------------
DAY_FULL = {
    "Lunes":"Lu","Martes":"Ma","Miércoles":"Mi","Miercoles":"Mi",
    "Jueves":"Ju","Viernes":"Vi","Sábado":"Sa","Sabado":"Sa","Domingo":"Do"
}
pattern_sched = (
    r"(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[áa]bado|Domingo)"
    r"\s+(\d{1,2}:\d{2})\s+a\s+(\d{1,2}:\d{2})"
)

class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid = cid
        self.course = course
        self.meetings = meetings
        self.teacher = teacher
    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
                          for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

def parse_schedule_field(field):
    meetings = []
    for day_full, t0, t1 in re.findall(pattern_sched, field):
        d = DAY_FULL.get(day_full, day_full[:2])
        s = datetime.strptime(t0, "%H:%M").time()
        e = datetime.strptime(t1, "%H:%M").time()
        meetings.append((d, s, e))
    return meetings

@st.cache_data
def build_sections(df):
    by_sec = defaultdict(list)
    for _, r in df.iterrows():
        by_sec[r['SSEC']].append(r)
    secs = []
    for sec_id, rows in by_sec.items():
        meetings = []
        for r in rows:
            meetings += parse_schedule_field(r['Cátedra'])
        meetings = list(dict.fromkeys(meetings))
        secs.append(Section(sec_id, rows[0]['Asignatura'], meetings, rows[0]['Profesor']))
    return secs

# -------------------
# Core Scheduling
# -------------------
def overlaps(a, b):
    for d1, s1, e1 in a.meetings:
        for d2, s2, e2 in b.meetings:
            if d1 == d2 and s1 < e2 and s2 < e1:
                return True
    return False

def compute_window(combo):
    max_gap = 0
    by_day = defaultdict(list)
    for sec in combo:
        for d, s, e in sec.meetings:
            by_day[d].append((s, e))
    for meetings in by_day.values():
        meetings.sort(key=lambda x: x[0])
        for i in range(len(meetings)-1):
            gap = (meetings[i+1][0].hour*60 + meetings[i+1][0].minute) - \
                  (meetings[i][1].hour*60 + meetings[i][1].minute)
            max_gap = max(max_gap, gap)
    return max_gap

def compute_schedules(courses, ranking, min_days_free, banned, start_pref, end_pref, weights):
    # Generate all combos
    combos = list(product(*courses.values()))
    sims = []
    # Compute all metrics
    raw = []
    for combo in combos:
        if any(overlaps(a, b) for a in combo for b in combo if a!=b):
            continue
        days_occ = {d for sec in combo for d,_,_ in sec.meetings}
        free_days = 5 - len(days_occ)
        veto_cnt = sum(sec.teacher in banned for sec in combo)
        vio_pref = sum(1 for sec in combo for _, s, e in sec.meetings if s < start_pref or e > end_pref)
        gap = compute_window(combo)
        avg_rank = sum(ranking.get(sec.teacher, len(ranking)) for sec in combo)/len(combo)
        raw.append((combo, avg_rank, gap, free_days, veto_cnt, vio_pref))

    if not raw:
        return []

    # Find maxima for normalization
    mx_rank = max(r[1] for r in raw) or 1
    mx_gap  = max(r[2] for r in raw) or 1
    mx_free = max(r[3] for r in raw) or 1
    mx_veto = max(r[4] for r in raw) or 1
    mx_win  = max(r[5] for r in raw) or 1

    # Ideal vector = [rank(best), gap=0, free_days>=min_days, veto=0, vio_pref=0]
    # We'll set ideal normalized metrics: [1,1, free_days/min_desired clipped, 1,1]
    for combo, avg, gap, free, veto, vio in raw:
        n_rank = 1 - (avg/mx_rank)
        n_gap  = 1 - (gap/mx_gap)
        n_free = min(free/min_days_free, 1.0) if min_days_free>0 else 1.0
        n_veto = 1 - (veto/mx_veto)
        n_win  = 1 - (vio/mx_win)
        metrics = [n_rank, n_gap, n_free, n_veto, n_win]
        # Weighted Euclidean distance to ideal [1,1,1,1,1]
        diff_sq = 0
        for w, m in zip(weights.values(), metrics):
            diff_sq += w*((1-m)**2)
        max_diff_sq = sum(weights.values())*(1**2)
        dist = math.sqrt(diff_sq)
        sim  = 1 - dist/math.sqrt(max_diff_sq)
        sims.append((sim, combo))
    sims.sort(key=lambda x: x[0], reverse=True)
    return sims

# -------------------
# Visualization
# -------------------
def visualize_schedule(combo):
    DAY_MAP = {'Lu':0,'Ma':1,'Mi':2,'Ju':3,'Vi':4}
    labels  = ["Lunes","Martes","Mié","Jue","Vie"]
    fig, ax = plt.subplots(figsize=(10,6))
    ax.set_xticks([i+0.5 for i in range(5)])
    ax.set_xticklabels(labels)
    ax.set_ylim(20,8); ax.set_xlim(0,5)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    cmap, colors = {}, plt.cm.tab20.colors
    for sec in combo:
        if sec.course not in cmap:
            cmap[sec.course] = colors[len(cmap)%len(colors)]
        c = cmap[sec.course]
        for d,s,e in sec.meetings:
            x = DAY_MAP.get(d)
            if x is None: continue
            y0 = s.hour + s.minute/60
            h  = (e.hour + e.minute/60) - y0
            rect = patches.Rectangle((x+0.05,y0),0.9,h,facecolor=c,edgecolor='black',alpha=0.6)
            ax.add_patch(rect)
            ax.text(x+0.5, y0+h/2, f"{sec.cid}\n{sec.course}", ha='center', va='center', fontsize=7)
    st.pyplot(fig)

# -------------------
# Streamlit UI
# -------------------
def main():
    CSV_URL = "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv"
    st.sidebar.header("Carga de CSV")
    source = st.sidebar.radio("Origen CSV", ["GitHub", "Local", "Subir"])
    if source == "GitHub":
        try:
            df = pd.read_csv(CSV_URL)
            st.sidebar.success("✅ CSV cargado desde GitHub")
        except Exception as e:
            st.sidebar.error(f"No se pudo cargar remoto: {e}")
            source = "Local"
    if source == "Local":
        local_files = [f for f in os.listdir('.') if f.lower().endswith('.csv')]
        csv_choice = st.sidebar.selectbox("Selecciona un CSV local", local_files)
        df = pd.read_csv(csv_choice)
    if source == "Subir":
        uploaded = st.sidebar.file_uploader("Sube tu CSV", type="csv")
        if not uploaded:
            st.stop()
        df = pd.read_csv(uploaded)
        
    secs = build_sections(df)
    courses = defaultdict(list)
    for sec in secs:
        courses[sec.course].append(sec)

    sel = st.sidebar.multiselect("Asignaturas", sorted(courses), default=None)
    sub = {c:courses[c] for c in sel}

    teachers = sorted({sec.teacher for secs in sub.values() for sec in secs})
    rank_sel = st.sidebar.multiselect("Preferencia Docentes", teachers, default=None)
    ranking = {t:i for i,t in enumerate(rank_sel)}

    min_days_free = st.sidebar.slider("Días libres mínimo", 0, 5, 0)
    banned = st.sidebar.multiselect("Docentes vetados", teachers)
    start_pref = st.sidebar.time_input("Inicia después de", time(8,30))
    end_pref   = st.sidebar.time_input("Termina antes de", time(18,0))

    st.sidebar.header("Pesos de criterio")
    weights = {
        'rank':   st.sidebar.slider("Importancia Profesores favoritos", 1.0,5.0,3.0),
        'win':    st.sidebar.slider("Importancia Tamaño de ventana",     1.0,5.0,3.0),
        'off':    st.sidebar.slider("Importancia Dias libres",1.0,5.0,3.0),
        'veto':   st.sidebar.slider("Importancia Profesores vetados",    1.0,5.0,3.0),
        'window': st.sidebar.slider("Importancia Rango de horario", 1.0,5.0,3.0)
    }

    if st.sidebar.button("Generar"):
        sims = compute_schedules(sub, ranking, min_days_free, banned, start_pref, end_pref, weights)
        if not sims:
            st.warning("No hay soluciones.")
        else:
            st.header("Top 5 Horarios por Similitud")
            for sim, combo in sims[:5]:
                st.subheader(f"Similitud: {sim:.3f}")
                for sec in combo:
                    st.write(sec)
                st.markdown("---")
            st.header("Horario más afín")
            visualize_schedule(sims[0][1])

if __name__ == "__main__":
    main()
