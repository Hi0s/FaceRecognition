from django.urls import path

from . import views

app_name = 'checkin'

urlpatterns = [
    path('', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/<int:pk>/edit/', views.employee_edit, name='employee_edit'),
    path('employees/<int:pk>/delete/', views.employee_delete, name='employee_delete'),
    path('history/', views.history_view, name='history'),
    path('workdays/', views.workdays_view, name='workdays'),
    path('api/face-match/', views.face_match_api, name='face_match_api'),
]
