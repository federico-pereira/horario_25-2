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
    return ''.join(c for c in unicodedata.normalize('NFD', s)
                   if unicodedata.category(c) != 'Mn')

MEETING_RE = re.compile(
    r"(Lunes|Martes|Mi[eé]rcoles|Jueves|Viernes)\s*"
    r"(\d{1,2}:\d{2}:?\d{0,2})\s*[-aA]\s*(\d{1,2}:\d{2}:?\d{0,2})"
)

def parse_meetings(raw: str):
    meetings = []
    for dia, t0, t1 in MEETING_RE.findall(raw):
        fmt = "%H:%M:%S" if t0.count(':') == 2 else "%H:%M"
        h0 = datetime.strptime(t0, fmt).time()
        h1 = datetime.strptime(t1, fmt).time()
        meetings.append((dia, h0, h1))
    return meetings

# ----- Data Structures -----
class Section:
    def __init__(self, cid, course, meetings, teacher):
        self.cid = cid
        self.course = course
        self.meetings = meetings
        self.teacher = teacher
    def __str__(self):
        times = "; ".join(f"{d} {s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for d, s, e in self.meetings)
        return f"[{self.cid}] {self.course} — {times} — {self.teacher}"

# ----- Scheduling Logic -----
def build_courses(df):
    by_sec = defaultdict(list)
    for _, r in df.iterrows():
        by_sec[r['Sección']].append(r)
    courses = defaultdict(list)
    for sec_id, rows in by_sec.items():
        meetings = []
        for r in rows:
            meetings.extend(parse_meetings(r['Cátedra']))
        course = rows[0]['Asignatura']
        teacher = rows[0]['Profesor']
        courses[course].append(Section(sec_id, course, meetings, teacher))
    return courses

def overlaps(a: Section, b: Section) -> bool:
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
        for i in range(len(meetings) - 1):
            end_prev = meetings[i][1]
            start_next = meetings[i+1][0]
            gap = (start_next.hour*60 + start_next.minute) - (end_prev.hour*60 + end_prev.minute)
            max_gap = max(max_gap, gap)
    return max_gap

def filter_slots(secs, slot):
    m0, m1 = time(8,30), time(14,30)
    a0 = time(14,31)
    out = []
    for sec in secs:
        ok = True
        for _, st, en in sec.meetings:
            if slot == 'Mañana' and not (m0 <= st <= m1 and m0 <= en <= m1): ok = False
            if slot == 'Tarde' and not (st >= a0): ok = False
        if slot == 'Ambos': ok = True
        if ok:
            out.append(sec)
    return out

def compute_schedules(courses, ranking, slot, min_days_free, weights, banned):
    # time bounds
    m0, m1 = time(8,30), time(14,30)
    a0 = time(14,31)
    hard = weights['slot'] > 3
    filtered = {c: (filter_slots(secs, slot) if hard else secs) for c, secs in courses.items()}
    combos = list(product(*filtered.values()))
    metrics = []
    for combo in combos:
        if any(overlaps(a, b) for a in combo for b in combo if a != b):
            continue
        avg_rank = sum(ranking.get(sec.teacher, len(ranking)) for sec in combo) / len(combo)
        win = compute_window(combo)
        occ_days = {d for sec in combo for d, _, _ in sec.meetings}
        free_days = 5 - len(occ_days)
        if free_days < min_days_free:
            continue
        ban_v = sum(1 for sec in combo if sec.teacher in banned)
        slot_v = 0
        if not hard:
            for sec in combo:
                for _, st, en in sec.meetings:
                    if slot == 'Mañana' and not (m0 <= st <= m1 and m0 <= en <= m1): slot_v += 1
                    if slot == 'Tarde' and not (st >= a0): slot_v += 1
        metrics.append((combo, avg_rank, win, free_days, ban_v, slot_v))
    if not metrics:
        return []
    # normalization maxima
    max_vals = {
        'rank': max(m[1] for m in metrics),
        'win': max(m[2] for m in metrics),
        'free': max(m[3] for m in metrics),
        'ban': max(m[4] for m in metrics),
        'slot': max(m[5] for m in metrics),
    }
    for k in max_vals:
        max_vals[k] = max_vals[k] or 1
    scored = []
    total_w = sum(weights.values())
    for combo, avg_rank, win, free_days, ban_v, slot_v in metrics:
        n_rank = 1 - (avg_rank / max_vals['rank'])
        n_win = 1 - (win / max_vals['win'])
        n_free = free_days / max_vals['free']
        n_ban = 1 - (ban_v / max_vals['ban'])
        n_slot = 1 - (slot_v / max_vals['slot'])
        score = (
            weights['rank'] * n_rank +
            weights['win'] * n_win +
            weights['off'] * n_free +
            weights['ban'] * n_ban +
            weights['slot'] * n_slot
        ) / total_w
        scored.append((score, combo))
    return sorted(scored, key=lambda x: x[0], reverse=True)

# ----- Streamlit App -----
def main():
    st.title("Generador de Horarios con Prioridades")
    # CSV input
    csv_url = st.sidebar.text_input(
        "URL raw GitHub:",
        "https://raw.githubusercontent.com/federico-pereira/horario_25-2/main/horario.csv"
    )
    df = pd.read_csv(csv_url)
    st.sidebar.write("Columnas:", df.columns.tolist())
    # rename for processing
    df = df.rename(columns={
        'SSEC': 'Sección',
        'Asignatura': 'Asignatura',
        'Profesor': 'Profesor',
        'Cátedra': 'Cátedra'
    })
    # build course sections
    courses = build_courses(df)
    # user selections
    sel_courses = st.sidebar.multiselect(
        "Asignaturas:", sorted(courses.keys()), sorted(courses.keys())
    )
    selected = {c: courses[c] for c in sel_courses}
    teachers = sorted({sec.teacher for secs in selected.values() for sec in secs})
    banned = st.sidebar.multiselect("Vetar profesores:", teachers)
    rank_sel = st.sidebar.multiselect("Ranking (mejor a peor):", teachers, teachers)
    ranking = {t: i for i, t in enumerate(rank_sel)}
    slot = st.sidebar.selectbox("Franja:", ['Ambos', 'Mañana', 'Tarde'])
    min_free = st.sidebar.slider("Días libres mínimos:", 0, 5, 1)
    weights = {
        'rank': st.sidebar.slider('Peso ranking', 1, 5, 3),
        'win':  st.sidebar.slider('Peso ventana', 1, 5, 3),
        'off':  st.sidebar.slider('Peso días libres', 1, 5, 3),
        'ban':  st.sidebar.slider('Peso vetos', 1, 5, 3),
        'slot': st.sidebar.slider('Peso franja', 1, 5, 3),
    }
    # compute and display
    scored = compute_schedules(selected, ranking, slot, min_free, weights, set(banned))
    if not scored:
        st.warning("No soluciones válidas.")
        return
    st.subheader("Top 3 soluciones")
    for i, (sc, combo) in enumerate(scored[:3], 1):
        st.markdown(f"**Solución {i} (score: {sc:.2f})**")
        for sec in combo:
            st.write(str(sec))
    st.subheader("Horario óptimo")
    visualize_streamlit(scored[0][1])

# ----- Visualization -----
def visualize_streamlit(sections):
    DAY_ORDER = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes']
    idx = {d: i for i, d in enumerate(DAY_ORDER)}
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.set_xticks([i+0.5 for i in range(len(DAY_ORDER))])
    ax.set_xticklabels(DAY_ORDER)
    ax.set_ylim(20, 8)
    ax.set_xlim(0, len(DAY_ORDER))
    ax.set_ylabel('Hora')
    ax.grid(True, 'both', '--', 0.5)
    colors = plt.cm.tab20.colors
    cmap = {}
    for sec in sections:
        if sec.course not in cmap:
            cmap[sec.course] = colors[len(cmap) % len(colors)]
        c = cmap[sec.course]
        for d, s, e in sec.meetings:
            x = idx.get(d)
            if x is None: continue
            y0 = s.hour + s.minute/60
            h = (e.hour + e.minute/60) - y0
            rect = patches.Rectangle((x+0.05, y0), 0.9, h,
                                     facecolor=c, edgecolor='black', alpha=0.6)
            ax.add_patch(rect)
            ax.text(x+0.5, y0 + h/2,
                    f"{sec.cid}\n{sec.course}", ha='center', va='center', fontsize=7)
    st.pyplot(fig)

if __name__ == '__main__':
    main()

