from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import User

AGE_MAJORITE = 18


class Profil(models.Model):
    TYPE_PROFIL_CHOICES = [
        ('eleve', _('Élève / futur bachelier')),
        ('contributeur', _('Contributeur')),
    ]
    # Badges vérifiés : attribués uniquement par un administrateur (jamais par l'élève lui-même)
    BADGES = [
        ('contributeur', _('Contributeur vérifié')),
        ('ambassadeur', _('Ambassadeur')),
        ('conseiller', _("Conseiller d'orientation")),
    ]
    LANGUES = [('fr', 'Français'), ('en', 'English')]
    SOUS_SYSTEMES = [
        ('francophone', _('Francophone (Baccalauréat)')),
        ('anglophone', _('Anglophone (GCE)')),
    ]
    # Séries du Baccalauréat (sous-système francophone)
    SERIES_BAC = [
        ('C', _('Bac C (Maths-Physique-Chimie)')),
        ('D', _('Bac D (Maths-Physique-SVT)')),
        ('A4', _('Bac A4 (Littéraire)')),
        ('B', _('Bac B (Économie)')),
        ('F', _('Bac F (Technique industriel)')),
        ('TI', _('Bac TI (Technique)')),
    ]
    # Combinaisons du GCE Advanced Level (sous-système anglophone)
    SERIES_GCE = [
        ('gce_sciences', _('GCE A Level – Sciences')),
        ('gce_arts', _('GCE A Level – Arts')),
        ('gce_commercial', _('GCE A Level – Commercial')),
        ('gce_technique', _('GCE A Level – Technical')),
    ]
    SERIE_BAC_CHOICES = SERIES_BAC + SERIES_GCE + [('autre', _('Autre / En cours de détermination'))]

    utilisateur = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profil')
    type_profil = models.CharField(max_length=20, choices=TYPE_PROFIL_CHOICES, default='eleve')
    langue = models.CharField(max_length=2, choices=LANGUES, default='fr')
    sous_systeme = models.CharField(max_length=12, choices=SOUS_SYSTEMES, blank=True)
    serie_bac = models.CharField(max_length=20, choices=SERIE_BAC_CHOICES, blank=True)
    centres_interet = models.CharField(max_length=255, blank=True, help_text="Séparés par des virgules")
    region = models.CharField(max_length=100, blank=True)
    projet_etudes = models.CharField(max_length=255, blank=True, help_text="Ce que l'élève aimerait faire après le bac")
    ecole_souhaitee = models.CharField(max_length=255, blank=True, help_text="École où l'élève aimerait poursuivre ses études")
    date_creation = models.DateTimeField(auto_now_add=True)
    # Passe à True quand l'élève a terminé (ou passé) l'accueil progressif après l'inscription
    accueil_termine = models.BooleanField(default=False)
    ecoles_favorites = models.ManyToManyField('etablissements.Etablissement', blank=True, related_name='fans')
    badge = models.CharField(max_length=20, choices=BADGES, blank=True,
                             help_text="Badge vérifié affiché dans la communauté. Attribué par un administrateur après vérification.")
    # Protection des mineurs : les messages privés entre adultes et mineurs sont limités
    annee_naissance = models.PositiveSmallIntegerField(null=True, blank=True)
    # Acceptation des conditions d'utilisation et de la politique de confidentialité
    date_consentement = models.DateTimeField(null=True, blank=True)

    REGIONS = [
        'Adamaoua', 'Centre', 'Est', 'Extrême-Nord', 'Littoral',
        'Nord', 'Nord-Ouest', 'Ouest', 'Sud', 'Sud-Ouest',
    ]
    # Nom affiché de chaque région (en anglais : Far North, North-West...)
    NOMS_REGIONS = {
        'Adamaoua': _('Adamaoua'), 'Centre': _('Centre'), 'Est': _('Est'), 'Extrême-Nord': _('Extrême-Nord'),
        'Littoral': _('Littoral'), 'Nord': _('Nord'), 'Nord-Ouest': _('Nord-Ouest'), 'Ouest': _('Ouest'),
        'Sud': _('Sud'), 'Sud-Ouest': _('Sud-Ouest'),
    }

    def __str__(self):
        return f"Profil de {self.utilisateur.username}"

    def progression(self):
        """Pourcentage du profil rempli (série, centres d'intérêt, région, projet d'études)."""
        champs = [self.serie_bac, self.centres_interet, self.region, self.projet_etudes or self.ecole_souhaitee]
        return round(100 * sum(1 for c in champs if c) / len(champs))

    def est_majeur(self):
        """True si l'élève a 18 ans cette année ou plus. Âge inconnu : considéré comme mineur, par prudence."""
        return bool(self.annee_naissance) and timezone.now().year - self.annee_naissance >= AGE_MAJORITE

    @staticmethod
    def annees_de_naissance():
        """Années proposées dans le formulaire : de 10 à 70 ans."""
        annee = timezone.now().year
        return list(range(annee - 10, annee - 71, -1))
