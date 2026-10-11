"""Charge les établissements : grandes écoles publiques, universités d'État et IPES de la liste officielle du MINESUP.

Usage : python manage.py charger_etablissements
La commande peut être relancée sans risque : elle met à jour les établissements existants au lieu de les dupliquer,
et ne touche pas aux informations complétées à la main (frais, filières, site web...).
"""
from pathlib import Path

from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from etablissements.import_ipes import lire_pdf, ville_dans
from etablissements.models import Etablissement
from orientation.services import CHEFS_LIEUX

PDF_IPES = "Liste IPES par ordre alphabétique.pdf"

# (nom, ville, région, latitude, longitude)
GRANDES_ECOLES = [
    ("École Nationale Supérieure Polytechnique de Yaoundé (ENSP)", "Yaoundé", "Centre", 3.8700, 11.5021),
    ("École Nationale d'Administration et de Magistrature (ENAM)", "Yaoundé", "Centre", 3.8767, 11.5213),
    ("École Nationale Supérieure des Travaux Publics (ENSTP)", "Yaoundé", "Centre", 3.8880, 11.5030),
    ("École Supérieure des Sciences et Techniques de l'Information et de la Communication (ESSTIC)", "Yaoundé", "Centre", 3.8697, 11.5174),
    ("Institut des Relations Internationales du Cameroun (IRIC)", "Yaoundé", "Centre", 3.8814, 11.5085),
    ("École Nationale Supérieure Polytechnique de Douala (ENSPD)", "Douala", "Littoral", 4.0587, 9.7357),
    ("Institut Universitaire de Technologie de Douala (IUT)", "Douala", "Littoral", 4.0611, 9.7043),
    ("École Supérieure des Sciences Économiques et Commerciales (ESSEC)", "Douala", "Littoral", 4.0483, 9.7043),
    ("École Normale Supérieure de l'Enseignement Technique de Douala (ENSET)", "Douala", "Littoral", 4.0400, 9.7000),
    ("Institut Universitaire de Technologie Fotso Victor (IUT Bandjoun)", "Bandjoun", "Ouest", 5.3833, 10.4167),
]

# Universités d'État : positions approximatives des campus principaux, à vérifier
UNIVERSITES = [
    ("Université de Yaoundé I", "Yaoundé", "Centre", 3.8600, 11.4990),
    ("Université de Yaoundé II (Soa)", "Soa", "Centre", 3.9833, 11.5833),
    ("Université de Douala", "Douala", "Littoral", 4.0560, 9.7400),
    ("Université de Dschang", "Dschang", "Ouest", 5.4440, 10.0670),
    ("University of Buea", "Buea", "Sud-Ouest", 4.1550, 9.2870),
    ("University of Bamenda", "Bambili", "Nord-Ouest", 5.9960, 10.2500),
    ("Université de Ngaoundéré", "Ngaoundéré", "Adamaoua", 7.4220, 13.5450),
    ("Université de Maroua", "Maroua", "Extrême-Nord", 10.6100, 14.3250),
    ("Université d'Ebolowa", "Ebolowa", "Sud", 2.9150, 11.1500),
    ("Université de Bertoua", "Bertoua", "Est", 4.5800, 13.6800),
    ("Université de Garoua", "Garoua", "Nord", 9.3000, 13.4000),
]


def enregistrer(nom, region, valeurs, garder_position):
    """Crée ou met à jour un établissement repéré par son nom et sa région.

    garder_position : ne pas écraser une position déjà corrigée à la main (ou relevée sur le terrain).
    """
    existant = Etablissement.objects.filter(nom=nom, region__in=[region, ""]).first()
    if existant is None:
        Etablissement.objects.create(nom=nom, region=region, **valeurs)
        return True
    if garder_position and not existant.position_approximative:
        valeurs = {k: v for k, v in valeurs.items() if k not in ("localisation", "position_approximative")}
    for champ, valeur in valeurs.items():
        setattr(existant, champ, valeur)
    existant.region = region
    existant.save()
    return False


class Command(BaseCommand):
    help = "Charge les grandes écoles, les universités d'État et les IPES autorisés (liste du MINESUP)."

    @transaction.atomic
    def handle(self, *args, **options):
        crees = 0
        for nom, ville, region, lat, lon in GRANDES_ECOLES:
            crees += enregistrer(nom, region, {
                "type_etablissements": "grande_ecole", "statut": "public", "ville": ville, "adresse": ville,
                "admission": "concours", "localisation": Point(lon, lat, srid=4326), "source": "Saisie OrientIA",
            }, garder_position=True)

        for nom, ville, region, lat, lon in UNIVERSITES:
            crees += enregistrer(nom, region, {
                "type_etablissements": "universite", "statut": "public", "ville": ville, "adresse": ville,
                "localisation": Point(lon, lat, srid=4326), "position_approximative": True, "a_verifier": True,
                "source": "Universités d'État du Cameroun (saisie OrientIA, à vérifier)",
            }, garder_position=True)

        instituts = lire_pdf(Path(settings.BASE_DIR) / "documents" / PDF_IPES)
        for region, nom in instituts:
            ville = ville_dans(nom)
            if ville:
                nom_ville, lat, lon = ville
            else:
                nom_ville, lat, lon = CHEFS_LIEUX[region]
            crees += enregistrer(nom, region, {
                "type_etablissements": "ipes", "statut": "prive", "ville": nom_ville if ville else "",
                "adresse": nom_ville if ville else f"Région {region}",
                "localisation": Point(lon, lat, srid=4326), "position_approximative": True, "a_verifier": True,
                "source": "Liste des IPES autorisés (MINESUP)",
            }, garder_position=True)

        total = len(GRANDES_ECOLES) + len(UNIVERSITES) + len(instituts)
        self.stdout.write(self.style.SUCCESS(
            f"{total} établissements traités ({crees} nouveaux) : {len(GRANDES_ECOLES)} grandes écoles, "
            f"{len(UNIVERSITES)} universités d'État, {len(instituts)} IPES. "
            f"Total dans la base : {Etablissement.objects.count()}."))
        self.stdout.write("Les positions des IPES et des universités sont approximatives (centre de la ville ou chef-lieu "
                          "de région) : elles sont marquées « à vérifier » dans l'administration.")
