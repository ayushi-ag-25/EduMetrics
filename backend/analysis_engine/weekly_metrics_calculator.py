# ============================================================
#  analysis_engine/weekly/weekly_metrics_calculator.py  (Django ORM version)
#
#  Computes effort_score + academic_performance per student per week
#  and writes them to weekly_metrics in the analysis DB.
#
#  All mysql.connector calls replaced with Django ORM.
#  Client DB  → ClientXxx models  (routed to 'client_db')
#  Analysis DB → WeeklyMetrics model (routed to 'default')
# ============================================================

import numpy as np
import warnings

warnings.filterwarnings('ignore')

# ── Client DB models ──────────────────────────────────────────
from analysis_engine.client_models import (
    ClientSimState,
    ClientClass,
    ClientStudent,
    ClientAttendance,
    ClientAssignmentDefinition,
    ClientAssignmentSubmission,
    ClientQuizDefinition,
    ClientQuizSubmission,
    ClientLibraryVisit,
    ClientBookBorrow,
    ClientExamResult,
    ClientExamSchedule,
)

# ── Analysis DB models ────────────────────────────────────────
from analysis_engine.models import WeeklyMetrics


# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════

MIDTERM_WEEK  = 8
ENDTERM_WEEK  = 18
EXAM_WEEKS    = {MIDTERM_WEEK, ENDTERM_WEEK}
EFFORT_WINDOW = 3

W_LIB_VISITS    = 25
W_BOOK_BORROWS  = 20
W_ASSN_QUALITY  = 20
W_ASSN_PLAG     = 15
W_ATT_RATE      = 10
W_QUIZ_SUB_RATE =  5
W_ASSN_SUB_RATE =  5

WEIGHT_M = 0.40
WEIGHT_N = 0.30
WEIGHT_P = 0.30


# ══════════════════════════════════════════════════════════════
# 1. CONTEXT
# ══════════════════════════════════════════════════════════════

def _get_sim_context():
    state = ClientSimState.objects.using('client_db').get(id=1)
    gw    = state.current_week

    if gw <= 18:
        sem_week, slot = gw, 'odd'
    else:
        sem_week, slot = gw - 18, 'even'

    classes = list(ClientClass.objects.using('client_db').all())
    sem_map = {
        cls.class_id: (cls.odd_sem if slot == 'odd' else cls.even_sem)
        for cls in classes
    }

    effort_window_weeks = []
    w = sem_week
    while w >= 1 and len(effort_window_weeks) < EFFORT_WINDOW:
        if w not in EXAM_WEEKS:
            effort_window_weeks.append(w)
        w -= 1

    return {
        'global_week':         gw,
        'sem_week':            sem_week,
        'slot':                slot,
        'sem_map':             sem_map,
        'effort_window_weeks': effort_window_weeks,
    }


# ══════════════════════════════════════════════════════════════
# 2. CLIENT DB FETCHERS (ORM replacing raw SQL)
# ══════════════════════════════════════════════════════════════

def _fetch_students(sem_map):
    class_ids = list(sem_map.keys())
    qs = ClientStudent.objects.using('client_db').filter(class_id__in=class_ids)
    return list(qs.values('student_id', 'name', 'class_id'))


def _fetch_attendance_window(sem_map, weeks):
    if not weeks:
        return []
    class_ids = list(sem_map.keys())
    qs = ClientAttendance.objects.using('client_db').filter(
        class_id__in=class_ids,
        week__in=weeks,
    )
    return [
        {
            'student_id':    r['student_id'],
            'sem_week':      r['week'],
            'present':       r['present'],
            'lectures_held': r['lectures_held'],
        }
        for r in qs.values('student_id', 'week', 'present', 'lectures_held')
    ]


