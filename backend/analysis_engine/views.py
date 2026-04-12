"""
=================================================================================
  EduMetrics — analysis_engine/views.py

  All API endpoints the frontend (dashboard_updated.html / app.js) needs.

  DESIGN PHILOSOPHY
  The frontend is pure HTML/JS with static mock data. Every endpoint is shaped
  to match the exact data structures in app.js so wiring up fetch() is a
  straight drop-in replacement — no reshaping needed on the frontend side.

  BASE URL: /api/analysis/

  ENDPOINTS
  ─────────────────────────────────────────────────────────────────────────────
  DASHBOARD
    GET  dashboard/summary/?class_id=X&semester=Y&sem_week=Z

  FLAGGED STUDENTS (matches FLAGGED[] in app.js)
    GET  flagged/?class_id=X&semester=Y&sem_week=Z

  ALL STUDENTS ROSTER (matches ALL_STUDENTS[] in app.js)
    GET  students/?class_id=X&semester=Y&sem_week=Z

  STUDENT DETAIL (slideout / deep-dive)
    GET  student/<student_id>/detail/?semester=Y&sem_week=Z

  STUDENT TRAJECTORY (line chart)
    GET  student/<student_id>/trajectory/?semester=Y[&from_week=1]

  CLASS ANALYTICS (heatmap + scatter)
    GET  analytics/?class_id=X&semester=Y&sem_week=Z

  LAST WEEK COMPARISON (matches LAST_WEEK[] in app.js)
    GET  last_week/?class_id=X&semester=Y&sem_week=Z

  PREDICTIONS
    GET  pre_mid_term/?class_id=X&semester=Y[&sem_week=6|7]
    GET  pre_mid_term/student/?student_id=X[&semester=Y]
    GET  pre_end_term/?class_id=X&semester=Y
    GET  pre_end_term/student/?student_id=X[&semester=Y]
    GET  risk_of_failing/?class_id=X&semester=Y[&sem_week=Z]
    GET  risk_of_failing/student/?student_id=X[&semester=Y]
    GET  pre_sem_watchlist/?class_id=X&target_semester=Y
    GET  pre_sem_watchlist/student/?student_id=X[&target_semester=Y]

  INTERNAL
    POST trigger_calibrate/
=================================================================================
"""

import os
import sys
import traceback

from django.db.models import Avg, Max
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import (
    weekly_flags,
    weekly_metrics,
    pre_mid_term,
    pre_end_term,
    risk_of_failing,
    pre_sem_watchlist,
    intervention_log,
)
from .serializer import (
    weekly_flagSerializer,
    performanceSerializer,
    PreMidTermSerializer,
    PreEndTermSerializer,
    RiskOfFailingSerializer,
    PreSemWatchlistSerializer,
)

# Client DB models — wrapped in try so server starts even without client DB
try:
    from .client_models import ClientStudent
    HAS_CLIENT_DB = True
except Exception:
    HAS_CLIENT_DB = False

from .calibrate_analysis_db import calibrate


