from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import weekly_flags,weekly_metrics
from .serializer import weekly_flagSerializer,performanceSerializer

@api_view(['GET'])
def get_flaggeddata(request):
    queryset = weekly_flags.objects.filter(
        semester=request.get('semester'), 
        sem_week=request.get('sem_week'),
        class_id=request.get('class_id'))
    serializer = weekly_flagSerializer(queryset, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def class_performance(request):
    queryset=weekly_metrics.objects.filter(class_id=request.get('class_id'))
    serializer=performanceSerializer(queryset,many=True,fields=['student_id','academic_performance'])
    return Response(serializer.data)

@api_view(['GET'])
def student_performance(request):
    queryset=weekly_metrics.objects.filter(
        student_id=request.get('student_id'),
        sem_week= request.get('sem_Week')
    )
    serializer=performanceSerializer(queryset,many=True)
    return Response(serializer.data)

@api_view(['GET'])
def student_trajectory(request):
    queryset=weekly_metrics.objects.filter(
        student_id=request.get('student_id'),
        sem_week__gte = request.get('week_from'),
    )
    serializer=performanceSerializer(queryset,many=True,)
    return Response(serializer.data)



# Create your views here.
