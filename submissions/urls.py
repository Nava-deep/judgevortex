from django.urls import path
from django.contrib.auth import views as auth_views
from .views import *

urlpatterns = [
    path('', landing, name='landing'),
    path('dashboard/', slist, name='list'),
    path('submit/', create, name='create'),
    path('submission/<uuid:pk>/', detail, name='detail'),
    path('register/', register, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='submissions/auth/login.html',redirect_authenticated_user=True), name='login'),
    path('submission/<uuid:pk>/delete/', delete, name='delete'),
    path('logout/', auth_views.LogoutView.as_view(next_page='landing'), name='logout'),
]