def _fetch_quiz_submissions_semester(sem_map):
    """All quiz submissions for the current semester (cumulative)."""
    class_ids = list(sem_map.keys())
    semesters = list(set(sem_map.values()))

    # Get quiz definitions for this semester
    defn_qs = ClientQuizDefinition.objects.using('client_db').filter(
        class_id__in=class_ids,
    ).values('quiz_id', 'scheduled_week')
    # NOTE: add semester filter if your quiz_definitions table has a semester column:
    #   .filter(semester__in=semesters)
    defn_map = {d['quiz_id']: d['scheduled_week'] for d in defn_qs}

    if not defn_map:
        return []

    sub_qs = ClientQuizSubmission.objects.using('client_db').filter(
        quiz_id__in=list(defn_map.keys()),
    ).values('student_id', 'class_id', 'quiz_id', 'score_pct', 'attempted')

    return [
        {
            'student_id': r['student_id'],
            'class_id':   r['class_id'],
            'score_pct':  r['score_pct'],
            'attempted':  r['attempted'],
            'sem_week':   defn_map[r['quiz_id']],
        }
        for r in sub_qs
    ]


def _fetch_assignment_submissions_semester(sem_map):
    """All assignment submissions for the current semester (cumulative)."""
    class_ids = list(sem_map.keys())

    defn_qs = ClientAssignmentDefinition.objects.using('client_db').filter(
        class_id__in=class_ids,
    ).values('assignment_id', 'due_week', 'max_marks')
    # NOTE: add semester filter if your assignment_definitions has a semester column
    defn_map = {d['assignment_id']: d for d in defn_qs}

    if not defn_map:
        return []

    sub_qs = ClientAssignmentSubmission.objects.using('client_db').filter(
        assignment_id__in=list(defn_map.keys()),
    ).values('student_id', 'class_id', 'assignment_id', 'marks_obtained', 'quality_pct', 'plagiarism_pct')

    return [
        {
            'student_id':    r['student_id'],
            'class_id':      r['class_id'],
            'marks_obtained': r['marks_obtained'],
            'quality_pct':   r['quality_pct'],
            'plagiarism_pct': r['plagiarism_pct'],
            'max_marks':     defn_map[r['assignment_id']]['max_marks'],
            'sem_week':      defn_map[r['assignment_id']]['due_week'],
        }
        for r in sub_qs
    ]


def _fetch_library_window(sem_map, weeks):
    if not weeks:
        return []
    class_ids = list(sem_map.keys())
    qs = ClientLibraryVisit.objects.using('client_db').filter(
        class_id__in=class_ids,
        week__in=weeks,
    )
    return [
        {
            'student_id':      r['student_id'],
            'sem_week':        r['week'],
            'physical_visits': r['physical_visits'],
        }
        for r in qs.values('student_id', 'week', 'physical_visits')
    ]


def _fetch_book_borrows_window(sem_map, weeks):
    if not weeks:
        return []
    class_ids = list(sem_map.keys())
    qs = ClientBookBorrow.objects.using('client_db').filter(
        class_id__in=class_ids,
        borrow_week__in=weeks,
    )
    return [
        {'student_id': r['student_id'], 'sem_week': r['borrow_week']}
        for r in qs.values('student_id', 'borrow_week')
    ]


def _fetch_midterm_results(sem_map):
    class_ids = list(sem_map.keys())
    sched_qs = ClientExamSchedule.objects.using('client_db').filter(
        class_id__in=class_ids,
        exam_type='midterm',
    ).values('schedule_id')
    sched_ids = [s['schedule_id'] for s in sched_qs]

    if not sched_ids:
        return []

    qs = ClientExamResult.objects.using('client_db').filter(
        schedule_id__in=sched_ids,
    )
    return list(qs.values('student_id', 'score_pct'))


