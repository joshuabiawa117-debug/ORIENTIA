from django.urls import path

from . import views

app_name = 'communaute'

urlpatterns = [
    path('', views.liste, name='liste'),
    path('nouvelle-question/', views.nouveau, name='nouveau'),
    path('<int:pk>/', views.detail, name='detail'),
    path('<int:pk>/repondre/', views.repondre, name='repondre'),
    path('reponse/<int:pk>/utile/', views.voter, name='voter'),
    path('reponse/<int:pk>/meilleure/', views.meilleure, name='meilleure'),
    path('membre/<str:username>/', views.membre, name='membre'),
    path('messages/', views.messagerie, name='messagerie'),
    path('messages/<str:username>/', views.conversation, name='conversation'),
    path('signaler/<str:type_contenu>/<int:pk>/', views.signaler, name='signaler'),
    path('membre/<str:username>/bloquer/', views.bloquer, name='bloquer'),
]
