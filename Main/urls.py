"""
URL configuration for Main project.


The `urlpatterns` list routes URLs to views. For more information please see:
   https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
   1. Add an import:  from my_app import views
   2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
   1. Add an import:  from other_app.views import Home
   2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
   1. Import the include() function: from django.urls import include, path
   2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from tournifyx import views
from tournifyx.views import *


urlpatterns = [
   path('', login, name='login'),
   path('home', home, name='home'),
   path('register/', register, name='register'),
   path('logout/', logout, name='logout'),
   path('admin/', admin.site.urls),
   path('host-tournament/', views.host_tournament, name='host_tournament'),
   path('join-tournament/', views.join_tournament, name='join_tournament'),
   path('tournament-dashboard/<int:tournament_id>/', views.tournament_dashboard, name='tournament_dashboard'),
   path('user-tournaments/', views.user_tournaments, name='user_tournaments'),
   path('update-tournament/<int:tournament_id>/', views.update_tournament, name='update_tournament'),
   path('about/', views.about, name='about'),
   path('payment/<int:tournament_id>/', views.payment, name='payment'),
]
