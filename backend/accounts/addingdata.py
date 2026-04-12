'''
this thing is not affecting calibrate() at all ,it just reads advisors table 
keep it inside calibrate ,separate from it in apps.py doesnt matter
'''

#later use this analyis engibe @api_view(['POST'])

from .models import Users 
from analysis_engine.client_models import ClientAdvisor

def sync():
    for adv in ClientAdvisor.objects.all():
        advisor_name = adv.name
        advisor_id = adv.advisor_id
        class_id = adv.class_id

        if not Users.objects.filter(advisor_id=advisor_id).exists():
            user = Users(advisor_id=advisor_id, advisor_name=advisor_name, class_id=class_id)
            user.save()
    print('advisor details synced')
    return {'message': 'synced'}

