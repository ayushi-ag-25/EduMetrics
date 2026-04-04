# ============================================================
#  analysis_engine/weekly/flagging.py  (Django ORM version)
#
#  All mysql.connector calls replaced with Django ORM.
#  Client DB  → ClientXxx models  (routed to 'client_db')
#  Analysis DB → WeeklyFlag, InterventionLog models (routed to 'default')
#
#  Run as a Django management command or call generate_weekly_triage()
#  directly from calibrate_analysis_db.
# ============================================================

import numpy as np
import warnings

warnings.filterwarnings('ignore')

# ── Client DB models (managed=False, route → client_db) ──────
from analysis_engine.client_models import (
    ClientSimState,
    ClientClass,
    ClientStudent,
    ClientAttendance,
    ClientAssignmentSubmission,
    ClientAssignmentDefinition,
    ClientExamResult,
    ClientExamSchedule,
)

# ── Analysis DB models (route → default) ─────────────────────
# Import your actual analysis models here.
# These must already exist in analysis_engine/models.py
from analysis_engine.models import WeeklyFlag, InterventionLog

# ── Django ORM helpers ────────────────────────────────────────
from django.db import transaction
from django.db.models import Avg, Max, Sum, F, Q


# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════

MIDTERM_WEEK = 8
ENDTERM_WEEK = 18
EXAM_WEEKS   = {MIDTERM_WEEK, ENDTERM_WEEK}


# ══════════════════════════════════════════════════════════════
# 1. CONTEXT — replaces _get_sim_context() + raw SQL
# ══════════════════════════════════════════════════════════════

def _get_sim_context():
    """
    Read sim_state and classes from client DB via Django ORM.
    Returns the same dict structure as the original.
    """
    state = ClientSimState.objects.using('client_db').get(id=1)
    global_week = state.current_week

    # Derive sem_week and slot
    if global_week <= 18:
        sem_week, slot = global_week, 'odd'
    else:
        sem_week, slot = global_week - 18, 'even'

    # Build sem_map {class_id → current semester}
    # NOTE: Your ClientClass model needs odd_sem / even_sem fields.
    # If your classes table uses a single 'semester' column instead,
    # replace cls.odd_sem/cls.even_sem with cls.semester below.
    classes = list(ClientClass.objects.using('client_db').all())
    sem_map = {
        cls.class_id: (cls.odd_sem if slot == 'odd' else cls.even_sem)
        for cls in classes
    }

    # Baseline window: up to 4 teaching weeks before current sem_week
    baseline_weeks = []
    w = sem_week - 1
    while w >= 1 and len(baseline_weeks) < 4:
        if w not in EXAM_WEEKS:
            baseline_weeks.append(w)
        w -= 1

    return {
        'global_week':     global_week,
        'sem_week':        sem_week,
        'slot':            slot,
        'sem_map':         sem_map,
        'classes':         classes,
        'baseline_weeks':  baseline_weeks,
        'is_grace_period': sem_week <= 3,
    }


# ══════════════════════════════════════════════════════════════
# 2. ESCALATION MEMORY — replaces _load_memory() / _save_memory()
# ══════════════════════════════════════════════════════════════

def _load_memory():
    """
    Read latest escalation state per student from v_current_escalation.
    We replicate the view logic in Python using InterventionLog.
    Returns { student_id → {'escalation_level': int, 'last_flagged_week': int} }
    """
    # Get the latest intervention_log row per student (equivalent to the view)
    from django.db.models import Max
    latest_per_student = (
        InterventionLog.objects
        .values('student_id')
        .annotate(latest=Max('logged_at'))
    )

    memory = {}
    for entry in latest_per_student:
        row = (
            InterventionLog.objects
            .filter(student_id=entry['student_id'], logged_at=entry['latest'])
            .first()
        )
        if row:
            memory[row.student_id] = {
                'escalation_level':  row.escalation_level,
                'last_flagged_week': row.sem_week,
            }
    return memory


def _save_memory(new_memory, sem_week, semester):
    """
    Write escalation changes to InterventionLog.
    new_memory: { student_id → {'escalation_level': int, 'diagnosis': str} }
    """
    if not new_memory:
        return

    logs = [
        InterventionLog(
            student_id       = sid,
            semester         = semester,
            sem_week         = sem_week,
            escalation_level = data['escalation_level'],
            trigger_diagnosis= data.get('diagnosis', ''),
        )
        for sid, data in new_memory.items()
    ]
    InterventionLog.objects.bulk_create(logs)


