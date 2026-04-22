# ============================================================
#  analysis_engine/pre_end_term.py  (Django ORM version)
#
#  Runs at sem_week == 17 (the last teaching week before the endterm).
#  Predicts endterm score using Ridge regression (pure NumPy).
#  Writes prediction into the dedicated `pre_end_term` table.
#
#  Logic mirrors pre_mid_term.py but:
#    - Fires at week 17 only (PRE_END_WEEK = 17)
#    - Uses weeks 10-16 as feature input (post-midterm teaching weeks)
#    - Also incorporates actual midterm score as a feature
#    - Loads weights from endterm_model_weights.json
#
#  All DB access via Django ORM.
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
    ClientExamResult,
    ClientExamSchedule,
)

# ── Analysis DB models ────────────────────────────────────────
from analysis_engine.models import weekly_metrics, PreEndTerm


# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

_HERE                     = os.path.dirname(os.path.abspath(__file__))
ENDTERM_MODEL_WEIGHTS_PATH = os.path.join(_HERE,'models','endterm_model_weightsjson')
# Fall back to midterm weights if endterm weights don't exist yet
MIDTERM_MODEL_WEIGHTS_PATH = os.path.join(_HERE, 'models','midterm_model_weights.json')

PRE_END_WEEK   = 17           # week at which this script fires
ENDTERM_WEEK   = 18           # actual exam week (for reference)

# Post-midterm weeks used as input features
POST_MID_WEEKS = list(range(9, 17))   # weeks 9-16 (week 8 = midterm exam, skip)


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
# 3. FETCH POST-MIDTERM WEEKLY METRICS (weeks 9-16)
# ══════════════════════════════════════════════════════════════

def _fetch_weekly_metrics(sem_map, feature_weeks):
    """
    Returns { student_id: { week: {'ap': float|None, 'effort': float|None} } }
    """
    semesters = list(set(sem_map.values()))

    qs = weekly_metrics.objects.filter(
        semester__in=semesters,
        sem_week__in=feature_weeks,
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
# 4. FETCH ACTUAL MIDTERM SCORES from client DB
#    Used as an additional feature for endterm prediction.
# ══════════════════════════════════════════════════════════════

def _fetch_midterm_scores(sem_map):
    """
    Returns { student_id: avg_midterm_score_pct (float) }
    Averages across all subjects in case a student has multiple midterms.
    """
    semesters = list(set(sem_map.values()))

    try:
        qs = ClientExamResult.objects.using('client_db').filter(
            semester__in=semesters,
            exam_type='midterm',
        ).values('student_id', 'score_pct')
    except Exception:
        # exam_type field might differ — fall back to weekly_metrics.midterm_score_pct
        qs = []

    scores = {}
    if qs:
        from collections import defaultdict
        bucket = defaultdict(list)
        for r in qs:
            bucket[r['student_id']].append(float(r['score_pct']) if r['score_pct'] is not None else None)
        for sid, vals in bucket.items():
            valid = [v for v in vals if v is not None]
            scores[sid] = sum(valid) / len(valid) if valid else None
    else:
        # Fallback: read from weekly_metrics.midterm_score_pct
        qs2 = weekly_metrics.objects.filter(
            semester__in=semesters,
            midterm_score_pct__isnull=False,
        ).values('student_id', 'midterm_score_pct')
        from collections import defaultdict
        bucket = defaultdict(list)
        for r in qs2:
            bucket[r['student_id']].append(float(r['midterm_score_pct']))
        for sid, vals in bucket.items():
            scores[sid] = sum(vals) / len(vals) if vals else None

    return scores


# ══════════════════════════════════════════════════════════════
# 5. LOAD MODEL WEIGHTS
#    Tries endterm_model_weights.json first; falls back to
#    model_weights.json (midterm weights) if not present.
# ══════════════════════════════════════════════════════════════

def _load_weights():
    path = ENDTERM_MODEL_WEIGHTS_PATH
    if not os.path.exists(path):
        print(f"  [pre_end_term] endterm_model_weights.json not found — falling back to midterm weights.")
        path = MIDTERM_MODEL_WEIGHTS_PATH

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No model weights found at:\n  {ENDTERM_MODEL_WEIGHTS_PATH}\n  {MIDTERM_MODEL_WEIGHTS_PATH}\n"
            "Please provide endterm_model_weights.json in the analysis_engine directory."
        )

    with open(path) as f:
        raw = json.load(f)

    for key in ('scaler', 'ridge', 'norm_weights', 'sum_weeks', 'features'):
        if key not in raw:
            raise KeyError(f"model weights file is missing required key: '{key}'")

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
        'prior_neutral': float(scaler_mean[2]) if len(scaler_mean) > 2 else 0.0,
    }

    print(f"  [pre_end_term] weights loaded from: {path}")
    print(f"  [pre_end_term] Features     : {weights['features']}")
    print(f"  [pre_end_term] Coefs        : {weights['coef'].round(4).tolist()}")
    print(f"  [pre_end_term] Intercept    : {weights['intercept']:.4f}")
    return weights


