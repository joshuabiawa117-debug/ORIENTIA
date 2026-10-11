from django.urls import path
from . import donnees, views

urlpatterns = [
    path('', views.accueil, name='accueil'),
    path('langue/', views.changer_langue, name='changer_langue'),
    path('chat/', views.chat, name='chat'),
    path('chat/historique/', views.historique_chat, name='historique_chat'),
    path('chat/historique/<uuid:conversation>/supprimer/', views.supprimer_conversation, name='supprimer_conversation'),
    path('api/chat/', views.api_chat, name='api_chat'),
    path('api/chat/avis/', views.api_avis, name='api_avis'),
    path('api/transcrire/', views.api_transcrire, name='api_transcrire'),
    path('etablissements/', views.carte, name='carte'),
    path('inscription/', views.inscription, name='inscription'),
    path('connexion/', views.connexion, name='connexion'),
    path('deconnexion/', views.deconnexion, name='deconnexion'),
    path('bienvenue/', views.bienvenue, name='bienvenue'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('confidentialite/', views.page_legale, {'page': 'confidentialite'}, name='confidentialite'),
    path('conditions/', views.page_legale, {'page': 'conditions'}, name='conditions'),
    path('mes-donnees/', donnees.mes_donnees, name='mes_donnees'),
    path('sw.js', views.service_worker, name='service_worker'),
    path('hors-ligne/', views.hors_ligne, name='hors_ligne'),
    path('taches/quotidiennes/', views.taches_quotidiennes, name='taches_quotidiennes'),
]