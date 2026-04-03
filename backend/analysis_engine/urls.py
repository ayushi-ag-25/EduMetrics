
from django.urls import path 
from .views import get_flaggeddata, class_performance, student_performance, student_trajectory

urlpatterns=[
    path('get_flaggeddata/', get_flaggeddata, name='get_flaggeddata'),
    path('class_performance/', class_performance, name='class_performance'), 
    path('student_performance/', student_performance, name='student_performance'),
    path('student_trajectory/', student_trajectory, name='student_trajectory'), 
]