# ══════════════════════════════════════════════════════════════
# 6. COMPUTE WEIGHTED SUMS over post-midterm weeks
# ══════════════════════════════════════════════════════════════

def _compute_weighted_sums(weekly_data, feature_weeks, norm_weights, ap_fill, eff_fill):
    ap_vals = np.array(
        [
            weekly_data[w]['ap']
            if w in weekly_data and weekly_data[w]['ap'] is not None
            else ap_fill
            for w in feature_weeks
        ],
        dtype=float,
    )
    eff_vals = np.array(
        [
            weekly_data[w]['effort']
            if w in weekly_data and weekly_data[w]['effort'] is not None
            else eff_fill
            for w in feature_weeks
        ],
        dtype=float,
    )
    return float(norm_weights @ ap_vals), float(norm_weights @ eff_vals)


# ══════════════════════════════════════════════════════════════
# 7. RIDGE INFERENCE (pure NumPy)
# ══════════════════════════════════════════════════════════════

def _predict(weighted_ap_sum, weighted_eff_sum, prior_score, weights):
    """
    prior_score: actual midterm score (or weights['prior_neutral'] if unavailable).
    """
    x_raw = np.array([weighted_ap_sum, weighted_eff_sum, prior_score], dtype=float)
    x_std = (x_raw - weights['scaler_mean']) / weights['scaler_scale']
    raw   = float(weights['coef'] @ x_std) + weights['intercept']
    return round(float(np.clip(raw, 0.0, 100.0)), 2)


# ══════════════════════════════════════════════════════════════
# 8. WRITE PREDICTIONS to pre_end_term table
#    Idempotent: re-running at week 17 updates the existing row.
# ══════════════════════════════════════════════════════════════

def _write_predictions(predictions, sem_map):
    rep_semester  = min(sem_map.values())
    created_count = 0
    updated_count = 0

    for p in predictions:
        obj, created = PreEndTerm.objects.get_or_create(
            student_id = p['student_id'],
            semester   = rep_semester,
            sem_week   = PRE_END_WEEK,
            defaults={
                'class_id':                p['class_id'],
                'predicted_endterm_score': p['predicted_endterm'],
            }
        )
        if not created:
            obj.predicted_endterm_score = p['predicted_endterm']
            obj.class_id = p['class_id']
            obj.save(update_fields=['predicted_endterm_score', 'class_id'])
            updated_count += 1
        else:
            created_count += 1

    print(f"  [pre_end_term] Wrote {created_count} new rows, updated {updated_count} existing rows "
          f"in pre_end_term (sem_week={PRE_END_WEEK}, semester={rep_semester})")


# ══════════════════════════════════════════════════════════════
# 9. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════

