import json
import os
from datetime import timedelta
from io import StringIO
from unittest import mock
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from etablissements.models import Etablissement
from interface.models import Profil

from .import_bts import extraire
from .models import Concours, Filiere, ResultatTest, UniteEnseignement
from .services import resume_pour_orientia


class DonneesMixin:

    def setUp(self):
        self.info = Filiere.objects.create(nom="Génie informatique", slug="genie-informatique", domaine="informatique", niveau="ingenieur")
        UniteEnseignement.objects.create(filiere=self.info, semestre=1, code="INF111", intitule="Algorithmique", credits=5, heures=75)
        # Une école à Douala, une à Yaoundé
        self.douala = Etablissement.objects.create(nom="IUT de Douala", type_etablissements="institut", ville="Douala",
                                                   latitude=4.0611, longitude=9.7043)
        self.yaounde = Etablissement.objects.create(nom="ENSP Yaoundé", type_etablissements="institut", ville="Yaoundé",
                                                    latitude=3.8700, longitude=11.5021)
        for e in (self.douala, self.yaounde):
            e.filieres.add(self.info)
        self.eleve = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        Profil.objects.filter(utilisateur=self.eleve).update(region="Littoral", centres_interet="Informatique", accueil_termine=True)


class FichesFilieresTests(DonneesMixin, TestCase):

    def test_catalogue_et_recherche_par_matiere(self):
        self.assertContains(self.client.get(reverse('orientation:filieres')), "Génie informatique")
        self.assertContains(self.client.get(reverse('orientation:filieres') + "?q=algorithmique"), "Génie informatique")
        self.assertNotContains(self.client.get(reverse('orientation:filieres') + "?q=zoologie"), "Génie informatique")

    def test_fiche_avec_matieres_et_ecoles(self):
        page = self.client.get(reverse('orientation:filiere', args=["genie-informatique"]))
        self.assertContains(page, "Algorithmique")
        self.assertContains(page, "IUT de Douala")


class EcolesProchesTests(DonneesMixin, TestCase):

    def test_tri_par_distance_depuis_la_region(self):
        self.client.force_login(self.eleve)  # région Littoral → Douala
        page = self.client.get(reverse('orientation:ecoles_proches'))
        noms = [e.nom for e in page.context['ecoles']]
        self.assertEqual(noms, ["IUT de Douala", "ENSP Yaoundé"])

    def test_tri_par_distance_depuis_la_position(self):
        page = self.client.get(reverse('orientation:ecoles_proches') + "?filiere=genie-informatique&lat=3.86&lon=11.51")
        self.assertEqual([e.nom for e in page.context['ecoles']], ["ENSP Yaoundé", "IUT de Douala"])

    def test_orientia_connait_les_ecoles_proches(self):
        texte = resume_pour_orientia(Profil.objects.get(utilisateur=self.eleve))
        self.assertIn("IUT de Douala", texte)
        self.assertLess(texte.index("IUT de Douala"), texte.index("ENSP Yaoundé"))


class ConcoursTests(DonneesMixin, TestCase):

    def test_calendrier_rappels_et_email(self):
        demain = timezone.localdate() + timedelta(days=1)
        c = Concours.objects.create(nom="Concours ENSP", etablissement=self.yaounde, date_cloture=demain)
        self.assertContains(self.client.get(reverse('orientation:concours')), "J-1")

        self.client.force_login(self.eleve)
        self.client.post(reverse('orientation:suivre_concours', args=[c.pk]))
        self.assertTrue(c.abonnes.filter(pk=self.eleve.pk).exists())

        call_command('envoyer_rappels_concours', stdout=StringIO())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("demain", mail.outbox[0].subject)

    def test_dates_non_publiees(self):
        Concours.objects.create(nom="Concours ENAM")
        self.assertContains(self.client.get(reverse('orientation:concours')), "Dates pas encore publiées")


class ImportBTSTests(TestCase):

    def test_programmes_officiels(self):
        fiches = extraire(Path(settings.BASE_DIR) / "documents" / "Offre de formation BTS-Vol 1.pdf")
        self.assertEqual(len(fiches), 13)
        for fiche in fiches:
            self.assertEqual(sum(u['credits'] for u in fiche['unites']), 120, fiche['nom'])
            self.assertTrue(fiche['debouches'], fiche['nom'])


