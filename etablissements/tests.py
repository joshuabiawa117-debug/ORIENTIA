import os
from unittest import mock

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
            latitude=3.86, longitude=11.5, frais_annuels=50000)
        ensp.filieres.add(filiere)
        call_command("charger_etablissements", stdout=SILENCE)
        ensp.refresh_from_db()
        self.assertEqual((ensp.region, ensp.frais_annuels, ensp.filieres.count()), ("Centre", 50000, 1))
        self.assertAlmostEqual(ensp.longitude, 11.5)


@mock.patch.dict(os.environ, {"KOBO_API_TOKEN": "jeton", "KOBO_FORM_UID": "formulaire"})
class ImportKoboTests(TestCase):

    def test_import_avec_ville_region_et_filieres(self):
        filiere = Filiere.objects.create(nom="BTS Aquaculture", slug="bts-aquaculture", domaine="agropastoral")
        # Un institut déjà connu, placé au chef-lieu : le relevé de terrain donne sa vraie position
        Etablissement.objects.create(nom="Institut Agricole", type_etablissements="ipes", position_approximative=True,
                                     latitude=3.8, longitude=11.5)
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
        self.assertAlmostEqual(institut.latitude, 4.17)
        self.assertEqual(list(institut.filieres.all()), [filiere])
        self.assertFalse(Etablissement.objects.filter(nom="Sans position").exists())
        self.assertIn("formulaire", appel.call_args[0][0])


class DistancesTests(TestCase):

    def test_distance_yaounde_douala(self):
        from .geo import Position, distance_km
        # Environ 200 km à vol d'oiseau entre les deux villes
        self.assertAlmostEqual(distance_km(Position(3.848, 11.502), Position(4.051, 9.768)), 194, delta=5)
        self.assertEqual(distance_km(Position(4.0, 9.7), Position(4.0, 9.7)), 0)

    def test_tri_du_plus_proche_au_plus_loin(self):
        from .geo import Position, trier_par_distance
        loin = Etablissement.objects.create(nom="Garoua", type_etablissements="ipes", latitude=9.30, longitude=13.40)
        proche = Etablissement.objects.create(nom="Douala", type_etablissements="ipes", latitude=4.05, longitude=9.77)
        tries = trier_par_distance(Etablissement.objects.all(), Position(3.85, 11.50))
        self.assertEqual([e.nom for e in tries], [proche.nom, loin.nom])
        self.assertLess(tries[0].distance_km, tries[1].distance_km)


class StockageBlobTests(TestCase):
    """Annales sur Vercel Blob (le disque de Vercel est en lecture seule)."""

    def test_envoi_et_adresse_publique(self):
        from django.core.files.base import ContentFile
        from django.test import override_settings

        from config.stockage import VercelBlobStorage

        faux_client = mock.Mock()
        faux_client.put.return_value = mock.Mock(pathname="annales/sujet-AbC123.pdf")
        stockage = VercelBlobStorage()
        with override_settings(BLOB_URL_BASE="https://store.public.blob.vercel-storage.com"), \
                mock.patch.object(VercelBlobStorage, "client", return_value=faux_client):
            nom = stockage.save("annales/sujet.pdf", ContentFile(b"%PDF-1.4", name="sujet.pdf"))
            self.assertEqual(nom, "annales/sujet-AbC123.pdf")
            self.assertEqual(stockage.url(nom), "https://store.public.blob.vercel-storage.com/annales/sujet-AbC123.pdf")
        args, options = faux_client.put.call_args
        self.assertEqual((args[0], options["access"], options["add_random_suffix"]), ("annales/sujet.pdf", "public", True))

    def test_adresse_deduite_du_jeton(self):
        from django.test import override_settings

        from config.stockage import url_base_du_store
        with override_settings(BLOB_URL_BASE=""), mock.patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "vercel_blob_rw_AbCd1234_secret"}):
            self.assertEqual(url_base_du_store(), "https://abcd1234.public.blob.vercel-storage.com")
