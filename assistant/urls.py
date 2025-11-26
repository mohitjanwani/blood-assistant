from django.urls import path
from . import views

urlpatterns = [
    path('', views.chat_page, name='home'), 
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/report/', views.report_api, name='report_api'),
    path('download-report/<int:profile_id>/', views.download_report, name='download_report'),
    path('register/', views.register_view, name='register'),
    path("get-response/", views.get_response, name="get_response"),
]
