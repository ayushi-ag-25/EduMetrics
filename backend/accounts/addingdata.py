#later use this analyis engibe @api_view(['POST'])

from .models import Users 
from analysis_engine.client_models import ClientAdvisor

def sync():
    for adv in ClientAdvisor.objects.all():
        advisor_name = adv.advisor_name
        advisor_id = adv.advisor_id
        class_id = adv.class_id

        if not Users.objects.filter(advisor_id=advisor_id).exists():
            user = Users(advisor_id=advisor_id, advisor_name=advisor_name, class_id=class_id)
            user.save()

    return {'message': 'synced'}s