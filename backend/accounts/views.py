from rest_framework.permissions import AllowAny
from rest_framework.decorators import permission_classes
from rest_framework.decorators import api_view
from .models import Users
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from django.db.models import Max
from analysis_engine.models import weekly_metrics

def get_token(user):
    refresh=RefreshToken.for_user(user)
    return{
        'refresh':str(refresh),
        'access':str(refresh.access_token)
    }

@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    id=request.data.get('advisor_id')
    password=request.data.get('password')

    if not id :
        return Response({'error':'advisor_id is required'},status=400)
    
    advisor=Users.objects.filter(advisor_id=id).first()
    if advisor:
        actual= f"{advisor.advisor_name}{advisor.advisor_id[-3::]}"

        if password==actual:
            # Get latest semester and week for this advisor's class
            agg = weekly_metrics.objects.filter(
                class_id=advisor.class_id
            ).aggregate(max_semester=Max('semester'))
            max_sem = agg['max_semester'] or 1

            agg2 = weekly_metrics.objects.filter(
                class_id=advisor.class_id,
                semester=max_sem
            ).aggregate(max_week=Max('sem_week'))
            max_week = agg2['max_week'] or 1

            res = {
                'message':      'Login successful',
                'class_id':     advisor.class_id,
                'advisor_id':   advisor.advisor_id,
                'advisor_name': advisor.advisor_name,
                'semester':     max_sem,
                'sem_week':     max_week,
            }
            tokens = get_token(advisor)
            res.update(tokens)
            return Response(res)
        return Response({'error': 'Invalid credentials'}, status=401)
    return Response({'error': 'Advisor not found'}, status=404)