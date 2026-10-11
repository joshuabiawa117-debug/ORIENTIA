from django.urls import path

from . import views

app_name = 'espace'

urlpatterns = [
    path('ma-filiere/', views.ma_filiere, name='filiere'),
    path('emploi-du-temps/', views.emploi_du_temps, name='emploi_du_temps'),
    path('suivi/', views.suivi, name='suivi'),
    path('emploi-du-temps/importer/', views.importer_emploi, name='importer_emploi'),
]
