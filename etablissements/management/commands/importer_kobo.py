"""Importe les établissements relevés sur le terrain avec KoboToolbox.

Usage : python manage.py importer_kobo
Réglages dans config/.env : KOBO_API_TOKEN (clé API Kobo) et KOBO_FORM_UID (identifiant du formulaire).

Champs lus dans chaque relevé (noms des questions du formulaire Kobo) :
  Obligatoires : Nom_de_l_etablissement, la position GPS (_geolocation)
  Facultatifs  : Type_d_etablissement, Adresse, Ville, Region, Statut (public / prive), Site_web,
                 Filieres (choix multiple : identifiants des filières OrientIA séparés par des espaces,
                 ex. « bts-aquaculture bts-genie-rural »)
La position relevée sur place remplace la position approximative d'un établissement déjà connu.
"""
import os

import requests
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError

from etablissements.models import Etablissement
from interface.models import Profil
from orientation.models import Filiere

URL_KOBO = "https://kf.kobotoolbox.org/api/v2/assets/{uid}/data/"


def texte(releve, champ):
    return str(releve.get(champ) or "").strip()


class Command(BaseCommand):
    help = "Importe les établissements relevés sur le terrain avec KoboToolbox."

    def handle(self, *args, **options):
        jeton, formulaire = os.getenv("KOBO_API_TOKEN"), os.getenv("KOBO_FORM_UID")
        if not jeton or not formulaire:
            raise CommandError("Renseigne KOBO_API_TOKEN et KOBO_FORM_UID dans config/.env.")

        reponse = requests.get(URL_KOBO.format(uid=formulaire), headers={"Authorization": f"Token {jeton}"}, timeout=30)
        reponse.raise_for_status()
        releves = reponse.json().get("results", [])
        self.stdout.write(f"{len(releves)} relevé(s) trouvé(s).")

        filieres = {f.slug: f for f in Filiere.objects.all()}
        importes = 0
        for releve in releves:
            nom = texte(releve, "Nom_de_l_etablissement")
            gps = releve.get("_geolocation") or [None, None]  # format Kobo : [latitude, longitude]
            if not nom or gps[0] is None or gps[1] is None:
                self.stdout.write(self.style.WARNING(f"Relevé ignoré (nom ou position GPS manquant) : {nom or '?'}"))
                continue

            valeurs = {
                "localisation": Point(float(gps[1]), float(gps[0]), srid=4326),  # Point(longitude, latitude)
                "position_approximative": False,
                "source": "Relevé de terrain KoboToolbox",
            }
            for champ_kobo, champ in (("Type_d_etablissement", "type_etablissements"), ("Adresse", "adresse"),
                                      ("Ville", "ville"), ("Site_web", "site_web")):
                if texte(releve, champ_kobo):
                    valeurs[champ] = texte(releve, champ_kobo)
            if texte(releve, "Region") in Profil.REGIONS:
                valeurs["region"] = texte(releve, "Region")
            if texte(releve, "Statut") in ("public", "prive"):
                valeurs["statut"] = texte(releve, "Statut")

            etablissement = Etablissement.objects.filter(nom=nom).first()
            cree = etablissement is None
            if cree:
                etablissement = Etablissement(nom=nom, type_etablissements="institut")
            for champ, valeur in valeurs.items():
                setattr(etablissement, champ, valeur)
            etablissement.save()

            slugs = texte(releve, "Filieres").split()
            inconnus = [s for s in slugs if s not in filieres]
            etablissement.filieres.add(*[filieres[s] for s in slugs if s in filieres])
            if inconnus:
                self.stdout.write(self.style.WARNING(f"  {nom} : filières inconnues ignorées : {', '.join(inconnus)}"))
            importes += 1
            self.stdout.write(f"{nom} : {'créé' if cree else 'mis à jour'}.")

        self.stdout.write(self.style.SUCCESS(f"{importes} établissement(s) importé(s) depuis KoboToolbox."))