# ─────────────────────────────────────────────────────────────────────────────
#  SHARED HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _require(request, *params):
    """Check that all named query params are present. Returns (dict, err_response)."""
    missing = [p for p in params if not request.query_params.get(p)]
    if missing:
        return None, Response(
            {'error': f'Missing required query params: {", ".join(missing)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return {p: request.query_params[p] for p in params}, None


def _name_map(class_id):
    """Return {student_id: name} from client DB, or {} if unavailable."""
    if not HAS_CLIENT_DB:
        return {}
    try:
        qs = ClientStudent.objects.using('client_db').filter(class_id=class_id)
        return {s.student_id: s.name for s in qs}
    except Exception:
        return {}


def _risk_level(risk_tier: str) -> str:
    """Map backend risk_tier string → frontend riskLevel (high/med/safe)."""
    rt = (risk_tier or '').lower()
    if 'tier 1' in rt or 'critical' in rt:
        return 'high'
    if 'tier 2' in rt or 'high' in rt:
        return 'high'
    if 'tier 3' in rt or 'warning' in rt:
        return 'med'
    return 'safe'


def _cap(urgency: int) -> int:
    """Clamp urgency_score (can exceed 100) to 0-100 for frontend riskScore."""
    return min(int(urgency or 0), 100)


def _f(val, default=0.0):
    """Safe Decimal/None → float."""
    if val is None:
        return default
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return default


def _avatar(name: str) -> str:
    parts = name.split()
    return ''.join(p[0].upper() for p in parts[:2]) if parts else '?'


def _build_factors(diagnosis: str, urgency_score: int):
    """Turn pipe-delimited diagnosis string into factors[] for the frontend."""
    parts = [d.strip() for d in (diagnosis or '').split('|') if d.strip()]
    COLOR_MAP = {
        'severe absenteeism':   '#ef4444',
        'low attendance':       '#ef4444',
        'attendance fader':     '#f59e0b',
        'stopped submitting':   '#f59e0b',
        'integrity violation':  '#7c3aed',
        'exam failure':         '#ef4444',
        'hard test drop':       '#f59e0b',
    }
    factors = []
    n = max(len(parts), 1)
    for part in parts[:3]:
        color = '#a78bfa'
        for key, col in COLOR_MAP.items():
            if key in part.lower():
                color = col
                break
        factors.append({'label': part, 'pct': min(int(urgency_score * 0.8 / n), 100), 'color': color})
    return factors, parts[0] if parts else 'Unknown'


# ─────────────────────────────────────────────────────────────────────────────
#  1. DASHBOARD SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def dashboard_summary(request):
    """
    GET /api/analysis/dashboard/summary/?class_id=X&semester=Y&sem_week=Z

    Powers the 4 stat cards at the top of the dashboard page.
    """
    params, err = _require(request, 'class_id', 'semester', 'sem_week')
    if err:
        return err

    class_id = params['class_id']
    semester = int(params['semester'])
    sem_week = int(params['sem_week'])

    total_students = weekly_metrics.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).count()

    flags_qs  = weekly_flags.objects.filter(class_id=class_id, semester=semester, sem_week=sem_week)
    flagged   = flags_qs.count()
    avg_urgency = _f(flags_qs.aggregate(a=Avg('urgency_score'))['a'])

    interventions = intervention_log.objects.filter(
        semester=semester, sem_week=sem_week,
        student_id__in=flags_qs.values_list('student_id', flat=True)
    ).count()

    return Response({
        'class_id':                class_id,
        'semester':                semester,
        'sem_week':                sem_week,
        'total_students':          total_students,
        'avg_risk_score':          round(avg_urgency, 1),
        'flagged_this_week':       flagged,
        'interventions_this_week': interventions,
        'risk_breakdown': {
            'critical': flags_qs.filter(risk_tier__icontains='Tier 1').count(),
            'watch':    flags_qs.filter(risk_tier__icontains='Tier 2').count(),
            'warning':  flags_qs.filter(risk_tier__icontains='Tier 3').count(),
            'safe':     max(total_students - flagged, 0),
        },
    })


# ─────────────────────────────────────────────────────────────────────────────
#  2. FLAGGED STUDENTS  — matches app.js FLAGGED[] structure exactly
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def flagged_students(request):
    sys.stdout.write('i nside')
    """
    GET /api/analysis/flagged/?class_id=X&semester=Y&sem_week=Z

    Returns the list of flagged students for the week, shaped to match FLAGGED[]
    in app.js — the dashboard's "Who to act on today" grid.
    """
    params, err = _require(request, 'class_id', 'semester', 'sem_week')
    if err:
        return err

    class_id = params['class_id']
    semester = int(params['semester'])
    sem_week = int(params['sem_week'])

    flags = list(weekly_flags.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).order_by('-urgency_score'))

    names = _name_map(class_id)

    # Class averages for comparison bars
    cls_agg = weekly_metrics.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).aggregate(avg_et=Avg('effort_score'), avg_perf=Avg('academic_performance'))
    class_avg_et   = _f(cls_agg['avg_et'],   65.0)
    class_avg_perf = _f(cls_agg['avg_perf'], 70.0)

    result = []
    for flag in flags:
        sid  = flag.student_id
        name = names.get(sid, sid)

        m = weekly_metrics.objects.filter(
            student_id=sid, semester=semester, sem_week=sem_week
        ).first()

        # Weekly trajectory for line charts
        traj = list(weekly_metrics.objects.filter(
            student_id=sid, semester=semester, sem_week__lte=sem_week
        ).order_by('sem_week').values(
            'sem_week', 'effort_score', 'academic_performance', 'overall_att_pct'
        ))

        week_et = [_f(r['effort_score']) for r in traj]
        week_at = [round(_f(r['overall_att_pct']), 1) for r in traj]
        week_perf = [_f(r['academic_performance']) for r in traj]
        student_avg_et   = round(sum(week_et)   / max(len(week_et),   1), 1)
        student_avg_perf = round(sum(week_perf) / max(len(week_perf), 1), 1)
        student_avg_at   = round(sum(week_at)   / max(len(week_at),   1), 1)

        # Latest midterm prediction
        pmt = pre_mid_term.objects.filter(student_id=sid, semester=semester).order_by('-sem_week').first()
        midterm_str = f"Predicted: {_f(pmt.predicted_midterm_score)}%" if pmt else "N/A"

        # Flag history from intervention_log
        flag_hist = [
            {
                'date':       f"Week {fh['sem_week']}",
                'diagnosis':  fh['trigger_diagnosis'] or 'Flagged',
                'intervened': fh['advisor_notified'],
            }
            for fh in intervention_log.objects.filter(
                student_id=sid, semester=semester
            ).order_by('sem_week').values('sem_week', 'trigger_diagnosis', 'advisor_notified')
        ]

        factors, major_factor = _build_factors(flag.diagnosis, int(flag.urgency_score or 0))
        att_pct = round(_f(m.overall_att_pct), 1) if m else 0.0
        risk_score = _cap(flag.urgency_score)

        result.append({
            # Identity
            'id':     sid,
            'name':   name,
            'roll':   sid,
            'avatar': _avatar(name),

            # Risk
            'risk':         _risk_level(flag.risk_tier),
            'reason':       flag.diagnosis or '',
            'riskFail':     risk_score,
            'riskDetention': min(int(risk_score * 0.7), 100),
            'recovery':     max(0, 100 - risk_score),

            # Current metrics
            'academicPerf': _f(m.academic_performance    if m else None),
            'effortScore':  _f(m.effort_score            if m else None),
            'attendRecent': att_pct,
            'quizSubmit':   round(_f(m.quiz_attempt_rate if m else None) * 100, 1),
            'quizAvg':      _f(m.quiz_avg_pct            if m else None),
            'assignAvg':    _f(m.assn_avg_pct            if m else None),
            'midterm':      midterm_str,

            # Averages
            'avgRisk':       risk_score,
            'avgEt':         student_avg_et,
            'avgAt':         student_avg_at,
            'overallAttend': att_pct,

            # Chart arrays
            'weekEt':         week_et,
            'weekAt':         week_at,
            'classAvgEt':     class_avg_et,
            'classAvgPerf':   class_avg_perf,
            'studentAvgEt':   student_avg_et,
            'studentAvgPerf': student_avg_perf,
            'etThisWeek':    _f(m.effort_score          if m else None),
            'perfThisWeek':  _f(m.academic_performance  if m else None),

            # History
            'flagHistory': flag_hist,
            'factors':     factors,
            'majorFactor': major_factor,
        })
    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
