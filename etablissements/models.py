from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

class Etablissement(models.Model):
    nom = models.CharField(max_length=255)
    type_etablissements = models.CharField(max_length=100)
    adresse = models.CharField(max_length=255, blank=True)
    localisation = models.PointField(srid=4326)
    ville = models.CharField(max_length=100, blank=True)
    statut = models.CharField(max_length=10, choices=[('public', _('Public')), ('prive', _('Privé'))], blank=True)
    site_web = models.URLField(blank=True)
    filieres = models.ManyToManyField('orientation.Filiere', blank=True, related_name='etablissements')
    # Informations pour le comparateur (facultatives)
    admission = models.CharField(max_length=20, blank=True, choices=[
        ('concours', _('Sur concours')), ('dossier', _('Sur étude de dossier')), ('libre', _('Inscription directe')),
    ])
    frais_annuels = models.PositiveIntegerField(null=True, blank=True, help_text="Frais de scolarité par an, en FCFA")
    capacite = models.PositiveIntegerField(null=True, blank=True, help_text="Nombre de places par an (environ)")
    description = models.TextField(blank=True)
    region = models.CharField(max_length=20, blank=True)
    # Position placée au chef-lieu de la région, ou estimée : à remplacer par la vraie position (relevé Kobo)
    position_approximative = models.BooleanField(default=False)
    source = models.CharField(max_length=255, blank=True, help_text="D'où vient l'information (document, relevé de terrain…)")
    a_verifier = models.BooleanField(default=False, help_text="Informations saisies automatiquement, à faire vérifier")

    def __str__(self):
        return self.nom

# Create your models here.
