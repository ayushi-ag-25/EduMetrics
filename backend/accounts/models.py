from django.db import models
from django.contrib.auth.models import AbstractBaseUser,BaseUserManager


class Users(AbstractBaseUser):
    advisor_id=models.CharField(max_length=20, primary_key=True)
    advisor_name = models.CharField(max_length=100)
    class_id=models.CharField(max_length=20,null=True)

    USERNAME_FIELD = 'advisor_id'
    objects = BaseUserManager()
    
    def __str__(self):
        return self.advisor_id
    