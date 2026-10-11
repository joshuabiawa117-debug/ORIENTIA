from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Sujet(models.Model):
    """Une question posée par un élève à la communauté, rattachée à une filière et/ou une école."""

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sujets')
    titre = models.CharField(max_length=200)
    contenu = models.TextField()
    filiere = models.ForeignKey('orientation.Filiere', on_delete=models.SET_NULL, null=True, blank=True, related_name='sujets')
    etablissement = models.ForeignKey('etablissements.Etablissement', on_delete=models.SET_NULL, null=True, blank=True, related_name='sujets')
    date_creation = models.DateTimeField(auto_now_add=True)
    # Masqué automatiquement après plusieurs signalements, ou par l'équipe de modération
    masque = models.BooleanField(default=False)

    class Meta:
        ordering = ['-date_creation']

    def __str__(self):
        return self.titre

    def est_resolu(self):
        return self.reponses.filter(meilleure=True).exists()


class Reponse(models.Model):
    sujet = models.ForeignKey(Sujet, on_delete=models.CASCADE, related_name='reponses')
    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reponses')
    contenu = models.TextField()
    date_creation = models.DateTimeField(auto_now_add=True)
    meilleure = models.BooleanField(default=False, help_text="Choisie comme meilleure réponse par l'auteur de la question")
    votes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='reponses_aimees')
    masque = models.BooleanField(default=False)

    class Meta:
        ordering = ['-meilleure', 'date_creation']
        verbose_name = 'réponse'

    def __str__(self):
        return f"Réponse de {self.auteur} à « {self.sujet} »"


class MessagePrive(models.Model):
    """Un message privé envoyé à un membre précis de la communauté."""

    expediteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages_envoyes')
    destinataire = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='messages_recus')
    contenu = models.TextField(max_length=3000)
    date = models.DateTimeField(auto_now_add=True)
    lu = models.BooleanField(default=False)

    class Meta:
        ordering = ['date']
        verbose_name = 'message privé'
        verbose_name_plural = 'messages privés'

    def __str__(self):
        return f"{self.expediteur} → {self.destinataire} ({self.date:%d/%m %H:%M})"


# ---------- Modération ----------

# Nombre de signalements (par des membres différents) à partir duquel un contenu est masqué en attendant la vérification
SEUIL_MASQUAGE = 3


class Signalement(models.Model):
    """Un membre signale une question, une réponse, un message privé ou un membre à l'équipe de modération."""
    MOTIFS = [
        ('harcelement', _('Harcèlement ou insultes')),
        ('arnaque', _("Arnaque ou demande d'argent")),
        ('inapproprie', _('Contenu sexuel ou inapproprié')),
        ('mineur', _("Comportement inquiétant envers un mineur")),
        ('faux', _('Fausse information')),
        ('spam', _('Publicité ou spam')),
        ('autre', _('Autre')),
    ]

    auteur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='signalements_faits')
    membre_signale = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='signalements_recus')
    sujet = models.ForeignKey(Sujet, on_delete=models.CASCADE, null=True, blank=True, related_name='signalements')
    reponse = models.ForeignKey(Reponse, on_delete=models.CASCADE, null=True, blank=True, related_name='signalements')
    message = models.ForeignKey(MessagePrive, on_delete=models.CASCADE, null=True, blank=True, related_name='signalements')
    motif = models.CharField(max_length=20, choices=MOTIFS)
    details = models.TextField(blank=True, max_length=1000)
    date = models.DateTimeField(auto_now_add=True)
    traite = models.BooleanField(default=False, help_text="Coché quand l'équipe a examiné le signalement")
    note_moderation = models.TextField(blank=True, help_text="Décision prise (visible seulement par l'équipe)")

    class Meta:
        ordering = ['traite', '-date']

    def __str__(self):
        return f"{self.get_motif_display()} — {self.membre_signale} (par {self.auteur})"

    def contenu_signale(self):
        objet = self.sujet or self.reponse or self.message
        if objet is None:
            return ""
        return getattr(objet, 'titre', None) or objet.contenu


class Blocage(models.Model):
    """Un membre bloqué ne peut plus écrire en privé à celui qui l'a bloqué (et inversement)."""
    bloqueur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='blocages')
    bloque = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bloque_par')
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['bloqueur', 'bloque'], name='blocage_unique')]

    def __str__(self):
        return f"{self.bloqueur} a bloqué {self.bloque}"
