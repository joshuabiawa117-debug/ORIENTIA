from django.contrib import admin

from .models import ChoixFiliere, Creneau, Note, Parcours, SeanceRevision, Tache

admin.site.register([Parcours, ChoixFiliere, Note, Tache, Creneau, SeanceRevision])
