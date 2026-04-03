
from rest_framework.decorators import api_view
from .models import Users
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response

def get_token(user):
    refresh=RefreshToken.for_user(user)
    return{
        'refresh':str(refresh),
        'access':str(refresh.access_token)
    }

@api_view(['GET'])
def login(request):
    id=request.data.get('advisor_id')
    password=request.data.get('password')

    if not id :
        return Response({'error':'advisor_id is required'},status=400)
    
    advisor=Users.objects.filter(advisor_id=id)
    if advisor:
        if advisor.check_password(password):
            res={'message':'Login successful',
                          'class_id':advisor.class_id,
                          'advisor_id':advisor.advisor_id, 
                          'advisor_name': advisor.advisor_name}
            tokens=get_token(advisor)
            res.update(tokens)
            return Response(res)