"""
URL configuration for EduMetrics backend.

Base URLs:
  /api/analysis/  — all analysis engine endpoints (preferred)
  /api/login/     — JWT login
  /api/logout/    — JWT logout
  /health/        — Railway / Render health-check
"""

from django.contrib import admin
from django.urls import path, include
from accounts.views import login
from rest_framework_simplejwt.views import TokenBlacklistView, TokenRefreshView
from analysis_engine.views import health

urlpatterns = [
    path('admin/', admin.site.urls),

    # Analysis engine 
    path('api/analysis/', include('analysis_engine.urls')),

    # Auth
    path('api/login/', login, name='login'),
    path('api/logout/', TokenBlacklistView.as_view(), name='logout'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

]
