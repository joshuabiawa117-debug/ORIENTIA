from django.conf import settings
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models


class DocumentChunk(models.Model):
    source = models.CharField(max_length=255)  # nom du fichier PDF d'origine
    contenu = models.TextField()  # le texte du chunk
    # Index de recherche plein texte (français, insensible aux accents), rempli par « manage.py indexer_documents »
    recherche = SearchVectorField(null=True)

    class Meta:
        indexes = [GinIndex(fields=['recherche'])]

    def __str__(self):
        return f"{self.source} — {self.contenu[:50]}..."


class EchangeChat(models.Model):
    """Une question posée à OrientIA et sa réponse.

    Sert de mémoire à la conversation (questions de suivi), d'historique pour l'élève connecté,
    et permet de repérer les mauvaises réponses grâce aux avis 👍 / 👎.
    """
    AVIS = [(1, '👍 Utile'), (-1, '👎 Pas utile')]

    conversation = models.UUIDField(db_index=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='echanges_chat')
    # Visiteur sans compte : la conversation est rattachée à sa session
    cle_session = models.CharField(max_length=40, blank=True)
    question = models.TextField()
    reponse = models.TextField()
    sources = models.JSONField(default=list, blank=True)
    nom_document = models.CharField(max_length=255, blank=True, help_text="Fichier joint par l'élève, s'il y en a un")
    langue = models.CharField(max_length=5, blank=True)
    avis = models.SmallIntegerField(choices=AVIS, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date']
        verbose_name = 'échange avec OrientIA'
        verbose_name_plural = 'échanges avec OrientIA'

    def __str__(self):
        return self.question[:80]
