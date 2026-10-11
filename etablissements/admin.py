from django.contrib import admin

from .models import Etablissement


@admin.register(Etablissement)
class EtablissementAdmin(admin.ModelAdmin):
    list_display = ('nom', 'type_etablissements', 'ville', 'region', 'statut', 'admission', 'frais_annuels',
                    'position_approximative', 'a_verifier')
    list_filter = ('type_etablissements', 'statut', 'region', 'position_approximative', 'a_verifier')
    list_editable = ('a_verifier',)
    search_fields = ('nom', 'ville', 'adresse')
    filter_horizontal = ('filieres',)
