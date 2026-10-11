from django.contrib import admin, messages

from .models import Blocage, MessagePrive, Reponse, Signalement, Sujet


class ReponseInline(admin.TabularInline):
    model = Reponse
    extra = 0
    fields = ('auteur', 'contenu', 'meilleure', 'masque')


@admin.register(Sujet)
class SujetAdmin(admin.ModelAdmin):
    list_display = ('titre', 'auteur', 'filiere', 'etablissement', 'masque', 'date_creation')
    list_filter = ('masque', 'filiere__domaine')
    search_fields = ('titre', 'contenu')
    inlines = [ReponseInline]


@admin.register(MessagePrive)
class MessagePriveAdmin(admin.ModelAdmin):
    list_display = ('expediteur', 'destinataire', 'date', 'lu')
    search_fields = ('expediteur__username', 'destinataire__username', 'contenu')


@admin.register(Signalement)
class SignalementAdmin(admin.ModelAdmin):
    """File de modération : les signalements non traités apparaissent en premier."""
    list_display = ('date', 'motif', 'membre_signale', 'auteur', 'apercu', 'traite')
    list_filter = ('traite', 'motif')
    search_fields = ('membre_signale__username', 'auteur__username', 'details')
    readonly_fields = ('auteur', 'membre_signale', 'sujet', 'reponse', 'message', 'motif', 'details', 'date', 'apercu')
    fields = ('apercu', 'motif', 'details', 'membre_signale', 'auteur', 'sujet', 'reponse', 'message', 'date',
              'traite', 'note_moderation')
    actions = ['marquer_traite', 'masquer_contenu', 'retablir_contenu', 'desactiver_compte']

    @admin.display(description='Contenu signalé')
    def apercu(self, signalement):
        return signalement.contenu_signale()[:120] or f"(profil de {signalement.membre_signale})"

    @admin.action(description='Marquer comme traité')
    def marquer_traite(self, request, queryset):
        queryset.update(traite=True)

    @admin.action(description='Masquer la question / la réponse signalée')
    def masquer_contenu(self, request, queryset):
        for s in queryset:
            for objet in (s.sujet, s.reponse):
                if objet:
                    objet.masque = True
                    objet.save(update_fields=['masque'])
        queryset.update(traite=True)

    @admin.action(description='Rétablir le contenu (signalement non fondé)')
    def retablir_contenu(self, request, queryset):
        for s in queryset:
            for objet in (s.sujet, s.reponse):
                if objet:
                    objet.masque = False
                    objet.save(update_fields=['masque'])
        queryset.update(traite=True)

    @admin.action(description='Désactiver le compte du membre signalé')
    def desactiver_compte(self, request, queryset):
        comptes = {s.membre_signale for s in queryset if not s.membre_signale.is_staff}
        for compte in comptes:
            compte.is_active = False
            compte.save(update_fields=['is_active'])
        queryset.update(traite=True)
        self.message_user(request, f"{len(comptes)} compte(s) désactivé(s).", messages.WARNING)


@admin.register(Blocage)
class BlocageAdmin(admin.ModelAdmin):
    list_display = ('bloqueur', 'bloque', 'date')
    search_fields = ('bloqueur__username', 'bloque__username')
