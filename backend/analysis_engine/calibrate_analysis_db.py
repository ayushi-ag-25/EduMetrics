# this file replaces calibrate_analysis_db.py in the non-django version

# working=>
# receives trigger from simulator => compares client db state vs analysis db state => if client db is behind we roll back the analysis db , if if client db is ahead we run our 'analysis scripts' 


# ============================================================
#  analysis_engine/calibrate_analysis_db.py
#
#  Synchronises the analysis DB with the client DB.
#  Called by the Django view trigger_calibrate() in views.py.
#
#  All mysql.connector / Flask code replaced with Django ORM.
#  DB routing is handled by EduMetricsRouter (routers.py):
#    — ClientSimState, ClientClass, etc.  → 'client_db'   (read-only)
#    — analysis_state, weekly_metrics, …  → 'default'     (read-write)
# ============================================================

import importlib
import time
import traceback
from datetime import datetime

from django.db import transaction

# ── Client DB models (read-only) ─────────────────────────────
from .client_models import (
    ClientSimState,
    ClientClass,
)

# ── Analysis DB models (read-write) ──────────────────────────
from .models import (
    analysis_state,
    weekly_metrics,
    weekly_flags,
    pre_sem_watchlist,
    intervention_log,
    subject_difficulty,
    event_log,
)


# ══════════════════════════════════════════════════════════════
# 1. CONSTANTS
# ══════════════════════════════════════════════════════════════

WEEKS_PER_SEM               = 18
TOTAL_WEEKS                 = 36
MIDTERM_WEEK                = 8
ENDTERM_WEEK                = 18
EXAM_WEEKS                  = {MIDTERM_WEEK, ENDTERM_WEEK}
FLAG_START_WEEK             = 4
MONTHLY_EVERY_N_TEACH_WEEKS = 4
RISK_MIN_WEEK               = 6
PRE_MID_WEEKS               = {6, 7}
RISK_OF_FAILING_WEEK        = 10
PRE_END_WEEK                = 17
PRE_SEM_WEEK                = 18


# ══════════════════════════════════════════════════════════════
# 2. WEEK / SEMESTER HELPERS
# ══════════════════════════════════════════════════════════════

def _global_to_sem_week(global_week):
    """Return (sem_week, slot) where slot is 'odd' or 'even'."""
    if global_week <= WEEKS_PER_SEM:
        return global_week, "odd"
    return global_week - WEEKS_PER_SEM, "even"

def _is_exam_week(sem_week):
    return sem_week in EXAM_WEEKS


# ══════════════════════════════════════════════════════════════
# 3. STATE READERS / WRITERS  (ORM replaces raw SQL)
# ══════════════════════════════════════════════════════════════

def _get_client_state():
    """
    Read sim_state and classes from the client DB.
    Returns a dict with global_week, sem_week, slot, sem_map, classes.

    NOTE: ClientClass must have odd_sem / even_sem columns — uncomment
    those fields in client_models.py if they are currently commented out.
    """
    state = ClientSimState.objects.using('client_db').get(id=1)
    gw    = state.current_week
    sw, slot = _global_to_sem_week(max(gw, 1)) if gw > 0 else (0, "odd")

    classes = list(
        ClientClass.objects.using('client_db').values('class_id', 'odd_sem', 'even_sem')
    )
    sem_map = {
        c['class_id']: c['odd_sem'] if slot == 'odd' else c['even_sem']
        for c in classes
    }

    return {
        'global_week': gw,
        'sem_week':    sw,
        'slot':        slot,
        'sem_map':     sem_map,
        'classes':     classes,
    }


def _get_analysis_state():
    """
    Read the analysis_state singleton from the analysis DB.
    Returns a dict with global_week, sem_week, semester.
    """
    try:
        state = analysis_state.objects.get(id=1)
        return {
            'global_week': state.current_global_week,
            'sem_week':    state.current_sem_week,
            'semester':    state.current_semester,
        }
    except analysis_state.DoesNotExist:
        return {'global_week': 0, 'sem_week': 0, 'semester': 1}


def _set_analysis_state(global_week, sem_week, semester):
    """Upsert the analysis_state singleton."""
    analysis_state.objects.update_or_create(
        id=1,
        defaults={
            'current_global_week': global_week,
            'current_sem_week':    sem_week,
            'current_semester':    semester,
        }
    )


# ══════════════════════════════════════════════════════════════
# 4. EVENT LOG
# ══════════════════════════════════════════════════════════════

def _log_event(event_type, client_week, analysis_sem_week, semester,
               status='ok', error_msg=None, duration_ms=None):
    event_log.objects.create(
        event_type    = event_type,
        client_week   = client_week,
        analysis_week = analysis_sem_week,
        semester      = semester,
        status        = status,
        error_message = error_msg,
        duration_ms   = duration_ms,
    )


# ══════════════════════════════════════════════════════════════
# 5. SCRIPT REGISTRY
#    event_name → (dotted_module_path, function_name) or None
#
#    To add a new script: add one line here. Nothing else changes.
# ══════════════════════════════════════════════════════════════

