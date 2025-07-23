# streamlit_schedule_app_fixed.py

import streamlit as st
import pandas as pd  # Aseguramos importar pandas
import unicodedata
from datetime import datetime, time
from itertools import product
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Helper functions
def strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')

def parse_time_slot(ts):
    day, rest = ts.split(" ", 1)
    t0, _, t1 = rest.partition(" - ")
    start = datetime.strptime(t0, "%H:%M:%S").time()
    end = datetime.strptime(t1, "%H:%M:%S").time()
    return day, start, end

def normalize_day(d):
    return {"lu":"Lu","ma":"Ma","mi":"Mi","ju":"Ju","vi":"Vi"}.get(d.strip().lower()[:2], None)

class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid = cid
        self.course = course
        self.meetings = meetings
        self.teacher = teacher

    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

def build_sections(df):
    by_sec = defaultdict(list)
    for _, r in df.iterrows():
        by_sec[r['Sección']].append(r)
    courses = defaultdict(list)
    for sec_id, rows in by_sec.items():
        meetings = [parse_time_slot(r['Horario']) for r in rows]
        course = rows[0]['Asignatura']
        teacher = rows[0]['Docente']
        courses[course].append(Section(sec_id, course, meetings, teacher))
    return courses

def overlaps(a, b):
    for d1,s1,e1 in a.meetings:
        for d2,s2,e2 in b.meetings:
            if d1==d2 and s1<e2 and s2<e1:
                return True
    return False

def filter_slots(secs, slot):
    m0,m1=time(8,30),time(14,30)
    a0=time(14,31)
    out=[]
    for sec in secs:
        ok=True
        for _,st,en in sec.meetings:
            if slot=='Mañana' and not (m0<=st<=m1 and m0<=en<=m1): ok=False
            if slot=='Tarde' and not (st>=a0): ok=False
        if slot=='Ambos': ok=True
        if ok: out.append(sec)
    return out

def compute_window(combo):
    max_gap=0
    by_day=defaultdict(list)
    for sec in combo:
        for d,st,en in sec.meetings:
            by_day[d].append((st,en))
    for meetings in by_day.values():
        meetings.sort(key=lambda x:x[0])
        for i in range(len(meetings)-1):
            gap=(meetings[i+1][0].hour*60+meetings[i+1][0].minute)-(meetings[i][1].hour*60+meetings[i][1].minute)
            max_gap=max(max_gap,gap)
    return max_gap

# Corrección en compute_schedules para usar la clave 'off' en lugar de 'free'

def compute_schedules(courses, ranking, slot, min_days_free, weights, banned):
    hard_slot = weights['slot'] > 3
    filtered = {}
    for c, secs in courses.items():
        filtered[c] = filter_slots(secs, slot) if hard_slot else secs

    combos = list(product(*filtered.values()))
    scored = []
    for combo in combos:
        if any(overlaps(a, b) for a in combo for b in combo if a != b):
            continue
        avg_rank = sum(ranking.get(sec.teacher, len(ranking)) for sec in combo) / len(combo)
        win      = compute_window(combo)
        occupied = {d for sec in combo for d, _, _ in sec.meetings}
        days_free = 5 - len(occupied)
        if days_free < min_days_free:
            continue
        ban_vio  = sum(sec.teacher in banned for sec in combo)
        slot_vio = 0
        if not hard_slot:
            slot_vio = sum(
                1 for sec in combo for _, s, e in sec.meetings
                if (slot == 'Mañana' and not (time(8,30) <= s <= time(14,30) and time(8,30) <= e <= time(14,30)))
                   or (slot == 'Tarde' and not (s >= time(14,31)))
            )

        # Normalizamos máximos, asegurando no cero
        max_vals = {
            'rank': max(avg_rank, 1),
            'win' : max(win, 1),
            'off' : max(days_free, 1),
            'ban' : max(ban_vio, 1),
            'slot': max(slot_vio, 1)
        }

        # Ahora usamos la clave 'off' para días libres
        n = {
            'rank': 1 - (avg_rank / max_vals['rank']),
            'win' : 1 - (win / max_vals['win']),
            'off' : days_free / max_vals['off'],
            'ban' : 1 - (ban_vio / max_vals['ban']),
            'slot': 1 - (slot_vio / max_vals['slot'])
        }

        total_w = sum(weights.values())
        score = sum(weights[k] * n[k] for k in weights) / total_w
        scored.append((score, combo))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored

