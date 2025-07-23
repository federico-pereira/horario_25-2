# streamlit_horario_prioridad_completo_slider_hardlock.py

import streamlit as st
import pandas as pd
import re
from datetime import datetime, time
from itertools import product
from collections import defaultdict
import matplotlib.pyplot as plt
import matplotlib.patches as patches

st.set_page_config(layout="wide")
st.title("Generador de Horarios - UAI")

# Helpers
DAY_FULL = {
    "Lunes": "Lu", "Martes": "Ma", "Miércoles": "Mi", "Miercoles": "Mi",
    "Jueves": "Ju", "Viernes": "Vi", "Sábado": "Sa", "Sabado": "Sa", "Domingo": "Do"
}

def parse_schedule_field(field):
    pattern = r'(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes|S[áa]bado|Domingo)\s+(\d{1,2}:\d{2})\s+a\s+(\d{1,2}:\d{2})'
    matches = re.findall(pattern, field)
    meetings = []
    for day_full, t0, t1 in matches:
        day   = DAY_FULL.get(day_full, day_full[:2])
        start = datetime.strptime(t0, '%H:%M').time()
        end   = datetime.strptime(t1, '%H:%M').time()
        meetings.append((day, start, end))
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

@st.cache_data
def build_courses(df):
    by_sec = defaultdict(list)
    for _, r in df.iterrows():
        by_sec[r['SSEC']].append(r)
    courses = defaultdict(list)
    for sec_id, rows in by_sec.items():
        meetings = []
        for r in rows:
            meetings += parse_schedule_field(r['Cátedra'])
        meetings = list(dict.fromkeys(meetings))
        course  = rows[0]['Asignatura']
        teacher = rows[0]['Profesor']
        courses[course].append(Section(sec_id, course, meetings, teacher))
    return courses

def overlaps(a, b):
    for d1,s1,e1 in a.meetings:
        for d2,s2,e2 in b.meetings:
            if d1==d2 and s1<e2 and s2<e1:
                return True
    return False

def compute_window(combo):
    max_gap = 0
    by_day  = defaultdict(list)
    for sec in combo:
        for d, st, en in sec.meetings:
            by_day[d].append((st, en))
    for meetings in by_day.values():
        meetings.sort(key=lambda x: x[0])
        for i in range(len(meetings)-1):
            gap = (meetings[i+1][0].hour*60+meetings[i+1][0].minute) - (meetings[i][1].hour*60+meetings[i][1].minute)
            max_gap = max(max_gap, gap)
    return max_gap

def filter_slot_combo(combo, slot):
    m0, m1 = time(8,30), time(14,30)
    a0 = time(14,31)
    for sec in combo:
        for _, s, e in sec.meetings:
            if slot=='Mañana' and not (m0<=s<=m1 and m0<=e<=m1): return False
            if slot=='Tarde'  and not (s>=a0): return False
    return True

def compute_schedules(courses, ranking, min_days_free, banned, slot, weights):
    hard_slot = weights['slot'] == 5
    hard_veto = weights['veto'] == 5

    all_combos = list(product(*courses.values()))
    metrics = []
    for combo in all_combos:
        if any(overlaps(a,b) for a in combo for b in combo if a!=b):
            continue

        avg_rank = sum(ranking.get(sec.teacher, len(ranking)) for sec in combo)/len(combo)
        win      = compute_window(combo)
        occupied = {d for sec in combo for d,_,_ in sec.meetings}
        days_free = 5 - len(occupied)
        if days_free < min_days_free:
            continue

        veto_cnt = sum(sec.teacher in banned for sec in combo)
        if hard_veto and veto_cnt > 0:
            continue

        slot_vio = 0
        for sec in combo:
            for _, s, e in sec.meetings:
                if slot=='Mañana' and not (time(8,30)<=s<=time(14,30) and time(8,30)<=e<=time(14,30)):
                    slot_vio += 1
                if slot=='Tarde' and not (s>=time(14,31)):
                    slot_vio += 1
        if hard_slot and slot_vio > 0:
            continue

        metrics.append((combo, avg_rank, win, days_free, veto_cnt, slot_vio))

    max_vals = {
        'rank': max((m[1] for m in metrics), default=1),
        'win':  max((m[2] for m in metrics), default=1),
        'off':  max((m[3] for m in metrics), default=1),
        'veto': max((m[4] for m in metrics), default=1),
        'slot': max((m[5] for m in metrics), default=1)
    }

    scored = []
    total_w = sum(weights.values())
    for combo, avg, win, off, veto, slot_v in metrics:
        n_rank = 1 - (avg / max_vals['rank'])
        n_win  = 1 - (win / max_vals['win'])
        n_off  = off / max_vals['off']
        n_veto = 1 - (veto / max_vals['veto'])
        n_slot = 1 - (slot_v / max_vals['slot'])
        score = (weights['rank']*n_rank + weights['win']*n_win +
                 weights['off']*n_off   + weights['veto']*n_veto +
                 weights['slot']*n_slot) / total_w
        scored.append((score, combo))

    scored.sort(key=lambda x:x[0], reverse=True)
    return scored

