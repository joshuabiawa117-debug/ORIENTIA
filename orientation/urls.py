from django.urls import path

from . import views

app_name = 'orientation'

urlpatterns = [
    path('filieres/', views.filieres, name='filieres'),
    path('filieres/<slug:slug>/', views.filiere, name='filiere'),
    path('concours/', views.concours, name='concours'),
    path('concours/<int:pk>/rappel/', views.suivre_concours, name='suivre_concours'),
    path('ecoles-pour-toi/', views.ecoles_pour_toi, name='ecoles_proches'),
    path('test-orientation/', views.test_orientation, name='test'),
    path('test-orientation/resultat/<int:pk>/', views.resultat_test, name='resultat_test'),
    path('annales/', views.annales, name='annales'),
    path('annales/quiz/', views.generer_quiz, name='generer_quiz'),
    path('comparer/', views.comparateur, name='comparateur'),
    path('ecoles/<int:pk>/favori/', views.basculer_favori, name='favori'),
]
