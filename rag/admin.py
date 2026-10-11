from django.contrib import admin

from .models import EchangeChat


@admin.register(EchangeChat)
class EchangeChatAdmin(admin.ModelAdmin):
    """Relire les réponses d'OrientIA : filtrer sur « 👎 Pas utile » pour trouver celles à améliorer."""
    list_display = ('date', 'question_courte', 'avis', 'utilisateur', 'langue', 'nom_document')
    list_filter = ('avis', 'langue', 'date')
    search_fields = ('question', 'reponse')
    readonly_fields = ('conversation', 'utilisateur', 'cle_session', 'question', 'reponse', 'sources',
                       'nom_document', 'langue', 'avis', 'date')
    date_hierarchy = 'date'

    @admin.display(description='Question')
    def question_courte(self, echange):
        return echange.question[:90]

    def has_add_permission(self, request):
        return False