# ══════════════════════════════════════════════════════════════
# 3. ARCHETYPE ASSIGNMENT — no SQL, pure Python (unchanged)
# ══════════════════════════════════════════════════════════════

def _assign_archetype(sid, att_rows, current_sem_week):
    """
    att_rows: list of dicts with keys student_id, sem_week, present, lectures_held.
    att_rows here are plain Python dicts built from ORM querysets below.
    """
    window_start = current_sem_week - 6
    stu_rows = [
        r for r in att_rows
        if r['student_id'] == sid
        and r['sem_week'] > window_start
        and r['sem_week'] <= current_sem_week
        and r['sem_week'] not in EXAM_WEEKS
    ]
    if not stu_rows:
        return 'Insufficient Data'

    week_scores = {}
    for r in stu_rows:
        w  = r['sem_week']
        p  = float(r['present'] or 0)
        lh = float(r['lectures_held'] or 0)
        if w not in week_scores:
            week_scores[w] = [0.0, 0.0]
        week_scores[w][0] += p
        week_scores[w][1] += lh

    weekly = sorted([
        (w, (vals[0] / vals[1] * 100) if vals[1] > 0 else 100.0)
        for w, vals in week_scores.items()
    ])

    if len(weekly) < 3:
        return 'Insufficient Data (< 3 weeks)'

    x = np.array([pt[0] for pt in weekly], dtype=float)
    y = np.array([pt[1] for pt in weekly], dtype=float)

    slope, _   = np.polyfit(x, y, 1)
    volatility    = np.std(y)
    current_score = y[-1]

    if volatility > 25.0:                          return 'Crammer (High Volatility)'
    elif slope < -15.0 and current_score < 40:     return 'Silent Disengager (Steep Drop)'
    elif -15.0 <= slope < -5.0:                    return 'Slow Fader (Gradual Decline)'
    elif current_score > 85 and volatility < 10.0: return 'High Performer (Stable)'
    else:                                          return 'Consistent Average'


# ══════════════════════════════════════════════════════════════
# 4. DATA FETCHERS — raw SQL → Django ORM querysets
#    Each returns a list of plain dicts for easy processing.
# ══════════════════════════════════════════════════════════════

def _fetch_students(sem_map):
    """All students across all active classes."""
    class_ids = list(sem_map.keys())
    qs = ClientStudent.objects.using('client_db').filter(class_id__in=class_ids)
    return list(qs.values('student_id', 'name', 'class_id'))


def _fetch_attendance(sem_map, current_sem_week, baseline_weeks):
    """Attendance for current + baseline + archetype window weeks."""
    all_weeks = set(
        [current_sem_week] + baseline_weeks +
        list(range(max(1, current_sem_week - 6), current_sem_week + 1))
    )
    all_weeks = [w for w in all_weeks if w not in EXAM_WEEKS]
    class_ids = list(sem_map.keys())

    qs = ClientAttendance.objects.using('client_db').filter(
        class_id__in=class_ids,
        week__in=all_weeks,
    )
    return [
        {
            'student_id':    r['student_id'],
            'class_id':      r['class_id'],
            'sem_week':      r['week'],          # 'week' in DB = sem_week
            'present':       r['present'],
            'lectures_held': r['lectures_held'],
        }
        for r in qs.values('student_id', 'class_id', 'week', 'present', 'lectures_held')
    ]


def _fetch_assignments(sem_map, current_sem_week, baseline_weeks):
    """
    Assignment submissions for current and baseline weeks.
    Joined with assignment_definitions via Python (no cross-DB join needed —
    both tables are on the same client_db).
    """
    all_weeks = list(set([current_sem_week] + baseline_weeks))
    class_ids = list(sem_map.keys())

    # Get definitions whose due_week is in the window
    defn_qs = ClientAssignmentDefinition.objects.using('client_db').filter(
        class_id__in=class_ids,
        due_week__in=all_weeks,
    ).values('assignment_id', 'due_week')
    defn_map = {d['assignment_id']: d['due_week'] for d in defn_qs}

    if not defn_map:
        return []

    sub_qs = ClientAssignmentSubmission.objects.using('client_db').filter(
        assignment_id__in=list(defn_map.keys()),
    ).values('student_id', 'class_id', 'assignment_id', 'marks_obtained', 'plagiarism_pct')

    return [
        {
            'student_id':    r['student_id'],
            'class_id':      r['class_id'],
            'marks_obtained': r['marks_obtained'],
            'plagiarism_pct': r['plagiarism_pct'],
            'sem_week':       defn_map[r['assignment_id']],
        }
        for r in sub_qs
    ]


