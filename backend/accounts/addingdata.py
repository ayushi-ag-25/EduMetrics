#later use this analyis engibe @api_view(['POST'])

from .models import AdvisorAuth
from rest_framework.response import Response

def sync(request):
    advisor_id = request.data.get('advisor_id')
    password   = request.data.get('password')

    if not AdvisorAuth.objects.filter(advisor_id=advisor_id).exists():
        client = Advisor.objects.using('client_db').get(advisor_id=advisor_id)
        if client.password == password:
            auth = AdvisorAuth(advisor_id=advisor_id)
            auth.set_password(password)  # hashes
            auth.save()

    return Response({'message': 'synced'})