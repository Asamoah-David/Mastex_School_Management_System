from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('dashboard/', views.audit_dashboard, name='dashboard'),
    path('log/<int:pk>/', views.audit_log_detail, name='log_detail'),
    path('run-prune/', views.run_audit_prune, name='run_prune'),
]