#  3. ALL STUDENTS ROSTER  — matches app.js ALL_STUDENTS[] structure exactly
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def all_students(request):
    """
    GET /api/analysis/students/?class_id=X&semester=Y&sem_week=Z

    Returns every tracked student, shaped like ALL_STUDENTS[] in app.js —
    used for the students page heatmap and the galaxy/scatter view.
    """
    params, err = _require(request, 'class_id', 'semester', 'sem_week')
    if err:
        return err

    class_id = params['class_id']
    semester = int(params['semester'])
    sem_week = int(params['sem_week'])

    metrics  = list(weekly_metrics.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).values(
        'student_id', 'effort_score', 'academic_performance',
        'overall_att_pct', 'quiz_attempt_rate',
        'quiz_avg_pct', 'assn_avg_pct',
    ))
    # Pull latest risk labels from the dedicated risk_of_failing table
    rof_qs = (risk_of_failing.objects
              .filter(class_id=class_id, semester=semester, sem_week__lte=sem_week)
              .order_by('student_id', '-sem_week'))
    rof_map = {}
    for r in rof_qs:
        if r.student_id not in rof_map:
            rof_map[r.student_id] = r

    names = _name_map(class_id)

    flagged_map = {
        f.student_id: f
        for f in weekly_flags.objects.filter(
            class_id=class_id, semester=semester, sem_week=sem_week
        )
    }

    # Latest midterm predictions
    pmt_map = {}
    for p in pre_mid_term.objects.filter(class_id=class_id, semester=semester).order_by('-sem_week'):
        if p.student_id not in pmt_map:
            pmt_map[p.student_id] = _f(p.predicted_midterm_score)

    # Latest endterm predictions
    pet_map = {}
    for p in pre_end_term.objects.filter(class_id=class_id, semester=semester).order_by('-sem_week'):
        if p.student_id not in pet_map:
            pet_map[p.student_id] = _f(p.predicted_endterm_score)

    result = []
    for m in metrics:
        sid  = m['student_id']
        flag = flagged_map.get(sid)
        name = names.get(sid, sid)

        if flag:
            risk_score = _cap(flag.urgency_score)
            risk_lv    = _risk_level(flag.risk_tier)
        else:
            rof_row    = rof_map.get(m['student_id'])
            p_fail     = float(rof_row.p_fail) if rof_row else 0.0
            risk_score = min(int(p_fail * 100), 100)
            risk_lv    = ('high' if risk_score >= 70 else
                          'med'  if risk_score >= 45 else 'safe')

        att_pct = round(_f(m['overall_att_pct']), 1)
        quiz_sub_pct = round(_f(m['quiz_attempt_rate']) * 100, 1)
        engagement   = round((quiz_sub_pct + att_pct) / 2, 1)

        result.append({
            'id':           sid,
            'name':         name,
            'roll':         sid,
            'avatar':       _avatar(name),
            'academicPerf': _f(m['academic_performance']),
            'riskScore':    risk_score,
            'effort':       _f(m['effort_score']),
            'engagement':   engagement,
            'predMidterm':  pmt_map.get(sid, _f(m['academic_performance'])),
            'predEndterm':  pet_map.get(sid, _f(m['academic_performance'])),
            'attendance':   att_pct,
            'riskLevel':    risk_lv,
        })

    result.sort(key=lambda x: x['riskScore'], reverse=True)
    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