def _fetch_prior_endterm_results(sem_map):
    """Endterm results from the immediately preceding semester."""
    semesters    = list(set(sem_map.values()))
    prior_sems   = [s - 1 for s in semesters if s > 1]
    if not prior_sems:
        return []

    class_ids = list(sem_map.keys())
    # Get endterm schedules for prior semesters
    # NOTE: this requires semester field on exam_schedule
    sched_qs = ClientExamSchedule.objects.using('client_db').filter(
        class_id__in=class_ids,
        exam_type='endterm',
        # semester__in=prior_sems,   # uncomment if your schema has semester column
    ).values('schedule_id')
    sched_ids = [s['schedule_id'] for s in sched_qs]

    if not sched_ids:
        return []

    qs = ClientExamResult.objects.using('client_db').filter(
        schedule_id__in=sched_ids,
    )
    return list(qs.values('student_id', 'score_pct'))


def _fetch_recent_academic_performance(sem_map, current_sem_week):
    """
    Read last 2 weeks of academic_performance from analysis DB (WeeklyMetrics).
    Returns { student_id → [(sem_week, ap_value), ...] } sorted desc.
    """
    semesters = list(set(sem_map.values()))
    lookback  = []
    w = current_sem_week - 1
    while w >= 1 and len(lookback) < 2:
        if w not in EXAM_WEEKS:
            lookback.append(w)
        w -= 1

    if not lookback:
        return {}

    qs = WeeklyMetrics.objects.filter(
        semester__in=semesters,
        sem_week__in=lookback,
        academic_performance__isnull=False,
    ).values('student_id', 'sem_week', 'academic_performance')

    result = {}
    for r in qs:
        sid = r['student_id']
        result.setdefault(sid, []).append((r['sem_week'], float(r['academic_performance'])))

    for sid in result:
        result[sid].sort(key=lambda x: x[0], reverse=True)

    return result


# ══════════════════════════════════════════════════════════════
# 3. HELPERS (unchanged from original)
# ══════════════════════════════════════════════════════════════

def _group_by_student(rows):
    out = {}
    for r in rows:
        out.setdefault(r['student_id'], []).append(r)
    return out


# ══════════════════════════════════════════════════════════════
# 4. ACADEMIC PERFORMANCE CALCULATOR (pure Python — unchanged)
# ══════════════════════════════════════════════════════════════

def _compute_academic_performance(
    sid, sem_week, quiz_rows, assn_rows, midterm_score, prior_endterm, recent_ap
):
    if sem_week == MIDTERM_WEEK:
        return None, None, None, None

    attempted_quizzes = [r for r in quiz_rows if r.get('attempted') and float(r.get('score_pct') or 0) >= 0]
    quiz_avg = (
        sum(float(r['score_pct'] or 0) for r in attempted_quizzes) / len(attempted_quizzes)
        if attempted_quizzes else None
    )

    submitted_assns = [r for r in assn_rows if float(r.get('marks_obtained') or 0) > 0]
    assn_avg = None
    if submitted_assns:
        scores = []
        for r in submitted_assns:
            mm = float(r.get('max_marks') or 0)
            mo = float(r.get('marks_obtained') or 0)
            if mm > 0:
                scores.append(mo / mm * 100)
        assn_avg = sum(scores) / len(scores) if scores else None

    has_quiz = quiz_avg is not None
    has_assn = assn_avg is not None

    if has_quiz and has_assn:
        if midterm_score is not None:
            ap = (WEIGHT_M * quiz_avg + WEIGHT_N * assn_avg + WEIGHT_P * midterm_score) / (WEIGHT_M + WEIGHT_N + WEIGHT_P)
        else:
            ap = (quiz_avg + assn_avg) / 2
        return round(ap, 2), round(quiz_avg, 2), round(assn_avg, 2), midterm_score

    if has_quiz:
        return round(quiz_avg, 2), round(quiz_avg, 2), None, midterm_score
    if has_assn:
        return round(assn_avg, 2), None, round(assn_avg, 2), midterm_score

    if prior_endterm is not None:
        return round(prior_endterm, 2), None, None, midterm_score

    if recent_ap:
        ap = (2 * recent_ap[0][1] + 1 * recent_ap[1][1]) / 3 if len(recent_ap) >= 2 else recent_ap[0][1]
        return round(ap, 2), None, None, midterm_score

    return None, None, None, None