SCRIPT_REGISTRY = {
    # Weekly (run every teaching week)
    'weekly_metrics':    ('weekly_metrics_calculator', 'run'),
    'weekly_flags':      ('flagging',                  'generate_weekly_triage'),
    'risk_of_detention': ('risk_of_detention',         'run_detention_risk'),
    'risk_of_failing':   ('risk_of_failing',           'run_failing_risk'),

    # Event-based (run once at a specific week)
    'pre_mid_sem':  ('pre_mid_term',  'run'),
    'post_mid_sem': None,   # not yet written
    'pre_end_sem':  ('pre_end_term',  'run'),
    'post_end_sem': None,   # not yet written
    'pre_sem':      ('pre_sem',       'run'),
}


def _run_script(event_name, client_week, sem_week, semester):
    """
    Import and call the function registered under event_name.
    Logs the outcome to event_log. Never raises — all errors are caught.
    Returns True on success, False on skip/error.
    """
    entry = SCRIPT_REGISTRY.get(event_name)

    if entry is None:
        print(f'    [SKIP] {event_name} — not yet implemented')
        _log_event(event_name, client_week, sem_week, semester, status='skip')
        return False

    module_path, func_name = entry
    t0 = time.monotonic()
    try:
        mod  = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        func()
        ms = int((time.monotonic() - t0) * 1000)
        print(f'    [OK]   {event_name}  ({ms} ms)')
        _log_event(event_name, client_week, sem_week, semester, duration_ms=ms)
        return True
    except ModuleNotFoundError:
        ms = int((time.monotonic() - t0) * 1000)
        print(f'    [SKIP] {event_name} — module not found ({module_path})')
        _log_event(event_name, client_week, sem_week, semester, status='skip',
                   error_msg=f'ModuleNotFoundError: {module_path}', duration_ms=ms)
        return False
    except Exception as e:
        ms = int((time.monotonic() - t0) * 1000)
        print(f'    [ERR]  {event_name} — {e}')
        print(traceback.format_exc())
        _log_event(event_name, client_week, sem_week, semester, status='error',
                   error_msg=str(e)[:2000], duration_ms=ms)
        return False


# ══════════════════════════════════════════════════════════════
# 6. SCHEDULE: WHICH SCRIPTS RUN AT WHICH SEM_WEEK
# ══════════════════════════════════════════════════════════════

def _scripts_for_week(sem_week, global_week):
    """
    Return an ordered list of event_names to execute for this week.

    Execution order (dependencies flow top-to-bottom):
      1. weekly_metrics        — raw E_t / A_t signals
      2. weekly_flags          — triage built on top of weekly_metrics (week 4+)
      3. risk_of_detention     — detention risk (every teaching week)
      4. risk_of_failing       — fail-risk prediction (week 10+)
      5. pre_mid_sem           — predicted midterm score (weeks 6 & 7)
      6. pre_end_sem           — predicted endterm score (week 17)
      7. pre_sem               — next-semester watchlist (week 18)

    Exam weeks (8 and 18): no class data generated, nothing runs.
    """
    # Exam weeks: nothing to run
    if _is_exam_week(sem_week):
        return []

    scripts = []

    # 1. Core weekly signals — always first
    scripts.append('weekly_metrics')

    # 2. Flagging — after grace period
    if sem_week >= FLAG_START_WEEK:
        scripts.append('weekly_flags')

    # 3. Detention risk — every teaching week
    scripts.append('risk_of_detention')

    # 4. Fail-risk prediction — week 10 onwards
    if sem_week >= RISK_OF_FAILING_WEEK:
        scripts.append('risk_of_failing')

    # 5. Predicted midterm score — weeks 6 and 7
    if sem_week in PRE_MID_WEEKS:
        scripts.append('pre_mid_sem')

    # 6. Predicted endterm score — week 17 only
    if sem_week == PRE_END_WEEK:
        scripts.append('pre_end_sem')

    # 7. Pre-semester watchlist — week 18
    if sem_week == PRE_SEM_WEEK:
        scripts.append('pre_sem')

    return scripts


# ══════════════════════════════════════════════════════════════
# 7. ROLLBACK: CLEAN THE ANALYSIS DB
# ══════════════════════════════════════════════════════════════

