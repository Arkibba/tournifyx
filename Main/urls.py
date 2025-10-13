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
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
   path('', home, name='home'),
   path('login/', login, name='login'),
   path('home', home, name='home'),
   path('register/', register, name='register'),
   path('logout/', logout, name='logout'),
   path('admin/', admin.site.urls),
   path('host-tournament/', views.host_tournament, name='host_tournament'),
   path('join-tournament/', views.join_tournament, name='join_tournament'),
   path('tournament/<int:tournament_id>/', views.tournament_dashboard, name='tournament_dashboard'),
   #path('tournament/<int:tournament_id>/add-participant/', views.add_participant, name='add_participant'),
   path('user-tournaments/', views.user_tournaments, name='user_tournaments'),
   path('update-tournament/<int:tournament_id>/', views.update_tournament, name='update_tournament'),
   path('about/', views.about, name='about'),
   #path('payment/<int:tournament_id>/', views.payment, name='payment'),
   path('public-tournaments/', views.public_tournaments, name='public_tournaments'),
   path('public-tournaments-link/', views.public_tournaments, name='public_tournaments_link'),
   path('join-public-tournament/<int:tournament_id>/', views.join_public_tournament, name='join_public_tournament'),
   path('match/<int:match_id>/update/', views.update_match_result, name='update_match_result'),
   path('tournament/<int:tournament_id>/knockout-json/', views.tournament_knockout_json, name='tournament_knockout_json'),
   path('tournament/<int:tournament_id>/regenerate/', views.regenerate_fixtures, name='regenerate_fixtures'),
   path('profile/<str:username>/', views.profile_view, name='profile_view'),
   #path('payment/success/<int:tournament_id>/', views.payment_success, name='payment_success'),
   #path('payment/cancel/<int:tournament_id>/', views.payment_cancel, name='payment_cancel'),
   
]

if settings.DEBUG:
   urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