# ══════════════════════════════════════════════════════════════
# 5. EFFORT SCORE CALCULATOR (pure Python — unchanged)
# ══════════════════════════════════════════════════════════════

def _compute_effort(
    sid, window_weeks, att_rows, quiz_rows_sem, assn_rows_window,
    lib_rows, borrow_rows, has_prior_semester, academic_performance
):
    if not has_prior_semester and academic_performance is None:
        return None, None, None, None, None, None, None, None

    window_set = set(window_weeks)
    n_weeks    = len(window_weeks) if window_weeks else 1

    att_present = sum(float(r['present'] or 0) for r in att_rows
                      if r['student_id'] == sid and r['sem_week'] in window_set)
    att_held    = sum(float(r['lectures_held'] or 0) for r in att_rows
                      if r['student_id'] == sid and r['sem_week'] in window_set)
    att_rate = (att_present / att_held) if att_held > 0 else 1.0

    quizzes_in_window = [r for r in quiz_rows_sem
                         if r['student_id'] == sid and r['sem_week'] in window_set]
    quiz_attempted    = sum(1 for r in quizzes_in_window if r.get('attempted'))
    quiz_submit_rate  = (quiz_attempted / len(quizzes_in_window)
                         if quizzes_in_window else 1.0)

    assns_in_window  = [r for r in assn_rows_window
                        if r['student_id'] == sid and r['sem_week'] in window_set]
    assn_submitted   = [r for r in assns_in_window
                        if float(r.get('marks_obtained') or 0) > 0]
    assn_submit_rate = (len(assn_submitted) / len(assns_in_window)
                        if assns_in_window else 1.0)

    qualities = [float(r.get('quality_pct') or 0) for r in assn_submitted
                 if r.get('quality_pct') is not None]
    assn_quality_avg = sum(qualities) / len(qualities) if qualities else 0.0

    plags = [float(r.get('plagiarism_pct') or 0) for r in assns_in_window]
    assn_plagiarism_max = max(plags) if plags else 0.0

    lib_visits_w   = sum(int(r.get('physical_visits') or 0) for r in lib_rows
                         if r['student_id'] == sid and r['sem_week'] in window_set)
    book_borrows_w = sum(1 for r in borrow_rows
                         if r['student_id'] == sid and r['sem_week'] in window_set)

    s_lib    = min(lib_visits_w   / (5 * n_weeks), 1.0) * 100
    s_borrow = min(book_borrows_w / (2 * n_weeks), 1.0) * 100
    s_qual   = assn_quality_avg
    s_plag   = max(0.0, 100.0 - assn_plagiarism_max)
    s_att    = att_rate   * 100
    s_qsub   = quiz_submit_rate  * 100
    s_asub   = assn_submit_rate  * 100

    effort = (
        W_LIB_VISITS    * s_lib    +
        W_BOOK_BORROWS  * s_borrow +
        W_ASSN_QUALITY  * s_qual   +
        W_ASSN_PLAG     * s_plag   +
        W_ATT_RATE      * s_att    +
        W_QUIZ_SUB_RATE * s_qsub   +
        W_ASSN_SUB_RATE * s_asub
    ) / 100.0

    return (
        round(effort, 2),
        lib_visits_w,
        book_borrows_w,
        round(assn_quality_avg, 2),
        round(assn_plagiarism_max, 2),
        round(att_rate, 4),
        round(quiz_submit_rate, 4),
        round(assn_submit_rate, 4),
    )


# ══════════════════════════════════════════════════════════════
# 6. MAIN FUNCTION
# ══════════════════════════════════════════════════════════════