#  4. STUDENT DETAIL
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def student_detail(request, student_id):
    """
    GET /api/analysis/student/<student_id>/detail/?semester=Y&sem_week=Z

    Full deep-dive data for the student slideout panel.
    """
    semester = request.query_params.get('semester')
    sem_week = request.query_params.get('sem_week')

    if not semester:
        return Response({'error': 'semester is required'}, status=400)

    semester_int = int(semester)
    sem_week_int = int(sem_week) if sem_week else None

    # Current-week metrics
    mf = dict(student_id=student_id, semester=semester_int)
    if sem_week_int:
        mf['sem_week'] = sem_week_int
    m = weekly_metrics.objects.filter(**mf).order_by('-sem_week').first()

    # Trajectory
    traj_qs = weekly_metrics.objects.filter(student_id=student_id, semester=semester_int)
    if sem_week_int:
        traj_qs = traj_qs.filter(sem_week__lte=sem_week_int)
    traj = list(traj_qs.order_by('sem_week').values(
        'sem_week', 'effort_score', 'academic_performance',
        'overall_att_pct', 'quiz_avg_pct', 'assn_avg_pct',
    ))

    week_et   = [_f(r['effort_score'])          for r in traj]
    week_at   = [round(_f(r['overall_att_pct']), 1) for r in traj]
    week_perf = [_f(r['academic_performance'])  for r in traj]

    # Current flag
    cf_qs = weekly_flags.objects.filter(student_id=student_id, semester=semester_int)
    if sem_week_int:
        cf_qs = cf_qs.filter(sem_week=sem_week_int)
    curr_flag = cf_qs.order_by('-sem_week').first()

    # Flag history
    # build a set of weeks where advisor was notified
    intervened_weeks = set(
        intervention_log.objects.filter(student_id=student_id, semester=semester_int, advisor_notified=True)
        .values_list('sem_week', flat=True)
    )

    flag_hist = [
        {
            'date':       f"Week {f['sem_week']}",          # string not int
            'diagnosis':  f['diagnosis'],
            'intervened': f['sem_week'] in intervened_weeks, # merged from intervention_log
        }
        for f in weekly_flags.objects.filter(
            student_id=student_id, semester=semester_int
        ).order_by('sem_week').values('sem_week', 'risk_tier', 'urgency_score', 'diagnosis', 'archetype')
    ]

    # Intervention history
    int_hist = [
        {
            'week':        i['sem_week'],
            'escalation':  i['escalation_level'],
            'diagnosis':   i['trigger_diagnosis'],
            'intervened':  i['advisor_notified'],
            'notes':       i['notes'],
        }
        for i in intervention_log.objects.filter(
            student_id=student_id, semester=semester_int
        ).order_by('sem_week').values('sem_week', 'escalation_level', 'trigger_diagnosis', 'advisor_notified', 'notes')
    ]

    pmt = pre_mid_term.objects.filter(student_id=student_id, semester=semester_int).order_by('-sem_week').first()
    pet = pre_end_term.objects.filter(student_id=student_id, semester=semester_int).order_by('-sem_week').first()
    rof = risk_of_failing.objects.filter(student_id=student_id, semester=semester_int).order_by('-sem_week').first()

    cls_agg = weekly_metrics.objects.filter(
    class_id=m.class_id if m else '', semester=semester_int, sem_week=sem_week_int
    ).aggregate(avg_et=Avg('effort_score'), avg_perf=Avg('academic_performance'))
    class_avg_et   = _f(cls_agg['avg_et'],  65.0)
    class_avg_perf = _f(cls_agg['avg_perf'], 70.0)

    return Response({
        'student_id': student_id,
        'semester':   semester_int,
        'sem_week':   sem_week_int,

        # Snapshot
        'effort_score':         _f(m.effort_score if m else None),
        'academic_performance': _f(m.academic_performance if m else None),
        'overall_att_pct':      round(_f(m.overall_att_pct if m else None), 1),
        'quiz_attempt_rate':     round(_f(m.quiz_attempt_rate if m else None) * 100, 1),
        'quiz_avg_pct':         _f(m.quiz_avg_pct if m else None),
        'assn_avg_pct':         _f(m.assn_avg_pct if m else None),
        'library_visits':     int(m.library_visits or 0) if m else 0,
        'book_borrows':       int(m.book_borrows or 0)   if m else 0,

        # Risk
        'risk_tier':     curr_flag.risk_tier if curr_flag else 'Safe',
        'risk_level':    _risk_level(curr_flag.risk_tier if curr_flag else ''),
        'urgency_score': int(curr_flag.urgency_score or 0) if curr_flag else 0,
        'diagnosis':     curr_flag.diagnosis if curr_flag else '',
        'archetype':     curr_flag.archetype if curr_flag else None,

        # Predictions
        'predicted_midterm_score': _f(pmt.predicted_midterm_score if pmt else None),
        'predicted_endterm_score': _f(pet.predicted_endterm_score if pet else None),
        'p_fail':                  _f(rof.p_fail if rof else None),
        'risk_label':              rof.risk_label if rof else 'LOW',

        # Charts
        'week_labels': [f"W{r['sem_week']}" for r in traj],
        'weekEt':     week_et,
        'weekAt':     week_at,
        'weekPerf':   week_perf,
        'weekQuiz':   [_f(r['quiz_avg_pct'])  for r in traj],

        # History
        'flagHistory':         flag_hist,
        'interventionHistory': int_hist,

        # Aligned names (frontend expects these exact keys)
        'avgEt':          round(sum(week_et) / max(len(week_et), 1), 1),
        'avgAt':          round(sum(week_at) / max(len(week_at), 1), 1),
        'overallAttend':  round(_f(m.overall_att_pct if m else None), 1),
        'riskFail':       min(int(_f(rof.p_fail if rof else None) * 100), 100),
        'midterm':        f"Predicted: {_f(pmt.predicted_midterm_score if pmt else None)}%" if pmt else "N/A",
        'avgRisk':        int(curr_flag.urgency_score or 0) if curr_flag else 0,
        'riskDetention':  min(int((curr_flag.urgency_score or 0) * 0.7), 100) if curr_flag else 0,
        'etThisWeek':     _f(m.effort_score if m else None),
        'perfThisWeek':   _f(m.academic_performance if m else None),

        # Class averages for quad scatter
        'classAvgEt':     class_avg_et,
        'classAvgPerf':   class_avg_perf,
        'studentAvgEt':   round(sum(week_et)   / max(len(week_et),   1), 1),
        'studentAvgPerf': round(sum(week_perf) / max(len(week_perf), 1), 1),
    })