def _fetch_exams(sem_map, current_sem_week):
    """Exam results for any exam whose scheduled_week <= current_sem_week."""
    class_ids = list(sem_map.keys())

    # Get schedules up to current week
    sched_qs = ClientExamSchedule.objects.using('client_db').filter(
        class_id__in=class_ids,
        scheduled_week__lte=current_sem_week,
    ).values('schedule_id', 'scheduled_week')
    sched_map = {s['schedule_id']: s['scheduled_week'] for s in sched_qs}

    if not sched_map:
        return []

    result_qs = ClientExamResult.objects.using('client_db').filter(
        schedule_id__in=list(sched_map.keys()),
    ).values('student_id', 'class_id', 'score_pct', 'schedule_id')

    return [
        {
            'student_id': r['student_id'],
            'class_id':   r['class_id'],
            'score_pct':  r['score_pct'],
            'sem_week':   sched_map[r['schedule_id']],
        }
        for r in result_qs
    ]


# ══════════════════════════════════════════════════════════════
# 5. MAIN TRIAGE FUNCTION
#    Core logic is UNCHANGED — only the DB calls above changed.
# ══════════════════════════════════════════════════════════════

def generate_weekly_triage(capacity_limit=15):
    print("Initializing Weekly Rule-Based Triage Engine...")

    ctx            = _get_sim_context()
    sem_week       = ctx['sem_week']
    sem_map        = ctx['sem_map']
    baseline_weeks = ctx['baseline_weeks']
    is_grace       = ctx['is_grace_period']

    rep_semester = next(iter(sem_map.values()))

    print(f"  sem_week={sem_week}  semester={rep_semester}  "
          f"baseline={baseline_weeks}  grace={is_grace}")

    # ── Fetch raw data from client DB ─────────────────────────
    students  = _fetch_students(sem_map)
    att_rows  = _fetch_attendance(sem_map, sem_week, baseline_weeks)
    assn_rows = _fetch_assignments(sem_map, sem_week, baseline_weeks)
    exam_rows = _fetch_exams(sem_map, sem_week)

    # ── Load escalation memory ────────────────────────────────
    memory = _load_memory()

    # ── Pre-aggregate attendance ──────────────────────────────
    def _att_rate(rows, weeks):
        agg = {}
        for r in rows:
            if r['sem_week'] not in weeks:
                continue
            sid = r['student_id']
            if sid not in agg:
                agg[sid] = [0.0, 0.0]
            agg[sid][0] += float(r['present'] or 0)
            agg[sid][1] += float(r['lectures_held'] or 0)
        return {
            sid: (vals[0] / vals[1]) if vals[1] > 0 else 1.0
            for sid, vals in agg.items()
        }

    now_att  = _att_rate(att_rows, {sem_week})
    hist_att = _att_rate(att_rows, set(baseline_weeks)) if baseline_weeks else {}

    # ── Pre-aggregate assignments ─────────────────────────────
    def _assn_stats(rows, weeks):
        agg = {}
        for r in rows:
            if r['sem_week'] not in weeks:
                continue
            sid = r['student_id']
            if sid not in agg:
                agg[sid] = [0, 0, 0.0]
            agg[sid][1] += 1
            if float(r['marks_obtained'] or 0) > 0:
                agg[sid][0] += 1
            plag = float(r['plagiarism_pct'] or 0)
            if plag > agg[sid][2]:
                agg[sid][2] = plag
        return {
            sid: {
                'rate':     vals[0] / vals[1] if vals[1] > 0 else 1.0,
                'max_plag': vals[2],
            }
            for sid, vals in agg.items()
        }

    now_assn  = _assn_stats(assn_rows, {sem_week})
    hist_assn = _assn_stats(assn_rows, set(baseline_weeks)) if baseline_weeks else {}

    # ── Pre-aggregate exams ───────────────────────────────────
    current_exam_rows = [r for r in exam_rows if r['sem_week'] == sem_week]
    class_exam_avg    = (
        sum(float(r['score_pct']) for r in current_exam_rows) / len(current_exam_rows)
        if current_exam_rows else None
    )
    per_student_exam = {}
    for r in current_exam_rows:
        sid = r['student_id']
        per_student_exam.setdefault(sid, []).append(float(r['score_pct'] or 0))
    per_student_exam = {
        sid: sum(scores) / len(scores)
        for sid, scores in per_student_exam.items()
    }

    # ── Triage loop ───────────────────────────────────────────
    interventions = []
    new_memory    = {}

    for stu in students:
        sid  = stu['student_id']
        name = stu['name']
        cid  = stu['class_id']

        score     = 0
        diagnoses = []

        hist = memory.get(sid, {'escalation_level': 0, 'last_flagged_week': None})
        escalation_level  = hist['escalation_level']
        last_flagged_week = hist['last_flagged_week']

        # Plagiarism
        plag = now_assn.get(sid, {}).get('max_plag', 0)
        if plag > 50:
            score += 80
            diagnoses.append('Integrity Violation')

        # Severe absenteeism
        att_now = now_att.get(sid, 1.0)
        if att_now <= 0.30:
            score += 80
            diagnoses.append('Severe Absenteeism')

        # Exam failure
        if class_exam_avg is not None and sid in per_student_exam:
            avg_exam = per_student_exam[sid]
            if avg_exam < 50:
                if avg_exam < (class_exam_avg - 15.0):
                    score += 60
                    diagnoses.append(f'EXAM FAILURE ({avg_exam:.1f}%)')
                else:
                    score += 20
                    diagnoses.append('Hard Test Drop')

        # Attendance fader
        att_hist = hist_att.get(sid, 1.0)
        if (att_hist - att_now) > 0.20:
            score += 40
            diagnoses.append('Attendance Fader')

        # Stopped submitting
        assn_now_rate  = now_assn.get(sid,  {}).get('rate', 1.0)
        assn_hist_rate = hist_assn.get(sid, {}).get('rate', 1.0)
        if not is_grace and assn_now_rate == 0 and assn_hist_rate > 0:
            score += 40
            diagnoses.append('Stopped Submitting')

        # Compound + escalation boost
        if score > 0:
            severity_multiplier   = 1.0 + ((len(diagnoses) - 1) * 0.5)
            compounded_score      = score * severity_multiplier
            already_this_week     = (last_flagged_week == sem_week)
            if not already_this_week and escalation_level > 0:
                final_urgency = compounded_score + (escalation_level * 15)
            else:
                final_urgency = compounded_score

            if   final_urgency >= 200: risk_tier = 'Tier 1 (Critical Multi-Factor)'
            elif final_urgency >= 80:  risk_tier = 'Tier 2 (High Risk)'
            else:                      risk_tier = 'Tier 3 (Warning)'

            archetype = _assign_archetype(sid, att_rows, sem_week)

            interventions.append({
                'student_id':       sid,
                'name':             name,
                'class_id':         cid,
                'risk_tier':        risk_tier,
                'urgency_score':    int(final_urgency),
                'escalation_level': escalation_level,
                'archetype':        archetype,
                'diagnosis':        ' | '.join(diagnoses),
            })

            new_escl = escalation_level if already_this_week else escalation_level + 1
            new_memory[sid] = {
                'escalation_level': new_escl,
                'diagnosis':        ' | '.join(diagnoses),
            }
        else:
            if sid in memory:
                new_memory[sid] = {'escalation_level': 0, 'diagnosis': 'cleared'}

    # ── Rank and cap per class ────────────────────────────────
    by_class = {}
    for row in interventions:
        by_class.setdefault(row['class_id'], []).append(row)

    top_interventions = []
    for cid, rows in by_class.items():
        rows.sort(key=lambda x: x['urgency_score'], reverse=True)
        top_interventions.extend(rows[:capacity_limit])

    # ── Write weekly_flags to analysis DB ────────────────────
    if top_interventions:
        flag_objs = [
            WeeklyFlag(
                student_id      = row['student_id'],
                class_id        = row['class_id'],
                semester        = rep_semester,
                sem_week        = sem_week,
                risk_tier       = row['risk_tier'],
                urgency_score   = row['urgency_score'],
                escalation_level= row['escalation_level'],
                archetype       = row['archetype'],
                diagnosis       = row['diagnosis'],
            )
            for row in top_interventions
        ]
        WeeklyFlag.objects.bulk_create(flag_objs)

        breakdown = ', '.join(
            f"{cid}: {min(len(rows), capacity_limit)}"
            for cid, rows in sorted(by_class.items())
        )
        print(f"  SUCCESS — {len(top_interventions)} student(s) flagged "
              f"→ weekly_flags  (sem {rep_semester}, week {sem_week})")
        print(f"  Per-class breakdown — {breakdown}")
    else:
        print("  Great news: Zero interventions required this week.")

    # ── Persist escalation memory ─────────────────────────────
    _save_memory(new_memory, sem_week, rep_semester)
    print(f"  Escalation memory updated — {len(new_memory)} student(s) logged "
          f"→ intervention_log")


# ── Standalone entry point ────────────────────────────────────
if __name__ == '__main__':
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
    django.setup()
    generate_weekly_triage()