def run(sem_week=None, semester=None):
    """
    Public entry point.
    Fires at sem_week 17 (last teaching week before endterm).
    Writes to the dedicated pre_end_term table.
    """
    print("  [pre_end_term] Starting ...")

    # in absence of calibrate_analysis_db
    if not(sem_week or semester):
        ctx = _get_sim_context()
        sem_week = ctx['sem_week']
        sem_map  = ctx['sem_map']
        rep_semester = min(sem_map.values())
        if sem_week != PRE_END_WEEK:
            print(f"  [pre_end_term] Skipped — sem_week={sem_week}, fires only at week {PRE_END_WEEK}.")
            return

    # when calibrate_analysis_db is written
    else:
        rep_semester=semester
        classes = list(ClientClass.objects.using('client_db').all())
        # this part could be wrong
        sem_map = {
            cls.class_id: (cls.odd_sem if semester == 1 else cls.even_sem)
            for cls in classes
            }

    print(f"  [pre_end_term] sem_week={sem_week}  semester={rep_semester}")

    # ── Load model weights ─────────────────────────────────────
    weights      = _load_weights()

    # Determine which feature weeks to use (post-midterm)
    model_weeks  = weights.get('sum_weeks', POST_MID_WEEKS)
    feature_weeks = [w for w in model_weeks if 8 < w < sem_week]
    if not feature_weeks:
        feature_weeks = POST_MID_WEEKS

    raw_norm     = weights['norm_weights']
    # Trim/extend norm_weights to match number of feature weeks
    n = len(feature_weeks)
    if len(raw_norm) >= n:
        norm_weights = raw_norm[:n]
    else:
        # Extend with equal weights for extra weeks
        extra = np.ones(n - len(raw_norm)) / n
        norm_weights = np.concatenate([raw_norm, extra])
    if norm_weights.sum() > 0:
        norm_weights = norm_weights / norm_weights.sum()

    ap_fill       = float(weights['scaler_mean'][0])
    eff_fill      = float(weights['scaler_mean'][1])
    prior_neutral = weights['prior_neutral']  # used when actual midterm score unavailable

    # ── Fetch ──────────────────────────────────────────────────
    students      = _fetch_students(sem_map)
    all_wm_data   = _fetch_weekly_metrics(sem_map, feature_weeks)
    midterm_scores = _fetch_midterm_scores(sem_map)

    print(f"  [pre_end_term] Active students     : {len(students)}")
    print(f"  [pre_end_term] Students with WM    : {len(all_wm_data)}  (weeks {feature_weeks})")
    print(f"  [pre_end_term] Students w/ midterm : {sum(1 for v in midterm_scores.values() if v is not None)}")

    # ── Predict ────────────────────────────────────────────────
    predictions  = []
    n_no_wm_data = 0
    n_no_mid     = 0

    for stu in students:
        sid = stu['student_id']
        cid = stu['class_id']

        weekly_data = all_wm_data.get(sid, {})
        if not weekly_data:
            n_no_wm_data += 1

        actual_mid = midterm_scores.get(sid)
        if actual_mid is None:
            actual_mid = prior_neutral
            n_no_mid  += 1

        w_ap, w_eff = _compute_weighted_sums(
            weekly_data, feature_weeks, norm_weights, ap_fill, eff_fill
        )
        predicted = _predict(w_ap, w_eff, actual_mid, weights)

        predictions.append({
            'student_id':       sid,
            'class_id':         cid,
            'weighted_ap_sum':  round(w_ap,  4),
            'weighted_eff_sum': round(w_eff, 4),
            'actual_midterm':   round(actual_mid, 2),
            'predicted_endterm': predicted,
        })

    # ── Write ──────────────────────────────────────────────────
    _write_predictions(predictions, sem_map)

    # ── Summary ────────────────────────────────────────────────
    scores = [p['predicted_endterm'] for p in predictions]
    if scores:
        print(f"\n  [pre_end_term] Done — {len(predictions)} rows written to pre_end_term")
        print(f"  Score range  : {min(scores):.1f} – {max(scores):.1f}")
        print(f"  Score mean   : {sum(scores) / len(scores):.2f}")
    if n_no_wm_data:
        print(f"  WARNING: {n_no_wm_data} student(s) had no post-midterm weekly_metrics data.")
    if n_no_mid:
        print(f"  WARNING: {n_no_mid} student(s) had no actual midterm score — used prior_neutral.")

    print(f"\n  {'student_id':12s} {'w_ap':>8s} {'w_eff':>8s} {'midterm':>8s} {'predicted':>10s}")
    print(f"  {'-'*55}")
    for p in predictions[:5]:
        print(f"  {p['student_id']:12s} "
              f"{p['weighted_ap_sum']:8.2f} "
              f"{p['weighted_eff_sum']:8.2f} "
              f"{p['actual_midterm']:8.2f} "
              f"{p['predicted_endterm']:10.2f}")
    if len(predictions) > 5:
        print(f"  ... ({len(predictions) - 5} more rows written)")


if __name__ == '__main__':
    import django, os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    django.setup()
    run()