# ─────────────────────────────────────────────────────────────────────────────
#  5. STUDENT TRAJECTORY (line chart only)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def student_trajectory_view(request, student_id):
    """
    GET /api/analysis/student/<student_id>/trajectory/?semester=Y[&from_week=1]
    """
    semester  = request.query_params.get('semester')
    from_week = int(request.query_params.get('from_week', 1))

    if not semester:
        return Response({'error': 'semester is required'}, status=400)

    qs = list(weekly_metrics.objects.filter(
        student_id=student_id, semester=int(semester), sem_week__gte=from_week
    ).order_by('sem_week').values(
        'sem_week', 'effort_score', 'academic_performance',
        'overall_att_pct', 'quiz_avg_pct', 'assn_avg_pct',
    ))

    return Response({
        'student_id': student_id,
        'semester':   int(semester),
        'weeks':      [f"W{r['sem_week']}" for r in qs],
        'effort':     [_f(r['effort_score'])          for r in qs],
        'performance':[_f(r['academic_performance'])  for r in qs],
        'attendance': [round(_f(r['overall_att_pct']), 1) for r in qs],
        'quiz':       [_f(r['quiz_avg_pct'])           for r in qs],
        'assignment': [_f(r['assn_avg_pct'])           for r in qs],
    })


# ─────────────────────────────────────────────────────────────────────────────
#  6. CLASS ANALYTICS (analytics page)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def class_analytics(request):
    """
    GET /api/analysis/analytics/?class_id=X&semester=Y&sem_week=Z

    Powers the analytics page:
      - scatter plot: effort vs academic_performance (coloured by risk)
      - heatmap: student × metric grid
      - weekly class averages: line chart
    """
    params, err = _require(request, 'class_id', 'semester', 'sem_week')
    if err:
        return err

    class_id = params['class_id']
    semester = int(params['semester'])
    sem_week = int(params['sem_week'])

    metrics = list(weekly_metrics.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).values(
        'student_id', 'effort_score', 'academic_performance',
        'overall_att_pct', 'quiz_avg_pct', 'assn_avg_pct',
        'quiz_attempt_rate', 'library_visits',
    ))

    names = _name_map(class_id)
    flagged_ids = set(weekly_flags.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).values_list('student_id', flat=True))

    scatter = [{
        'student_id':  m['student_id'],
        'name':        names.get(m['student_id'], m['student_id']),
        'effort':      _f(m['effort_score']),
        'performance': _f(m['academic_performance']),
        'attendance':  round(_f(m['overall_att_pct']), 1),
        'flagged':     m['student_id'] in flagged_ids,
    } for m in metrics]

    heatmap = sorted([{
        'student_id':  m['student_id'],
        'name':        names.get(m['student_id'], m['student_id']),
        'avatar':      _avatar(names.get(m['student_id'], m['student_id'])),
        'effort':      _f(m['effort_score']),
        'performance': _f(m['academic_performance']),
        'attendance':  round(_f(m['overall_att_pct']), 1),
        'quiz_avg':    _f(m['quiz_avg_pct']),
        'assn_avg':    _f(m['assn_avg_pct']),
        'quiz_submit': round(_f(m['quiz_attempt_rate']) * 100, 1),
        'library':     int(m['library_visits'] or 0),
        'flagged':     m['student_id'] in flagged_ids,
    } for m in metrics], key=lambda x: x['performance'], reverse=True)

    weekly_avgs = list(weekly_metrics.objects.filter(
        class_id=class_id, semester=semester, sem_week__lte=sem_week
    ).values('sem_week').annotate(
        avg_effort=Avg('effort_score'),
        avg_perf=Avg('academic_performance'),
        avg_att=Avg('overall_att_pct'),
    ).order_by('sem_week'))

    cls = weekly_metrics.objects.filter(
        class_id=class_id, semester=semester, sem_week=sem_week
    ).aggregate(avg_et=Avg('effort_score'), avg_perf=Avg('academic_performance'))

    return Response({
        'class_id':          class_id,
        'semester':          semester,
        'sem_week':          sem_week,
        'scatter':           scatter,
        'heatmap':           heatmap,
        'class_avg_effort':  _f(cls['avg_et']),
        'class_avg_perf':    _f(cls['avg_perf']),
        'weekly_averages': [{
            'week':       f"W{r['sem_week']}",
            'avg_effort': _f(r['avg_effort']),
            'avg_perf':   _f(r['avg_perf']),
            'avg_att':    round(_f(r['avg_att']), 1),
        } for r in weekly_avgs],
    })


