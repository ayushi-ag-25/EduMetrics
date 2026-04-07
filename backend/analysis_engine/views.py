from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from .models import (
    weekly_flags,
    weekly_metrics,
    pre_mid_term,
    pre_end_term,
    risk_of_failing_prediction,
    pre_sem_watchlist,
)
from .serializer import (
    weekly_flagSerializer,
    performanceSerializer,
    PreMidTermSerializer,
    PreEndTermSerializer,
    RiskOfFailingSerializer,
    PreSemWatchlistSerializer,
)

import os
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import traceback #for effective tracking of errors
# import the calibrate function
from .calibrate_analysis_db import calibrate 


# ──────────────────────────────────────────────────────────────
#  EXISTING VIEWS (unchanged)
# ──────────────────────────────────────────────────────────────

@api_view(['GET'])
def get_flaggeddata(request):
    queryset = weekly_flags.objects.filter(
        semester=request.data.get('semester'),
        sem_week=request.data.get('sem_week'),
        class_id=request.data.get('class_id'),
    )
    serializer = weekly_flagSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def class_performance(request):
    queryset = weekly_metrics.objects.filter(class_id=request.data.get('class_id'))
    serializer = performanceSerializer(queryset, many=True, fields=['student_id', 'academic_performance'])
    return Response(serializer.data)


