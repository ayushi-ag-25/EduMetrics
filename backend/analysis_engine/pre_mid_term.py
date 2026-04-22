# ============================================================
#  analysis_engine/pre_mid_term.py  (Django ORM version)
#
#  Runs at sem_week == 6 AND sem_week == 7 (pre-midterm weeks).
#  Predicts midterm score using Ridge regression (pure NumPy).
#  Writes prediction into the dedicated `pre_mid_term` table
#  (NOT weekly_metrics.risk_of_failing — that was the old approach).
#
#  Trigger weeks: 6 (first pass) and 7 (final pass before exam).
#  One row per student per run → student gets 2 rows/semester.
#
#  All mysql.connector calls replaced with Django ORM.
# ============================================================

import os
import json
import warnings
import numpy as np

warnings.filterwarnings('ignore')

# ── Client DB models ──────────────────────────────────────────
from analysis_engine.client_models import (
    ClientSimState,
    ClientClass,
    ClientStudent,
)

# ── Analysis DB models ────────────────────────────────────────
from analysis_engine.models import weekly_metrics, PreMidTerm


# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

_HERE              = os.path.dirname(os.path.abspath(__file__))
MODEL_WEIGHTS_PATH = os.path.join(_HERE,'models', 'midterm_model_weights.json')

# Weeks at which this script fires (pre-midterm prediction windows)
PRE_MID_WEEKS = {6, 7}
MIDTERM_WEEK  = 8

# Weeks used as input features (the teaching weeks before the exam)
SUM_WEEKS_FALLBACK = [2, 3, 4, 5, 6, 7]


# ══════════════════════════════════════════════════════════════
# 1. CONTEXT
# ══════════════════════════════════════════════════════════════

def _get_sim_context():
    state    = ClientSimState.objects.using('client_db').get(id=1)
    gw       = state.current_week
    sem_week, slot = (gw, 'odd') if gw <= 18 else (gw - 18, 'even')

    classes  = list(ClientClass.objects.using('client_db').all())
    sem_map  = {
        c.class_id: (c.odd_sem if slot == 'odd' else c.even_sem)
        for c in classes
    }
    return {
        'global_week': gw,
        'sem_week':    sem_week,
        'slot':        slot,
        'sem_map':     sem_map,
    }


# ══════════════════════════════════════════════════════════════
# 2. FETCH STUDENTS
# ══════════════════════════════════════════════════════════════

def _fetch_students(sem_map):
    class_ids = list(sem_map.keys())
    qs = ClientStudent.objects.using('client_db').filter(class_id__in=class_ids)
    return list(qs.values('student_id', 'class_id'))


# ══════════════════════════════════════════════════════════════
# 3. FETCH WEEKLY METRICS from analysis DB
#    Uses weeks available UP TO (but not including) current week
# ══════════════════════════════════════════════════════════════

def _fetch_weekly_metrics(sem_map, sum_weeks):
    """
    Returns { student_id: { week: {'ap': float|None, 'effort': float|None} } }
    """
    semesters = list(set(sem_map.values()))

    qs = weekly_metrics.objects.filter(
        semester__in=semesters,
        sem_week__in=sum_weeks,
    ).values('student_id', 'sem_week', 'academic_performance', 'effort_score')

    result = {}
    for r in qs:
        sid = r['student_id']
        w   = r['sem_week']
        result.setdefault(sid, {})[w] = {
            'ap':     float(r['academic_performance']) if r['academic_performance'] is not None else None,
            'effort': float(r['effort_score'])         if r['effort_score']         is not None else None,
        }
    return result


# ══════════════════════════════════════════════════════════════
# 4. LOAD MODEL WEIGHTS
# ══════════════════════════════════════════════════════════════