# ─────────────────────────────────────────────────────────────────────────────
#  7. LAST WEEK COMPARISON  — matches app.js LAST_WEEK[] structure exactly
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def last_week_comparison(request):
    """
    GET /api/analysis/last_week/?class_id=X&semester=Y&sem_week=Z

    Returns flagged students from the previous week with delta comparisons —
    shaped like LAST_WEEK[] in app.js.
    """
    params, err = _require(request, 'class_id', 'semester', 'sem_week')
    if err:
        return err

    class_id  = params['class_id']
    semester  = int(params['semester'])
    sem_week  = int(params['sem_week'])
    prev_week = sem_week - 1

    if prev_week < 1:
        return Response([])

    prev_flags = list(weekly_flags.objects.filter(
        class_id=class_id, semester=semester, sem_week=prev_week
    ).order_by('-urgency_score'))

    names = _name_map(class_id)

    result = []
    for flag in prev_flags:
        sid  = flag.student_id
        name = names.get(sid, sid)

        curr_m = weekly_metrics.objects.filter(student_id=sid, semester=semester, sem_week=sem_week).first()
        prev_m = weekly_metrics.objects.filter(student_id=sid, semester=semester, sem_week=prev_week).first()
        curr_f = weekly_flags.objects.filter(student_id=sid, semester=semester, sem_week=sem_week).first()
        latest_int = intervention_log.objects.filter(student_id=sid, semester=semester).order_by('-logged_at').first()

        pmt = pre_mid_term.objects.filter(student_id=sid, semester=semester).order_by('-sem_week').first()
        midterm_str = f"Predicted: {_f(pmt.predicted_midterm_score)}%" if pmt else "N/A"

        factors, _ = _build_factors(flag.diagnosis, int(flag.urgency_score or 0))

        et_curr  = _f(curr_m.effort_score if curr_m else None)
        et_prev  = _f(prev_m.effort_score if prev_m else None)
        at_curr  = round(_f(curr_m.overall_att_pct if curr_m else None), 1)
        at_prev  = round(_f(prev_m.overall_att_pct if prev_m else None), 1)
        risk_prev = _cap(flag.urgency_score)
        risk_curr = _cap(curr_f.urgency_score) if curr_f else 0

        result.append({
            'id':      sid,
            'name':    name,
            'roll':    sid,
            'avatar':  _avatar(name),
            'risk':    _risk_level(flag.risk_tier),
            'midterm': midterm_str,
            'factors': factors,

            # Delta values
            'etCurr':   et_curr,
            'etPrev':   et_prev,
            'atCurr':   at_curr,
            'atPrev':   at_prev,
            'riskCurr': risk_curr,
            'riskPrev': risk_prev,

            # For detail card
            'avgRisk':       risk_prev,
            'avgEt':         et_prev,
            'avgAt':         at_prev,
            'overallAttend': at_prev,
            'riskDetention': min(int(risk_prev * 0.7), 100),
            'riskFailing':   risk_prev,
            'recovery':      max(0, 100 - risk_prev),

            # Intervention
            'status':       'intervene' if curr_f else 'resolved',
            'intervention': (latest_int.notes or latest_int.trigger_diagnosis
                             if latest_int else ''),
        })

    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
