"""Espace personnel de l'élève : gestion de filière, emploi du temps et suivi."""
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

JOURS = [
    (0, _('Lundi')), (1, _('Mardi')), (2, _('Mercredi')), (3, _('Jeudi')),
    (4, _('Vendredi')), (5, _('Samedi')), (6, _('Dimanche')),
]


class Parcours(models.Model):
    """Situation de l'élève : bachelier qui choisit sa voie, ou étudiant déjà inscrit dans une filière."""

    STATUTS = [
        ('bachelier', _('Bachelier / futur étudiant')),
        ('etudiant', _('Étudiant déjà inscrit')),
    ]

    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='parcours')
    statut = models.CharField(max_length=10, choices=STATUTS, default='bachelier')
    # Étudiant inscrit
    filiere = models.ForeignKey('orientation.Filiere', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    etablissement = models.ForeignKey('etablissements.Etablissement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    semestre = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(10)])

    def __str__(self):
        return f"Parcours de {self.utilisateur}"


class ChoixFiliere(models.Model):
    """Une filière visée par un bachelier (vœu 1, 2 ou 3) et l'avancement de ses démarches."""

    ETAPES = [
        ('renseigne', _('Je me renseigne')),
        ('dossier', _('Dossier en préparation')),
        ('candidature', _('Candidature déposée')),
        ('concours', _('Concours passé')),
        ('admis', _('Admis·e')),
        ('refuse', _('Non retenu·e')),
    ]

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='choix_filieres')
    rang = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(3)])
    filiere = models.ForeignKey('orientation.Filiere', on_delete=models.CASCADE, related_name='+')
    etablissement = models.ForeignKey('etablissements.Etablissement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    etape = models.CharField(max_length=12, choices=ETAPES, default='renseigne')
    remarque = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['rang']
        constraints = [models.UniqueConstraint(fields=['utilisateur', 'rang'], name='un_choix_par_rang')]

    def avancement(self):
        """Pourcentage d'avancement des démarches (pour la barre de progression)."""
        ordre = ['renseigne', 'dossier', 'candidature', 'concours', 'admis']
        if self.etape == 'refuse':
            return 100
        return round(100 * (ordre.index(self.etape) + 1) / len(ordre))


class AvancementMatiere(models.Model):
    """Où en est l'étudiant dans une matière de sa filière."""

    STATUTS = [
        ('a_faire', _('À commencer')),
        ('en_cours', _('En cours')),
        ('validee', _('Validée')),
    ]

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='avancements')
    unite = models.ForeignKey('orientation.UniteEnseignement', on_delete=models.CASCADE, related_name='+')
    statut = models.CharField(max_length=10, choices=STATUTS, default='a_faire')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['utilisateur', 'unite'], name='un_avancement_par_matiere')]


class Note(models.Model):
    """Une note obtenue (sur 20) dans une matière."""

    TYPES = [
        ('devoir', _('Devoir / contrôle continu')),
        ('examen', _('Examen')),
        ('tp', _('TP')),
    ]

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notes')
    matiere = models.CharField(max_length=255)
    unite = models.ForeignKey('orientation.UniteEnseignement', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    semestre = models.PositiveSmallIntegerField(default=1)
    valeur = models.DecimalField(max_digits=4, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(20)])
    coefficient = models.DecimalField(max_digits=4, decimal_places=1, default=1, validators=[MinValueValidator(0.1)])
    type_note = models.CharField(max_length=10, choices=TYPES, default='devoir')
    date = models.DateField()

    class Meta:
        ordering = ['-date', '-pk']


class Tache(models.Model):
    """Un objectif ou une tâche à faire, avec une échéance facultative."""

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='taches')
    titre = models.CharField(max_length=200)
    echeance = models.DateField(null=True, blank=True)
    faite = models.BooleanField(default=False)
    date_creation = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['faite', models.F('echeance').asc(nulls_last=True), '-date_creation']


class Creneau(models.Model):
    """Un créneau de la semaine : un cours fixe (emploi du temps de l'école) ou une disponibilité pour réviser."""

    TYPES = [
        ('cours', _('Cours')),
        ('dispo', _('Disponibilité')),
    ]

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='creneaux')
    type_creneau = models.CharField(max_length=5, choices=TYPES)
    jour = models.PositiveSmallIntegerField(choices=JOURS)
    debut = models.TimeField()
    fin = models.TimeField()
    intitule = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ['jour', 'debut']


class SeanceRevision(models.Model):
    """Une séance de révision de l'emploi du temps choisi par l'élève parmi les propositions."""

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='seances')
    jour = models.PositiveSmallIntegerField(choices=JOURS)
    debut = models.TimeField()
    fin = models.TimeField()
    matiere = models.CharField(max_length=255)
    formule = models.CharField(max_length=20)

    class Meta:
        ordering = ['jour', 'debut']