def visualize_schedule(combo):
    DAY_MAP = {'Lu':0,'Ma':1,'Mi':2,'Ju':3,'Vi':4}
    labels  = ["Lunes","Martes","Mié","Jue","Vie"]
    fig, ax = plt.subplots(figsize=(10,6))
    ax.set_xticks([i+0.5 for i in range(5)])
    ax.set_xticklabels(labels)
    ax.set_xlim(0,5); ax.set_ylim(20,8); ax.set_yticks(range(8,21))
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    colors, cmap = plt.cm.tab20.colors, {}
    for sec in combo:
        if sec.course not in cmap:
            cmap[sec.course] = colors[len(cmap)%len(colors)]
        c = cmap[sec.course]
        for d, s, e in sec.meetings:
            x = DAY_MAP.get(d)
            if x is None: continue
            y0 = s.hour + s.minute/60
            h  = (e.hour + e.minute/60) - y0
            ax.add_patch(patches.Rectangle((x+0.05,y0),0.9,h,facecolor=c,edgecolor='black',alpha=0.6))
            ax.text(x+0.5,y0+h/2,f"{sec.cid}\n{sec.course}",ha='center',va='center',fontsize=7)
    st.pyplot(fig)

def main():
    # 1) Remote-first CSV load
    CSV_URL = "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv"
    try:
        df = pd.read_csv(CSV_URL)
        st.success("✅ Cargado CSV desde GitHub")
    except Exception as e:
        st.warning(f"No pude cargar el CSV remoto: {e}")
        uploaded = st.file_uploader("Sube tu CSV", type="csv")
        if not uploaded:
            st.stop()
        df = pd.read_csv(uploaded)

    # 2) Build courses
    courses = build_courses(df)

    # Sidebar UI
    st.sidebar.header("Asignaturas")
    names = sorted(courses.keys())
    selected = st.sidebar.multiselect("Asignaturas", names, default=names)
    sub = {c: courses[c] for c in selected}

    st.sidebar.header("Ranking Docentes")
    teachers = sorted({sec.teacher for secs in sub.values() for sec in secs})
    ranking = st.sidebar.multiselect("Orden (mejor primero)", teachers, default=teachers)
    ranking_map = {t: i for i, t in enumerate(ranking)}

    st.sidebar.header("Cantidad de Días Libres")
    min_free = st.sidebar.slider("Días libres (0–5)", 0, 5, 0)

    st.sidebar.header("Docentes Vetados")
    banned = st.sidebar.multiselect("Veto", teachers)

    st.sidebar.header("Franja Horaria")
    slot = st.sidebar.selectbox("Franja", ["Ambos", "Mañana", "Tarde"])

    st.sidebar.header("Pesos")
    weights = {
        'rank': st.sidebar.slider("Ranking", 1.0, 5.0, 3.0),
        'win' : st.sidebar.slider("Ventana", 1.0, 5.0, 3.0),
        'off' : st.sidebar.slider("Días libres", 1.0, 5.0, 3.0),
        'veto': st.sidebar.slider("Vetado", 1.0, 5.0, 3.0),
        'slot': st.sidebar.slider("Franja", 1.0, 5.0, 3.0)
    }

    # 3) Generate on button
    if st.sidebar.button("Generar Horarios"):
        scored = compute_schedules(sub, ranking_map, min_free, banned, slot, weights)
        if not scored:
            st.warning("No hay soluciones válidas.")
        else:
            st.header("Top 5 Horarios")
            for score, combo in scored[:5]:
                st.subheader(f"Score: {score:.3f}")
                for sec in combo:
                    st.write(sec)
                st.markdown("---")
            st.header("Mejor Horario")
            visualize_schedule(scored[0][1])

if __name__ == "__main__":
    main()
