from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _g
from django.utils.translation import gettext_lazy as _


class Filiere(models.Model):
    """Une formation (ex. BTS Agroéquipement, Génie informatique) avec son programme."""

    DOMAINES = [
        ('agropastoral', _('Agropastoral')),
        ('eau_environnement', _('Eau et environnement')),
        ('informatique', _('Informatique et numérique')),
        ('genie', _('Génie et industrie')),
        ('sante', _('Santé')),
        ('gestion', _('Gestion, commerce et finance')),
        ('droit_administration', _('Droit et administration')),
        ('communication', _('Communication, langues et lettres')),
        ('enseignement', _('Enseignement')),
        ('sciences', _('Sciences fondamentales')),
    ]
    NIVEAUX = [
        ('bts', _('BTS (2 ans)')),
        ('licence', _('Licence (3 ans)')),
        ('ingenieur', _("Diplôme d'ingénieur (5 ans)")),
        ('master', _('Master (5 ans)')),
        ('autre', _('Autre')),
    ]

    nom = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    domaine = models.CharField(max_length=30, choices=DOMAINES)
    famille = models.CharField(max_length=150, blank=True, help_text="Ex. pour un BTS : « Agriculture et élevage »")
    niveau = models.CharField(max_length=20, choices=NIVEAUX, default='bts')
    duree = models.CharField(max_length=50, blank=True, help_text="Ex. 2 ans (4 semestres)")
    objectif = models.TextField(blank=True)
    debouches = models.TextField(blank=True, help_text="Un débouché par ligne")
    series_admises = models.CharField(max_length=100, blank=True, help_text="Séries de bac conseillées, séparées par des virgules (ex. C, D)")
    source = models.CharField(max_length=255, blank=True, help_text="D'où viennent ces informations")

    class Meta:
        ordering = ['domaine', 'nom']
        verbose_name = 'filière'

    def __str__(self):
        return f"{self.nom} ({self.get_niveau_display()})"

    def liste_debouches(self):
        return [d.strip(" -;.") for d in self.debouches.splitlines() if d.strip(" -;.")]

    def liste_series(self):
        return [s.strip() for s in self.series_admises.split(',') if s.strip()]


class UniteEnseignement(models.Model):
    """Une matière (UE) du programme officiel d'une filière, rangée par semestre."""

    CATEGORIES = [
        ('fondamentale', _('Fondamentale')),
        ('professionnelle', _('Professionnelle')),
        ('transversale', _('Transversale')),
    ]

    filiere = models.ForeignKey(Filiere, on_delete=models.CASCADE, related_name='unites')
    semestre = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=20, blank=True)
    intitule = models.CharField(max_length=255)
    categorie = models.CharField(max_length=20, choices=CATEGORIES, blank=True)
    credits = models.PositiveSmallIntegerField(null=True, blank=True)
    heures = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ['semestre', 'code']
        verbose_name = "unité d'enseignement"
        verbose_name_plural = "unités d'enseignement"

    def __str__(self):
        return f"S{self.semestre} · {self.intitule}"


def annee_courante():
    return timezone.localdate().year


class Concours(models.Model):
    """Un concours d'entrée (ENSP, ENAM...) avec ses dates clés."""

    nom = models.CharField(max_length=200)
    etablissement = models.ForeignKey('etablissements.Etablissement', on_delete=models.SET_NULL, null=True, blank=True, related_name='concours')
    filieres = models.ManyToManyField(Filiere, blank=True, related_name='concours')
    annee = models.PositiveSmallIntegerField(default=annee_courante)
    description = models.TextField(blank=True)
    conditions = models.TextField(blank=True, help_text="Conditions d'accès (diplôme, âge, séries...)")
    pieces_a_fournir = models.TextField(blank=True, help_text="Une pièce par ligne")
    date_ouverture = models.DateField(null=True, blank=True, help_text="Ouverture des inscriptions")
    date_cloture = models.DateField(null=True, blank=True, help_text="Clôture des inscriptions")
    date_epreuves = models.DateField(null=True, blank=True)
    lien_officiel = models.URLField(blank=True)
    abonnes = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='concours_suivis',
                                     help_text="Élèves qui veulent un rappel avant les échéances")

    class Meta:
        ordering = ['date_cloture', 'nom']
        verbose_name_plural = 'concours'

    def __str__(self):
        return f"{self.nom} {self.annee}"

    def liste_pieces(self):
        return [p.strip(" -;.") for p in self.pieces_a_fournir.splitlines() if p.strip(" -;.")]

    def prochaine_echeance(self):
        """(libellé, date, jours restants) de la prochaine date clé à venir, ou None."""
        aujourdhui = timezone.localdate()
        for libelle, date in [(_g("Ouverture des inscriptions"), self.date_ouverture),
                              (_g("Clôture des inscriptions"), self.date_cloture),
                              (_g("Épreuves"), self.date_epreuves)]:
            if date and date >= aujourdhui:
                return libelle, date, (date - aujourdhui).days
        return None

    def statut(self):
        """Statut affiché sur le calendrier."""
        aujourdhui = timezone.localdate()
        if not (self.date_ouverture or self.date_cloture or self.date_epreuves):
            return 'a_venir', _g("Dates pas encore publiées")
        if self.date_ouverture and aujourdhui < self.date_ouverture:
            return 'bientot', _g("Inscriptions bientôt ouvertes")
        if self.date_cloture and aujourdhui <= self.date_cloture:
            return 'ouvert', _g("Inscriptions ouvertes")
        if self.date_epreuves and aujourdhui <= self.date_epreuves:
            return 'epreuves', _g("Inscriptions closes, épreuves à venir")
        return 'termine', _g("Terminé")


class ResultatTest(models.Model):
    """Résultat du test d'orientation : un score par domaine."""

    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True,
                                    related_name='resultats_test')
    scores = models.JSONField(help_text="Score de chaque domaine en pourcentage, ex. {\"informatique\": 80}")
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "résultat du test d'orientation"
        verbose_name_plural = "résultats du test d'orientation"

    def __str__(self):
        return f"Test de {self.utilisateur or 'anonyme'} du {self.date:%d/%m/%Y}"

    def domaines_principaux(self, nombre=3):
        """Les domaines les mieux classés, du plus fort au moins fort."""
        return [d for d, _ in sorted(self.scores.items(), key=lambda x: -x[1])[:nombre]]


class Annale(models.Model):
    """Un sujet de concours des années passées (PDF), avec son corrigé éventuel."""

    concours = models.ForeignKey(Concours, on_delete=models.CASCADE, related_name='annales')
    matiere = models.CharField(max_length=100)
    annee = models.PositiveSmallIntegerField()
    sujet = models.FileField(upload_to='annales/')
    corrige = models.FileField(upload_to='annales/corriges/', blank=True)
    date_ajout = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-annee', 'matiere']

    def __str__(self):
        return f"{self.concours.nom} — {self.matiere} {self.annee}"