class TestOrientationTests(DonneesMixin, TestCase):

    def reponses(self, index):
        from .test_orientation import QUESTIONS
        return {f"q{i}": index for i in range(len(QUESTIONS))}

    def test_scores_entre_0_et_100(self):
        from .test_orientation import QUESTIONS, calculer_scores
        for index in range(4):
            scores = calculer_scores([index] * len(QUESTIONS))
            self.assertTrue(all(0 <= s <= 100 for s in scores.values()))
            self.assertEqual(set(scores), {d for d, _ in Filiere.DOMAINES})

    def test_visiteur_voit_son_resultat_mais_pas_celui_des_autres(self):
        reponse = self.client.post(reverse('orientation:test'), self.reponses(1))
        resultat = ResultatTest.objects.get()
        self.assertRedirects(reponse, reverse('orientation:resultat_test', args=[resultat.pk]))
        self.assertContains(self.client.get(reponse.url), "Tes domaines")

        autre = self.client_class()
        self.assertEqual(autre.get(reponse.url).status_code, 302)

    def test_trop_peu_de_reponses(self):
        self.client.post(reverse('orientation:test'), {"q0": 0})
        self.assertFalse(ResultatTest.objects.exists())

    def test_le_resultat_oriente_les_conseils(self):
        self.client.force_login(self.eleve)
        self.client.post(reverse('orientation:test'), self.reponses(0))
        profil = Profil.objects.get(utilisateur=self.eleve)
        from .services import domaines_du_profil
        self.assertEqual(domaines_du_profil(profil)[:3], ResultatTest.objects.get().domaines_principaux(3))


class QuizTests(TestCase):

    def demander(self, matiere="Mathématiques"):
        return self.client.post(reverse('orientation:generer_quiz'), json.dumps({"matiere": matiere}),
                                content_type='application/json')

    def test_matiere_inconnue(self):
        self.assertEqual(self.demander("Astrologie").status_code, 400)

    def test_sans_cle_mistral(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            self.assertEqual(self.demander().status_code, 503)

    def test_quiz_genere_et_valide(self):
        brut = json.dumps({"questions": [
            {"question": "2 + 2 ?", "choix": ["3", "4", "5", "6"], "reponse": 1, "explication": "Facile."},
            {"question": "Question mal formée", "choix": ["a", "b"], "reponse": 0},
            {"question": "Racine de 9 ?", "choix": ["1", "2", "3", "4"], "reponse": 7},
        ]})
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}), mock.patch('orientation.quiz.generer_json', return_value=brut):
            reponse = self.demander()
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["questions"], [
            {"question": "2 + 2 ?", "choix": ["3", "4", "5", "6"], "reponse": 1, "explication": "Facile."},
        ])

    def test_page_annales(self):
        self.assertContains(self.client.get(reverse('orientation:annales')), "Quiz d'entraînement")


class ComparateurTests(DonneesMixin, TestCase):

    def test_comparer_deux_ecoles(self):
        url = reverse('orientation:comparateur') + f"?ecoles={self.douala.pk}&ecoles={self.yaounde.pk}"
        page = self.client.get(url)
        self.assertEqual([e.nom for e in page.context['ecoles']], ["IUT de Douala", "ENSP Yaoundé"])
        self.assertContains(page, "Génie informatique")

    def test_favoris_preremplissent_le_comparateur(self):
        self.client.force_login(self.eleve)
        self.client.post(reverse('orientation:favori', args=[self.yaounde.pk]))
        page = self.client.get(reverse('orientation:comparateur'))
        self.assertEqual([e.nom for e in page.context['ecoles']], ["ENSP Yaoundé"])
        self.assertContains(self.client.get(reverse('dashboard')), "ENSP Yaoundé")
        # Deuxième clic : retiré des favoris
        self.client.post(reverse('orientation:favori', args=[self.yaounde.pk]))
        self.assertFalse(Profil.objects.get(utilisateur=self.eleve).ecoles_favorites.exists())