def _load_weights(path=MODEL_WEIGHTS_PATH):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Model weights not found at: {path}\n"
            "Run pre_mid_sem_analysis.py first to generate them."
        )
    with open(path) as f:
        raw = json.load(f)

    for key in ('scaler', 'ridge', 'norm_weights', 'sum_weeks', 'features'):
        if key not in raw:
            raise KeyError(f"model_weights.json is missing required key: '{key}'")

    scaler_mean  = np.array(raw['scaler']['mean_'],  dtype=float)
    scaler_scale = np.array(raw['scaler']['scale_'], dtype=float)

    weights = {
        'features':      raw['features'],
        'scaler_mean':   scaler_mean,
        'scaler_scale':  scaler_scale,
        'coef':          np.array(raw['ridge']['coef_'], dtype=float),
        'intercept':     float(raw['ridge']['intercept_']),
        'norm_weights':  np.array(raw['norm_weights'],   dtype=float),
        'sum_weeks':     raw['sum_weeks'],
        'prior_neutral': float(scaler_mean[2]),
    }

    print(f"  [pre_mid_term] weights loaded from: {path}")
    print(f"  [pre_mid_term] Features     : {weights['features']}")
    print(f"  [pre_mid_term] Coefs        : {weights['coef'].round(4).tolist()}")
    print(f"  [pre_mid_term] Intercept    : {weights['intercept']:.4f}")
    print(f"  [pre_mid_term] prior_neutral: {weights['prior_neutral']:.5f}")
    return weights


# ══════════════════════════════════════════════════════════════
# 5. COMPUTE WEIGHTED SUMS
# ══════════════════════════════════════════════════════════════

def _compute_weighted_sums(weekly_data, sum_weeks, norm_weights, ap_fill, eff_fill):
    ap_vals = np.array(
        [
            weekly_data[w]['ap']
            if w in weekly_data and weekly_data[w]['ap'] is not None
            else ap_fill
            for w in sum_weeks
        ],
        dtype=float,
    )
    eff_vals = np.array(
        [
            weekly_data[w]['effort']
            if w in weekly_data and weekly_data[w]['effort'] is not None
            else eff_fill
            for w in sum_weeks
        ],
        dtype=float,
    )
    return float(norm_weights @ ap_vals), float(norm_weights @ eff_vals)


# ══════════════════════════════════════════════════════════════
# 6. RIDGE INFERENCE (pure NumPy — no sklearn at runtime)
# ══════════════════════════════════════════════════════════════

def _predict(weighted_ap_sum, weighted_eff_sum, prior_midterm, weights):
    x_raw = np.array([weighted_ap_sum, weighted_eff_sum, prior_midterm], dtype=float)
    x_std = (x_raw - weights['scaler_mean']) / weights['scaler_scale']
    raw   = float(weights['coef'] @ x_std) + weights['intercept']
    return round(float(np.clip(raw, 0.0, 100.0)), 2)


# ══════════════════════════════════════════════════════════════
# 7. WRITE PREDICTIONS to pre_mid_term table
#    Appends a new row per student per run (sem_week 6 and 7).
#    Uses get_or_create so re-runs in the same week are idempotent.
# ══════════════════════════════════════════════════════════════

def _write_predictions(predictions, sem_map, current_sem_week):
    rep_semester = min(sem_map.values())

    created_count  = 0
    updated_count  = 0

    for p in predictions:
        obj, created = PreMidTerm.objects.get_or_create(
            student_id = p['student_id'],
            semester   = rep_semester,
            sem_week   = current_sem_week,
            defaults={
                'class_id':               p['class_id'],
                'predicted_midterm_score': p['predicted_midterm'],
            }
        )
        if not created:
            # Re-run in same week — update the score
            obj.predicted_midterm_score = p['predicted_midterm']
            obj.class_id = p['class_id']
            obj.save(update_fields=['predicted_midterm_score', 'class_id'])
            updated_count += 1
        else:
            created_count += 1

    print(f"  [pre_mid_term] Wrote {created_count} new rows, updated {updated_count} existing rows "
          f"in pre_mid_term (sem_week={current_sem_week}, semester={rep_semester})")