# Sustituye tu función compute_schedules actual con esta para resolver el KeyError.


def visualize(combo):
    DAY_MAP={"Lu":0,"Ma":1,"Mi":2,"Ju":3,"Vi":4}
    DAY_L=["Lunes","Martes","Mié","Jue","Vie"]
    fig, ax = plt.subplots(figsize=(10,6))
    ax.set_xticks([i+0.5 for i in range(5)])
    ax.set_xticklabels(DAY_L)
    ax.set_xlim(0,5); ax.set_ylim(20,8); ax.set_yticks(range(8,21))
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    colors=plt.cm.tab20.colors; cmap={}
    for sec in combo:
        if sec.course not in cmap: cmap[sec.course]=colors[len(cmap)%len(colors)]
        c=cmap[sec.course]
        for d,s,e in sec.meetings:
            x=DAY_MAP.get(d)
            if x is None: continue
            y0=s.hour+s.minute/60; h=(e.hour+e.minute/60)-y0
            ax.add_patch(patches.Rectangle((x+0.05,y0),0.9,h,facecolor=c,edgecolor='black',alpha=0.6))
            ax.text(x+0.5,y0+h/2,f"{sec.cid}\n{sec.course}",ha='center',va='center',fontsize=7)
    st.pyplot(fig)

# Streamlit UI
st.title("Generador de Horarios Interactivo")

uploaded = st.file_uploader("Sube tu CSV", type="csv")
if uploaded:
    df = pd.read_csv(uploaded)
    # filtros
    carrera = st.selectbox("Carrera", sorted(df["Carrera"].unique()))
    df = df[df["Carrera"]==carrera]
    plan    = st.selectbox("Plan", sorted(df["Plan"].unique()))
    df = df[df["Plan"]==plan]
    jornada = st.selectbox("Jornada", sorted(df["Jornada"].unique()))
    df = df[df["Jornada"]==jornada]
    nivel   = st.selectbox("Nivel", [v for v in sorted(df["Nivel"].unique()) if v.isdigit()])
    df = df[(df["Nivel"]==nivel)|(df["Nivel"].str.lower()=="optativos")]

    courses = build_sections(df)
    cursos  = st.multiselect("Cursos a incluir", sorted(courses.keys()))
    if cursos:
        # Lista de docentes como str
        all_teach = sorted({str(sec.teacher) for c in cursos for sec in courses[c]})
        ranking   = st.multiselect("Ranking docentes (mover en orden)", all_teach, default=all_teach)
        ranking_map = {t:i for i,t in enumerate(ranking)}
        banned    = st.multiselect("Docentes vetados", all_teach)
        slot      = st.selectbox("Franja", ["Mañana","Tarde","Ambos"])
        min_free  = st.slider("Cantidad de días libres", 0, 5, 0)
        weights   = {
            'rank': st.slider("Peso ranking", 1, 5, 3),
            'win' : st.slider("Peso ventana", 1, 5, 3),
            'off' : st.slider("Peso días libres", 1, 5, 3),
            'ban' : st.slider("Peso vetado", 1, 5, 3),
            'slot': st.slider("Peso franja", 1, 5, 3)
        }
        if st.button("Generar horarios"):
            sub    = {c:courses[c] for c in cursos}
            scored = compute_schedules(sub, ranking_map, slot, min_free, weights, banned)
            if not scored:
                st.warning("No se encontraron horarios válidos.")
            else:
                for sc, combo in scored[:5]:
                    st.write(f"**Score:** {sc:.2f}")
                    for sec in combo:
                        st.write(sec)
                    st.markdown("---")
                st.write("### Mejor horario")
                visualize(scored[0][1])