#  8-11. PREDICTION ENDPOINTS (unchanged from original, cleaned up)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
def pre_mid_term_list(request):
    """GET /api/analysis/pre_mid_term/?class_id=X&semester=Y[&sem_week=6|7]"""
    class_id = request.query_params.get('class_id')
    semester = request.query_params.get('semester')
    sem_week = request.query_params.get('sem_week')
    if not class_id or not semester:
        return Response({'error': 'class_id and semester are required'}, status=400)
    qs = pre_mid_term.objects.filter(class_id=class_id, semester=semester)
    if sem_week:
        qs = qs.filter(sem_week=sem_week)
    return Response(PreMidTermSerializer(qs, many=True).data)


@api_view(['GET'])
def pre_mid_term_student(request):
    """GET /api/analysis/pre_mid_term/student/?student_id=X[&semester=Y]"""
    student_id = request.query_params.get('student_id')
    semester   = request.query_params.get('semester')
    if not student_id:
        return Response({'error': 'student_id is required'}, status=400)
    qs = pre_mid_term.objects.filter(student_id=student_id)
    if semester:
        qs = qs.filter(semester=semester)
    return Response(PreMidTermSerializer(qs.order_by('-sem_week'), many=True).data)


@api_view(['GET'])
def pre_end_term_list(request):
    """GET /api/analysis/pre_end_term/?class_id=X&semester=Y"""
    class_id = request.query_params.get('class_id')
    semester = request.query_params.get('semester')
    if not class_id or not semester:
        return Response({'error': 'class_id and semester are required'}, status=400)
    qs = pre_end_term.objects.filter(class_id=class_id, semester=semester)
    return Response(PreEndTermSerializer(qs, many=True).data)


@api_view(['GET'])
def pre_end_term_student(request):
    """GET /api/analysis/pre_end_term/student/?student_id=X[&semester=Y]"""
    student_id = request.query_params.get('student_id')
    semester   = request.query_params.get('semester')
    if not student_id:
        return Response({'error': 'student_id is required'}, status=400)
    qs = pre_end_term.objects.filter(student_id=student_id)
    if semester:
        qs = qs.filter(semester=semester)
    return Response(PreEndTermSerializer(qs.order_by('-sem_week'), many=True).data)


