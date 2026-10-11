from django.contrib import admin

from .models import Annale, Concours, Filiere, ResultatTest, UniteEnseignement


class UniteEnseignementInline(admin.TabularInline):
    model = UniteEnseignement
    extra = 0


class AnnaleInline(admin.TabularInline):
    model = Annale
    extra = 1


@admin.register(Filiere)
class FiliereAdmin(admin.ModelAdmin):
    list_display = ('nom', 'domaine', 'niveau', 'famille')
    list_filter = ('domaine', 'niveau')
    search_fields = ('nom', 'famille')
    prepopulated_fields = {'slug': ('nom',)}
    inlines = [UniteEnseignementInline]


@admin.register(Concours)
class ConcoursAdmin(admin.ModelAdmin):
    list_display = ('nom', 'annee', 'date_ouverture', 'date_cloture', 'date_epreuves')
    list_filter = ('annee',)
    search_fields = ('nom',)
    filter_horizontal = ('filieres',)
    readonly_fields = ('abonnes',)
    inlines = [AnnaleInline]


@admin.register(Annale)
class AnnaleAdmin(admin.ModelAdmin):
    list_display = ('concours', 'matiere', 'annee', 'corrige')
    list_filter = ('concours', 'annee')


@admin.register(ResultatTest)
class ResultatTestAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'date')
    readonly_fields = ('scores',)