@api_view(['GET'])
def student_performance(request):
    queryset = weekly_metrics.objects.filter(
        student_id=request.data.get('student_id'),
        sem_week=request.data.get('sem_week'),
    )
    serializer = performanceSerializer(queryset, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def student_trajectory(request):
    queryset = weekly_metrics.objects.filter(
        student_id=request.data.get('student_id'),
        sem_week__gte=request.data.get('week_from'),
    )
    serializer = performanceSerializer(queryset, many=True)
    return Response(serializer.data)


# ──────────────────────────────────────────────────────────────
#  NEW VIEWS — PRE MID TERM
# ──────────────────────────────────────────────────────────────

@api_view(['GET'])
def pre_mid_term_list(request):
    """
    Return all predicted midterm scores for a class in a given semester.
    Query params: class_id, semester
    Optionally filter by sem_week (6 or 7) to see a specific prediction pass.
    """
    class_id  = request.query_params.get('class_id')
    semester  = request.query_params.get('semester')
    sem_week  = request.query_params.get('sem_week')

    if not class_id or not semester:
        return Response(
            {'error': 'class_id and semester are required query parameters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = pre_mid_term.objects.filter(class_id=class_id, semester=semester)
    if sem_week:
        qs = qs.filter(sem_week=sem_week)

    serializer = PreMidTermSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def pre_mid_term_student(request):
    """
    Return pre-midterm predictions for a specific student.
    Query params: student_id, semester
    """
    student_id = request.query_params.get('student_id')
    semester   = request.query_params.get('semester')

    if not student_id:
        return Response(
            {'error': 'student_id is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = pre_mid_term.objects.filter(student_id=student_id)
    if semester:
        qs = qs.filter(semester=semester)

    serializer = PreMidTermSerializer(qs, many=True)
    return Response(serializer.data)


# ──────────────────────────────────────────────────────────────
#  NEW VIEWS — PRE END TERM
# ──────────────────────────────────────────────────────────────

@api_view(['GET'])
def pre_end_term_list(request):
    """
    Return all predicted endterm scores for a class in a given semester.
    Query params: class_id, semester
    """
    class_id = request.query_params.get('class_id')
    semester = request.query_params.get('semester')

    if not class_id or not semester:
        return Response(
            {'error': 'class_id and semester are required query parameters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = pre_end_term.objects.filter(class_id=class_id, semester=semester)
    serializer = PreEndTermSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def pre_end_term_student(request):
    """
    Return pre-endterm predictions for a specific student.
    Query params: student_id, semester
    """
    student_id = request.query_params.get('student_id')
    semester   = request.query_params.get('semester')

    if not student_id:
        return Response(
            {'error': 'student_id is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = pre_end_term.objects.filter(student_id=student_id)
    if semester:
        qs = qs.filter(semester=semester)

    serializer = PreEndTermSerializer(qs, many=True)
    return Response(serializer.data)


# ──────────────────────────────────────────────────────────────
#  NEW VIEWS — RISK OF FAILING (dedicated table)
# ──────────────────────────────────────────────────────────────

@api_view(['GET'])
def risk_of_failing_list(request):
    """
    Return risk-of-failing predictions for a class at a given week.
    Query params: class_id, semester, sem_week
    """
    class_id = request.query_params.get('class_id')
    semester = request.query_params.get('semester')
    sem_week = request.query_params.get('sem_week')

    if not class_id or not semester:
        return Response(
            {'error': 'class_id and semester are required query parameters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = risk_of_failing_prediction.objects.filter(class_id=class_id, semester=semester)
    if sem_week:
        qs = qs.filter(sem_week=sem_week)

    serializer = RiskOfFailingSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def risk_of_failing_student(request):
    """
    Return risk-of-failing trajectory for a specific student.
    Query params: student_id, semester
    """
    student_id = request.query_params.get('student_id')
    semester   = request.query_params.get('semester')

    if not student_id:
        return Response(
            {'error': 'student_id is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = risk_of_failing_prediction.objects.filter(student_id=student_id)
    if semester:
        qs = qs.filter(semester=semester)

    serializer = RiskOfFailingSerializer(qs, many=True)
    return Response(serializer.data)


# ──────────────────────────────────────────────────────────────
#  NEW VIEWS — PRE SEM WATCHLIST
# ──────────────────────────────────────────────────────────────

@api_view(['GET'])
def pre_sem_watchlist_list(request):
    """
    Return pre-semester watchlist for a class.
    Query params: class_id, target_semester
    """
    class_id         = request.query_params.get('class_id')
    target_semester  = request.query_params.get('target_semester')

    if not class_id or not target_semester:
        return Response(
            {'error': 'class_id and target_semester are required query parameters.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = pre_sem_watchlist.objects.filter(class_id=class_id, target_semester=target_semester)
    serializer = PreSemWatchlistSerializer(qs, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def pre_sem_watchlist_student(request):
    """
    Return pre-semester watchlist entry for a specific student.
    Query params: student_id, target_semester (optional)
    """
    student_id      = request.query_params.get('student_id')
    target_semester = request.query_params.get('target_semester')

    if not student_id:
        return Response(
            {'error': 'student_id is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = pre_sem_watchlist.objects.filter(student_id=student_id)
    if target_semester:
        qs = qs.filter(target_semester=target_semester)

    serializer = PreSemWatchlistSerializer(qs, many=True)
    return Response(serializer.data)

# NEW
@csrf_exempt #CSRF exempt is used since the request from our streamlit app is not gonna have a CSRF token
def trigger_calibrate(request):
    # Django doesn't use @app.route, so we check the method manually
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # ── Auth ─────────────────────────────────────────────────────────────────
    secret = os.getenv("INTERNAL_SECRET")
    # In Django, headers are in request.META and usually prefixed with HTTP_
    # or you can use request.headers in Django 2.2+
    provided_secret = request.headers.get("X-Internal-Secret")

    if secret and provided_secret != secret:
        return JsonResponse({"error": "forbidden"}, status=403)

    # ── Run ──────────────────────────────────────────────────────────────────
    try:
        result = calibrate()
        return JsonResponse(result, status=200)
    except Exception as e:
        print(f"[FATAL] calibrate() raised:\n{traceback.format_exc()}")
        return JsonResponse({"error": str(e)}, status=500)


# not sure if we need this function
def health(request):
    """Railway health-check endpoint."""
    return JsonResponse({"status": "ok"}, status=200)