from django.contrib import admin

from .models import Profil


@admin.register(Profil)
class ProfilAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'type_profil', 'badge', 'serie_bac', 'region', 'annee_naissance',
                    'accueil_termine', 'date_creation')
    list_filter = ('badge', 'type_profil', 'serie_bac', 'region')
    list_editable = ('badge',)
    search_fields = ('utilisateur__username', 'utilisateur__email')
    readonly_fields = ('date_consentement',)