@api_view(['GET'])
def risk_of_failing_list(request):
    """GET /api/analysis/risk_of_failing/?class_id=X&semester=Y[&sem_week=Z]"""
    class_id = request.query_params.get('class_id')
    semester = request.query_params.get('semester')
    sem_week = request.query_params.get('sem_week')
    if not class_id or not semester:
        return Response({'error': 'class_id and semester are required'}, status=400)
    qs = risk_of_failing.objects.filter(class_id=class_id, semester=semester)
    if sem_week:
        qs = qs.filter(sem_week=sem_week)
    return Response(RiskOfFailingSerializer(qs, many=True).data)


@api_view(['GET'])
def risk_of_failing_student(request):
    """GET /api/analysis/risk_of_failing/student/?student_id=X[&semester=Y]"""
    student_id = request.query_params.get('student_id')
    semester   = request.query_params.get('semester')
    if not student_id:
        return Response({'error': 'student_id is required'}, status=400)
    qs = risk_of_failing.objects.filter(student_id=student_id)
    if semester:
        qs = qs.filter(semester=semester)
    return Response(RiskOfFailingSerializer(qs.order_by('-sem_week'), many=True).data)


@api_view(['GET'])
def pre_sem_watchlist_list(request):
    """GET /api/analysis/pre_sem_watchlist/?class_id=X&target_semester=Y"""
    class_id        = request.query_params.get('class_id')
    target_semester = request.query_params.get('target_semester')
    if not class_id or not target_semester:
        return Response({'error': 'class_id and target_semester are required'}, status=400)
    target_semester = int(target_semester)   # ← added cast
    qs = pre_sem_watchlist.objects.filter(class_id=class_id, target_semester=target_semester)
    print(f"[DEBUG ...]  → {qs.count()} rows")
    return Response(PreSemWatchlistSerializer(qs, many=True).data)


@api_view(['GET'])
def pre_sem_watchlist_student(request):
    """GET /api/analysis/pre_sem_watchlist/student/?student_id=X[&target_semester=Y]"""
    student_id      = request.query_params.get('student_id')
    target_semester = int(request.query_params.get('target_semester'))
    if not student_id:
        return Response({'error': 'student_id is required'}, status=400)
    qs = pre_sem_watchlist.objects.filter(student_id=student_id)
    if target_semester:
        qs = qs.filter(target_semester=target_semester)
    return Response(PreSemWatchlistSerializer(qs, many=True).data)

# ─────────────────────────────────────────────────────────────────────────────
#  INTERVENTIONS  — matches app.js INTERVENTIONS[] structure exactly
# ─────────────────────────────────────────────────────────────────────────────


@api_view(['GET'])
def interventions_list(request):
    """GET /api/analysis/interventions/?class_id=X&semester=Y&sem_week=Z"""
    params, err = _require(request, 'class_id', 'semester', 'sem_week')
    if err:
        return err

    class_id = params['class_id']
    semester = int(params['semester'])
    sem_week = int(params['sem_week'])

    logs = intervention_log.objects.filter(
        student_id__in=weekly_metrics.objects.filter(
            class_id=class_id, semester=semester
        ).values_list('student_id', flat=True),
        semester=semester,
        sem_week__lte=sem_week,
    ).order_by('-sem_week', '-logged_at')

    names = _name_map(class_id)

    result = []
    for log in logs:
        sid  = log.student_id
        name = names.get(sid, sid)
        result.append({
            'id':              log.id,
            'student_id':      sid,
            'name':            name,
            'avatar':          _avatar(name),
            'week':            log.sem_week,
            'escalation_level': log.escalation_level,
            'type':            f"Level {log.escalation_level} Escalation",
            'date':            f"Week {log.sem_week}",
            'diagnosis':       log.trigger_diagnosis or '',
            'advisor_notified': log.advisor_notified,
            'notes':           log.notes or '',
        })

    return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
#  INTERNAL / INFRA
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
def trigger_calibrate(request):
    """POST /api/analysis/trigger_calibrate/ — run full analysis pipeline."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    secret          = os.getenv('INTERNAL_SECRET')
    provided_secret = request.headers.get('X-Internal-Secret')
    if secret and provided_secret != secret:
        return JsonResponse({'error': 'forbidden'}, status=403)

    try:
        result = calibrate()
        return JsonResponse(result, status=200)
    except Exception as e:
        print(f'[FATAL] calibrate() raised:\n{traceback.format_exc()}')
        return JsonResponse({'error': str(e)}, status=500)

