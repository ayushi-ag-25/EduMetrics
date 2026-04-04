from dataclasses import fields

from rest_framework import serializers
from .models import weekly_flags,weekly_metrics

class weekly_flagSerializer(serializers.ModelSerializer):
    class Meta:
        model = weekly_flags
        fields = '__all__'

class performanceSerializer(serializers.ModelSerializer):
    def __init__(self,*args,**kwargs):
        fields=kwargs.pop('fields',None)
        super().__init__(*args,**kwargs)
        if fields:
            for f in set(self.fields) - set(fields):
                self.fields.pop(f)
    class Meta:
        model = weekly_metrics
        fields = ['student_id','academic_performance']