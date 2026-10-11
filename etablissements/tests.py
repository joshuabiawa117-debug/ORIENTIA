import os
from unittest import mock

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import TestCase

from orientation.models import Filiere

from .import_ipes import lire_lignes, region_de, ville_dans
from .models import Etablissement

SILENCE = open(os.devnull, "w")


class LectureListeIpesTests(TestCase):

    def test_noms_sur_plusieurs_lignes_et_en_tetes_ignores(self):
        lignes = [
            "LISTE DES INSTITUTIONS PRIVEES D’ENSEIGNEMENT SUPERIEUR", "Région de l’Adamaoua",
            "1 Institut Supérieur des Sciences, de Technologie, de Management et Développement",
            "Durable (ISSTMADD)", "2 Sanda Institut Supérieur de Management (SISMA)",
            "REPUBLIQUE DU CAMEROUN", "Paix-Travail-Patrie", "------------", "2 ",
            "Région du Sud-ouest", "1 Higher Institute of Applied Medical Sciences Buea",
        ]
        self.assertEqual(lire_lignes(lignes), [
            ("Adamaoua", "Institut Supérieur des Sciences, de Technologie, de Management et Développement Durable (ISSTMADD)"),
            ("Adamaoua", "Sanda Institut Supérieur de Management (SISMA)"),
            ("Sud-Ouest", "Higher Institute of Applied Medical Sciences Buea"),
        ])

    def test_regions_et_villes(self):
        self.assertEqual(region_de(" de l’Extrême de Nord"), "Extrême-Nord")
        self.assertEqual(region_de(" Nord-Ouest"), "Nord-Ouest")
        self.assertEqual(region_de(" de l’EST"), "Est")
        self.assertEqual(ville_dans("Institut Supérieur de Yaoundé")[0], "Yaoundé")
        self.assertIsNone(ville_dans("Institut Saint Jean"))


class ChargementEtablissementsTests(TestCase):

    def test_chargement_complet_et_relance_sans_doublon(self):
        call_command("charger_etablissements", stdout=SILENCE)
        total = Etablissement.objects.count()
        self.assertGreater(Etablissement.objects.filter(type_etablissements="ipes").count(), 200)
        self.assertEqual(Etablissement.objects.filter(type_etablissements="universite").count(), 11)
        self.assertTrue(Etablissement.objects.filter(type_etablissements="ipes", position_approximative=True).exists())
        call_command("charger_etablissements", stdout=SILENCE)
        self.assertEqual(Etablissement.objects.count(), total)

    def test_ne_touche_pas_aux_informations_completees_a_la_main(self):
        filiere = Filiere.objects.create(nom="Génie logiciel", slug="genie-logiciel", domaine="informatique")
        ensp = Etablissement.objects.create(
            nom="École Nationale Supérieure Polytechnique de Yaoundé (ENSP)", type_etablissements="institut",
            localisation=Point(11.5, 3.86, srid=4326), frais_annuels=50000)
        ensp.filieres.add(filiere)
        call_command("charger_etablissements", stdout=SILENCE)
        ensp.refresh_from_db()
        self.assertEqual((ensp.region, ensp.frais_annuels, ensp.filieres.count()), ("Centre", 50000, 1))
        self.assertAlmostEqual(ensp.localisation.x, 11.5)


@mock.patch.dict(os.environ, {"KOBO_API_TOKEN": "jeton", "KOBO_FORM_UID": "formulaire"})
class ImportKoboTests(TestCase):

    def test_import_avec_ville_region_et_filieres(self):
        filiere = Filiere.objects.create(nom="BTS Aquaculture", slug="bts-aquaculture", domaine="agropastoral")
        # Un institut déjà connu, placé au chef-lieu : le relevé de terrain donne sa vraie position
        Etablissement.objects.create(nom="Institut Agricole", type_etablissements="ipes", position_approximative=True,
                                     localisation=Point(11.5, 3.8, srid=4326))
        releves = {"results": [
            {"Nom_de_l_etablissement": "Institut Agricole", "Ville": "Obala", "Region": "Centre", "Statut": "prive",
             "Filieres": "bts-aquaculture inconnue", "_geolocation": [4.17, 11.53]},
            {"Nom_de_l_etablissement": "Sans position", "_geolocation": [None, None]},
        ]}
        with mock.patch("requests.get") as appel:
            appel.return_value.json.return_value = releves
            call_command("importer_kobo", stdout=SILENCE)
        institut = Etablissement.objects.get(nom="Institut Agricole")
        self.assertEqual((institut.ville, institut.region, institut.statut), ("Obala", "Centre", "prive"))
        self.assertFalse(institut.position_approximative)
        self.assertAlmostEqual(institut.localisation.y, 4.17)
        self.assertEqual(list(institut.filieres.all()), [filiere])
        self.assertFalse(Etablissement.objects.filter(nom="Sans position").exists())
        self.assertIn("formulaire", appel.call_args[0][0])