# ══════════════════════════════════════════════════════════════
# 8. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def run(sem_week=None, semester=None):

    # when we remove calibrate_analysis_db
    if not(sem_week or semester):
        ctx = _get_sim_context()
        sem_week = ctx['sem_week']  
        sem_map  = ctx['sem_map']
        if sem_week not in PRE_MID_WEEKS:
            print(f"  [pre_mid_term] Skipped — sem_week={sem_week}, fires only at weeks {sorted(PRE_MID_WEEKS)}.")
            return
        rep_semester = min(sem_map.values())

    # when using calibrate_analysi_db
    else:
        rep_semester=semester
        classes = list(ClientClass.objects.using('client_db').all())
        # this part could be wrong
        sem_map = {
            cls.class_id: (cls.odd_sem if semester == 1 else cls.even_sem)
            for cls in classes
            }

    print(f"  [pre_mid_term] sem_week={sem_week}  semester={rep_semester}")

    # ── Load model weights ─────────────────────────────────────
    weights       = _load_weights()
    sum_weeks     = [w for w in weights['sum_weeks'] if w < sem_week]  # only completed weeks
    if not sum_weeks:
        sum_weeks = SUM_WEEKS_FALLBACK
    norm_weights  = weights['norm_weights'][:len(sum_weeks)]
    # Re-normalise weights for however many weeks we actually have
    norm_weights  = norm_weights / norm_weights.sum() if norm_weights.sum() > 0 else norm_weights

    ap_fill       = float(weights['scaler_mean'][0])
    eff_fill      = float(weights['scaler_mean'][1])
    prior_neutral = weights['prior_neutral']

    # ── Fetch ──────────────────────────────────────────────────
    students    = _fetch_students(sem_map)
    all_wm_data = _fetch_weekly_metrics(sem_map, sum_weeks)

    print(f"  [pre_mid_term] Active students  : {len(students)}")
    print(f"  [pre_mid_term] Students with WM : {len(all_wm_data)}  (weeks {sum_weeks})")
    print(f"  [pre_mid_term] prior_midterm    : {prior_neutral:.5f} for all students")

    # ── Predict ────────────────────────────────────────────────
    predictions  = []
    n_no_wm_data = 0

    for stu in students:
        sid = stu['student_id']
        cid = stu['class_id']

        weekly_data = all_wm_data.get(sid, {})
        if not weekly_data:
            n_no_wm_data += 1

        w_ap, w_eff = _compute_weighted_sums(
            weekly_data, sum_weeks, norm_weights, ap_fill, eff_fill
        )
        predicted = _predict(w_ap, w_eff, prior_neutral, weights)

        predictions.append({
            'student_id':        sid,
            'class_id':          cid,
            'weighted_ap_sum':   round(w_ap,  4),
            'weighted_eff_sum':  round(w_eff, 4),
            'predicted_midterm': predicted,
        })

    # ── Write ──────────────────────────────────────────────────
    _write_predictions(predictions, sem_map, sem_week)

    # ── Summary ────────────────────────────────────────────────
    scores = [p['predicted_midterm'] for p in predictions]
    if scores:
        print(f"\n  [pre_mid_term] Done — {len(predictions)} rows written to pre_mid_term")
        print(f"  Score range  : {min(scores):.1f} – {max(scores):.1f}")
        print(f"  Score mean   : {sum(scores) / len(scores):.2f}")
    if n_no_wm_data:
        print(f"  WARNING: {n_no_wm_data} student(s) had no weekly_metrics data — "
              f"filled with scaler training means.")

    print(f"\n  {'student_id':12s} {'w_ap':>8s} {'w_eff':>8s} {'predicted':>10s}")
    print(f"  {'-'*45}")
    for p in predictions[:5]:
        print(f"  {p['student_id']:12s} "
              f"{p['weighted_ap_sum']:8.2f} "
              f"{p['weighted_eff_sum']:8.2f} "
              f"{p['predicted_midterm']:10.2f}")
    if len(predictions) > 5:
        print(f"  ... ({len(predictions) - 5} more rows written)")


if __name__ == '__main__':
    import django, os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    run()