def run():
    print("  [weekly_metrics] Starting...")

    ctx           = _get_sim_context()
    sem_week      = ctx['sem_week']
    sem_map       = ctx['sem_map']
    effort_window = ctx['effort_window_weeks']
    rep_semester  = next(iter(sem_map.values()))

    print(f"  sem_week={sem_week}  semester={rep_semester}  effort_window={effort_window}")

    # ── Fetch all data in bulk ─────────────────────────────────
    students       = _fetch_students(sem_map)
    att_rows       = _fetch_attendance_window(sem_map, effort_window)
    quiz_rows_sem  = _fetch_quiz_submissions_semester(sem_map)
    assn_rows_sem  = _fetch_assignment_submissions_semester(sem_map)
    lib_rows       = _fetch_library_window(sem_map, effort_window)
    borrow_rows    = _fetch_book_borrows_window(sem_map, effort_window)
    midterm_rows   = _fetch_midterm_results(sem_map)
    prior_end_rows = _fetch_prior_endterm_results(sem_map)
    recent_ap_map  = _fetch_recent_academic_performance(sem_map, sem_week)

    # ── Index by student ──────────────────────────────────────
    quiz_by_stu      = _group_by_student(quiz_rows_sem)
    assn_by_stu      = _group_by_student(assn_rows_sem)
    midterm_by_stu   = {r['student_id']: float(r['score_pct'] or 0) for r in midterm_rows}
    prior_end_by_stu = {r['student_id']: float(r['score_pct'] or 0) for r in prior_end_rows}
    students_with_prior = set(prior_end_by_stu.keys())

    # ── Compute metrics ────────────────────────────────────────
    to_create = []
    to_update = []
    existing  = {
        wm.student_id: wm
        for wm in WeeklyMetrics.objects.filter(
            semester=rep_semester, sem_week=sem_week,
            student_id__in=[s['student_id'] for s in students]
        )
    }

    for stu in students:
        sid = stu['student_id']
        cid = stu['class_id']

        ap, quiz_avg, assn_avg, midterm_pct = _compute_academic_performance(
            sid, sem_week,
            quiz_by_stu.get(sid, []),
            assn_by_stu.get(sid, []),
            midterm_by_stu.get(sid),
            prior_end_by_stu.get(sid),
            recent_ap_map.get(sid, []),
        )

        (effort, lib_v, book_b, assn_qual, assn_plag,
         att_r, quiz_sr, assn_sr) = _compute_effort(
            sid, effort_window, att_rows, quiz_rows_sem, assn_rows_sem,
            lib_rows, borrow_rows, sid in students_with_prior, ap,
        )

        fields = dict(
            class_id                = cid,
            effort_score            = effort,
            library_visits_w        = lib_v,
            book_borrows_w          = book_b,
            assn_quality_avg        = assn_qual,
            assn_plagiarism_max     = assn_plag,
            att_rate_recent         = att_r,
            quiz_submit_rate_recent = quiz_sr,
            assn_submit_rate_recent = assn_sr,
            academic_performance    = ap,
            quiz_avg_pct            = quiz_avg,
            assn_avg_pct            = assn_avg,
            midterm_score_pct       = midterm_pct,
            weight_m                = WEIGHT_M,
            weight_n                = WEIGHT_N,
            weight_p                = WEIGHT_P,
        )

        if sid in existing:
            obj = existing[sid]
            for k, v in fields.items():
                setattr(obj, k, v)
            to_update.append(obj)
        else:
            to_create.append(WeeklyMetrics(
                student_id=sid, semester=rep_semester, sem_week=sem_week,
                **fields
            ))

    if to_create:
        WeeklyMetrics.objects.bulk_create(to_create)
    if to_update:
        update_fields = list(fields.keys())
        WeeklyMetrics.objects.bulk_update(to_update, update_fields)

    computed = sum(
        1 for s in students
        if any([
            assn_by_stu.get(s['student_id']),
            quiz_by_stu.get(s['student_id']),
        ])
    )
    print(f"  [weekly_metrics] Done — {len(students)} students written, "
          f"{computed} with data  (sem {rep_semester}, week {sem_week})")


if __name__ == '__main__':
    import django, os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'your_project.settings')
    django.setup()
    run()