def _rollback_analysis_db(target_global_week):
    """
    Delete all derived rows computed beyond target_global_week, then
    reset analysis_state. Uses a single atomic transaction so the DB
    is never left in a half-cleaned state.
    """
    print(f'\n  [ROLLBACK] Cleaning analysis DB → global week {target_global_week}')

    if target_global_week == 0:
        target_sem_week = 0
        target_semester = 1
    else:
        target_sem_week, slot = _global_to_sem_week(target_global_week)
        first_class = ClientClass.objects.using('client_db').values('odd_sem', 'even_sem').first()
        target_semester = (
            first_class['odd_sem'] if slot == 'odd' else first_class['even_sem']
        ) if first_class else 1

    with transaction.atomic():
        if target_global_week == 0:
            # Full wipe of all derived data
            for model, label in [
                (weekly_metrics,   'weekly_metrics'),
                (weekly_flags,     'weekly_flags'),
                (pre_sem_watchlist,'pre_sem_watchlist'),
                (intervention_log, 'intervention_log'),
                (subject_difficulty,'subject_difficulty'),
                (event_log,        'event_log'),
            ]:
                count, _ = model.objects.all().delete()
                print(f'    Cleared {label} ({count} rows)')

        else:
            # Trim rows beyond (target_semester, target_sem_week)
            for model, label in [
                (weekly_metrics,  'weekly_metrics'),
                (weekly_flags,    'weekly_flags'),
                (intervention_log,'intervention_log'),
            ]:
                count, _ = model.objects.filter(
                    semester__gt=target_semester
                ).delete()
                count2, _ = model.objects.filter(
                    semester=target_semester,
                    sem_week__gt=target_sem_week
                ).delete()
                print(f'    Trimmed {label} ({count + count2} rows removed)')

            # pre_sem_watchlist is keyed by target_semester, not sem_week
            count, _ = pre_sem_watchlist.objects.filter(
                target_semester__gt=target_semester
            ).delete()
            print(f'    Trimmed pre_sem_watchlist ({count} rows removed)')

            # event_log: trim future entries but keep past audit trail
            count, _ = event_log.objects.filter(
                semester__gt=target_semester
            ).delete()
            count2, _ = event_log.objects.filter(
                semester=target_semester,
                analysis_week__gt=target_sem_week
            ).delete()
            print(f'    Trimmed event_log ({count + count2} rows removed)')

        # Reset the analysis_state singleton inside the same transaction
        _set_analysis_state(target_global_week, target_sem_week, target_semester)
        print(f'    analysis_state reset → global week {target_global_week}')


# ══════════════════════════════════════════════════════════════
# 8. ADVANCE: FILL THE GAP WEEK BY WEEK
# ══════════════════════════════════════════════════════════════

def _advance_analysis_db(from_global_week, to_global_week, classes):
    """
    Walk from (from_global_week + 1) to to_global_week inclusive.
    For each week: determine sem context → look up scripts → run in order →
    update analysis_state.

    analysis_state is persisted after every single week so that if a script
    crashes mid-jump, the next calibrate() call resumes from where it left off.
    """
    for gw in range(from_global_week + 1, to_global_week + 1):
        sw, slot = _global_to_sem_week(gw)

        # All classes in the same cohort move together — use first class as
        # the representative for the semester value.
        rep_semester = classes[0]['odd_sem'] if slot == 'odd' else classes[0]['even_sem']

        exam_tag = '[EXAM]' if _is_exam_week(sw) else ''
        print(f'\n  G-W{gw:02d}  sem-week {sw:02d}  sem {rep_semester}  {exam_tag}')

        scripts = _scripts_for_week(sw, gw)
        if not scripts:
            print('    Nothing scheduled this week.')
        else:
            for event_name in scripts:
                _run_script(event_name, gw, sw, rep_semester)

        # Persist progress after every week — safe for partial advances
        _set_analysis_state(gw, sw, rep_semester)


# ══════════════════════════════════════════════════════════════
# 9. PUBLIC ENTRY POINT
# ══════════════════════════════════════════════════════════════

def calibrate():
    """
    Synchronise the analysis DB with the client DB.

    Called by trigger_calibrate() in views.py, which is in turn hit by
    the simulator (app.py / Streamlit) after every advance_week() or
    rollback_to_week(). Blocks until all scripts have committed, then
    returns a summary dict that views.py serialises as JSON.
    """
    t_start = time.monotonic()
    print(f"\n{'='*60}")
    print(f"  calibrate_analysis_db  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    client   = _get_client_state()
    analysis = _get_analysis_state()

    client_gw   = client['global_week']
    analysis_gw = analysis['global_week']

    print(f'  Client DB   → global week {client_gw}')
    print(f'  Analysis DB → global week {analysis_gw}')

    result = {
        'client_week':     client_gw,
        'analysis_week':   analysis_gw,
        'action':          None,
        'weeks_processed': 0,
        'elapsed_ms':      0,
    }

    if client_gw == analysis_gw:
        print('  Already in sync. Nothing to do.')
        result['action'] = 'no_op'

    elif client_gw < analysis_gw:
        result['action'] = 'rollback'
        _rollback_analysis_db(client_gw)

    else:
        result['action']          = 'advance'
        result['weeks_processed'] = client_gw - analysis_gw
        print(f"  Gap: {result['weeks_processed']} week(s) to process")
        _advance_analysis_db(analysis_gw, client_gw, client['classes'])

    elapsed = int((time.monotonic() - t_start) * 1000)
    result['elapsed_ms'] = elapsed
    print(f'\n  Done — {elapsed} ms')
    print(f"{'='*60}\n")
    return result