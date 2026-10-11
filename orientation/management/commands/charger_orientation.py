"""Charge les fiches filières (BTS officiels + filières des grandes écoles) et les concours.

Usage : python manage.py charger_orientation
La commande peut être relancée sans créer de doublons.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from etablissements.models import Etablissement
from orientation.import_bts import extraire
from orientation.models import Concours, Filiere, UniteEnseignement

PDF_BTS = Path(settings.BASE_DIR) / "documents" / "Offre de formation BTS-Vol 1.pdf"
SOURCE_BTS = "MINESUP — Offre de formation BTS, volume 1 (programmes officiels)"
SOURCE_INDICATIVE = "Information indicative — à vérifier auprès de l'établissement"

# Filières des grandes écoles : (nom, domaine, niveau, séries conseillées, sigles des écoles qui la proposent)
FILIERES_ECOLES = [
    ("Génie informatique", "informatique", "ingenieur", "C, D, TI", ["ENSP", "ENSPD", "IUT Douala", "IUT Bandjoun"]),
    ("Génie civil", "genie", "ingenieur", "C, D, F", ["ENSP", "ENSPD", "ENSTP"]),
    ("Génie électrique", "genie", "ingenieur", "C, D, F", ["ENSP", "ENSPD", "IUT Douala", "IUT Bandjoun"]),
    ("Génie mécanique", "genie", "ingenieur", "C, D, F", ["ENSP", "ENSPD", "IUT Douala"]),
    ("Télécommunications", "informatique", "ingenieur", "C, D", ["ENSP"]),
    ("Travaux publics", "genie", "ingenieur", "C, D, F", ["ENSTP"]),
    ("Gestion et commerce", "gestion", "licence", "B, C, D, G", ["ESSEC", "IUT Douala", "IUT Bandjoun"]),
    ("Journalisme et communication", "communication", "licence", "A, B, C, D", ["ESSTIC"]),
    ("Relations internationales et diplomatie", "droit_administration", "master", "A, B, C, D", ["IRIC"]),
    ("Administration publique et magistrature", "droit_administration", "master", "A, B, C, D", ["ENAM"]),
    ("Enseignement technique", "enseignement", "licence", "C, D, F, TI", ["ENSET"]),
]

# Concours d'entrée : (nom, sigle de l'école). Les dates sont à saisir dans l'administration chaque année.
CONCOURS = [
    ("Concours d'entrée à l'ENSP de Yaoundé", "ENSP"),
    ("Concours d'entrée à l'ENSP de Douala", "ENSPD"),
    ("Concours d'entrée à l'ENSTP", "ENSTP"),
    ("Concours d'entrée à l'ENAM", "ENAM"),
    ("Concours d'entrée à l'ESSTIC", "ESSTIC"),
    ("Concours d'entrée à l'IRIC", "IRIC"),
    ("Concours d'entrée à l'ESSEC de Douala", "ESSEC"),
    ("Concours d'entrée à l'ENSET de Douala", "ENSET"),
    ("Concours d'entrée à l'IUT de Douala", "IUT Douala"),
    ("Concours d'entrée à l'IUT de Bandjoun", "IUT Bandjoun"),
]

# Comment retrouver chaque école dans la base (morceau du nom)
SIGLES = {
    "ENSP": "(ENSP)", "ENSPD": "(ENSPD)", "ENSTP": "(ENSTP)", "ENAM": "(ENAM)", "ESSTIC": "(ESSTIC)",
    "IRIC": "(IRIC)", "ESSEC": "(ESSEC)", "ENSET": "(ENSET)", "IUT Douala": "Technologie de Douala",
    "IUT Bandjoun": "IUT Bandjoun",
}


class Command(BaseCommand):
    help = "Charge les fiches filières (BTS officiels + grandes écoles) et la liste des concours."

    def ecole(self, sigle):
        return Etablissement.objects.filter(nom__icontains=SIGLES[sigle]).first()

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. BTS officiels depuis le PDF du MINESUP
        fiches = extraire(PDF_BTS)
        for fiche in fiches:
            filiere, _ = Filiere.objects.update_or_create(
                slug=slugify(f"bts-{fiche['nom']}"),
                defaults=dict(
                    nom=fiche['nom'], domaine=fiche['domaine'], famille=fiche['famille'], niveau='bts',
                    duree="2 ans (4 semestres)", objectif=fiche['objectif'],
                    debouches="\n".join(fiche['debouches']), source=SOURCE_BTS,
                ),
            )
            filiere.unites.all().delete()
            UniteEnseignement.objects.bulk_create([UniteEnseignement(filiere=filiere, **u) for u in fiche['unites']])
        self.stdout.write(self.style.SUCCESS(f"{len(fiches)} fiches BTS importées depuis le PDF officiel."))

        # 2. Filières des grandes écoles (indicatives) et liens avec les établissements
        manquantes = set()
        for nom, domaine, niveau, series, sigles in FILIERES_ECOLES:
            filiere, _ = Filiere.objects.update_or_create(
                slug=slugify(nom),
                defaults=dict(nom=nom, domaine=domaine, niveau=niveau, series_admises=series, source=SOURCE_INDICATIVE),
            )
            for sigle in sigles:
                etab = self.ecole(sigle)
                if etab:
                    etab.filieres.add(filiere)
                else:
                    manquantes.add(sigle)
        self.stdout.write(self.style.SUCCESS(f"{len(FILIERES_ECOLES)} filières de grandes écoles chargées."))

        # 3. Concours (sans dates : à compléter dans l'administration)
        for nom, sigle in CONCOURS:
            etab = self.ecole(sigle)
            if etab:
                # Grandes écoles publiques, toutes accessibles sur concours
                Etablissement.objects.filter(pk=etab.pk).update(statut='public', admission='concours')
            concours, _ = Concours.objects.get_or_create(nom=nom, defaults=dict(etablissement=etab))
            if etab:
                if concours.etablissement_id is None:
                    concours.etablissement = etab
                    concours.save(update_fields=['etablissement'])
                concours.filieres.add(*etab.filieres.all())
            else:
                manquantes.add(sigle)
        self.stdout.write(self.style.SUCCESS(f"{len(CONCOURS)} concours chargés (dates à saisir dans /admin)."))

        if manquantes:
            self.stdout.write(self.style.WARNING(
                "Établissements introuvables : " + ", ".join(sorted(manquantes)) +
                ". Lance d'abord « python manage.py charger_etablissements » puis relance cette commande."
            ))
