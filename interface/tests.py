import os
from datetime import date
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Profil


class ConnexionProgressiveTests(TestCase):

    def inscrire(self):
        return self.client.post(reverse('inscription'), {
            "email": "awa@exemple.com", "username": "awa", "password": "Orientation2026!", "consentement": "1",
        })

    def test_inscription_minimale_puis_accueil_progressif(self):
        reponse = self.inscrire()
        self.assertRedirects(reponse, reverse('bienvenue'))
        self.assertTrue(Profil.objects.filter(utilisateur__username="awa").exists())

    def test_dashboard_renvoie_vers_bienvenue_tant_que_non_termine(self):
        self.inscrire()
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('bienvenue'))

    def test_enregistrement_etape_par_etape(self):
        self.inscrire()
        reponse = self.client.post(reverse('bienvenue'), {"serie_bac": "C"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(reponse.json()["progression"], 25)
        reponse = self.client.post(reverse('bienvenue'), {"region": "Littoral", "centres_interet": "Informatique"},
                                   HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(reponse.json()["progression"], 75)
        reponse = self.client.post(reverse('bienvenue'), {"projet_etudes": "Devenir ingénieur·e", "ecole_souhaitee": "ENSP Yaoundé"},
                                   HTTP_X_REQUESTED_WITH="fetch")
        self.assertEqual(reponse.json()["progression"], 100)
        profil = Profil.objects.get(utilisateur__username="awa")
        self.assertEqual((profil.projet_etudes, profil.ecole_souhaitee), ("Devenir ingénieur·e", "ENSP Yaoundé"))

    def test_valeurs_invalides_ignorees(self):
        self.inscrire()
        self.client.post(reverse('bienvenue'), {"serie_bac": "ZZZ", "region": "Paris"}, HTTP_X_REQUESTED_WITH="fetch")
        profil = Profil.objects.get(utilisateur__username="awa")
        self.assertEqual((profil.serie_bac, profil.region), ("", ""))

    def test_je_finirai_plus_tard(self):
        self.inscrire()
        reponse = self.client.post(reverse('bienvenue'), {"terminer": "1"})
        self.assertRedirects(reponse, reverse('dashboard'))
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)

    def test_connexion_par_email_ou_pseudo(self):
        User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        for identifiant in ("awa", "AWA@exemple.com"):
            self.client.logout()
            reponse = self.client.post(reverse('connexion'), {"identifiant": identifiant, "password": "Orientation2026!"})
            self.assertEqual(reponse.status_code, 302, identifiant)

    def test_email_deja_utilise(self):
        User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        reponse = self.client.post(reverse('inscription'), {
            "email": "awa@exemple.com", "username": "autre", "password": "Orientation2026!",
        })
        self.assertContains(reponse, "Un compte existe déjà avec cet email")

    def test_bouton_google_seulement_si_configure(self):
        self.assertNotContains(self.client.get(reverse('connexion')), "Continuer avec Google")
        with mock.patch.dict(os.environ, {"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "y"}):
            reponse = self.client.get(reverse('connexion'))
        self.assertContains(reponse, "Continuer avec Google")
        self.assertContains(reponse, "/accounts/google/login/")

    def test_pages_publiques(self):
        for nom in ('accueil', 'chat', 'carte', 'connexion', 'inscription'):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 200, nom)

    def test_page_bienvenue_et_menu_connecte(self):
        self.inscrire()
        reponse = self.client.get(reverse('bienvenue') + "?etape=3")
        self.assertContains(reponse, "1/6")
        self.assertContains(reponse, "As-tu une idée d'école")
        self.assertContains(reponse, "Littoral")
        self.assertContains(reponse, "Se déconnecter")


class ApiChatTests(TestCase):

    def poser(self):
        return self.client.post(reverse('api_chat'), '{"question": "Quelles filières après un bac C ?"}',
                                content_type='application/json')

    def test_cle_mistral_manquante(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            reponse = self.poser()
        self.assertEqual(reponse.status_code, 503)
        self.assertIn("GROQ_API_KEY", reponse.json()["erreur"])

    def test_aucun_document_indexe(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}):
            reponse = self.poser()
        self.assertEqual(reponse.status_code, 503)
        self.assertIn("indexer_documents", reponse.json()["erreur"])



class BilingueTests(TestCase):
    """Site en anglais pour les élèves anglophones, mode sombre."""

    def setUp(self):
        self.eleve = User.objects.create_user("john", "john@example.com", "Orientation2026!")
        self.client.force_login(self.eleve)

    def test_bouton_langue_traduit_le_site_et_le_profil(self):
        self.client.post(reverse('changer_langue'), {"langue": "en", "suivant": reverse('accueil')})
        page = self.client.get(reverse('accueil'))
        self.assertContains(page, "Find your path after secondary school")
        self.assertContains(page, '<html lang="en">')
        self.assertEqual(Profil.objects.get(utilisateur=self.eleve).langue, "en")

        self.client.post(reverse('changer_langue'), {"langue": "fr", "suivant": reverse('accueil')})
        self.assertContains(self.client.get(reverse('accueil')), "Trouve ta voie après le bac")

    def test_redirection_externe_refusee(self):
        reponse = self.client.post(reverse('changer_langue'), {"langue": "en", "suivant": "https://pirate.example/"})
        self.assertEqual(reponse.url, reverse('accueil'))

    def test_eleve_anglophone_questions_suivantes_en_anglais_avec_le_gce(self):
        reponse = self.client.post(reverse('bienvenue'), {"sous_systeme": "anglophone"}, HTTP_X_REQUESTED_WITH="fetch")
        self.assertTrue(reponse.json()["recharger"])
        profil = Profil.objects.get(utilisateur=self.eleve)
        self.assertEqual((profil.sous_systeme, profil.langue), ("anglophone", "en"))

        page = self.client.get(reverse('bienvenue') + "?etape=3")
        self.assertContains(page, "What is your GCE A Level combination?")
        self.assertContains(page, "GCE A Level – Sciences")
        self.assertNotContains(page, "Bac C (Maths")

    def test_eleve_francophone_garde_les_series_du_bac(self):
        self.client.post(reverse('bienvenue'), {"sous_systeme": "francophone"}, HTTP_X_REQUESTED_WITH="fetch")
        page = self.client.get(reverse('bienvenue') + "?etape=3")
        self.assertContains(page, "Quelle est ta série de bac ?")
        self.assertContains(page, "Bac C (Maths-Physique-Chimie)")

    def test_la_connexion_retrouve_la_langue_du_profil(self):
        Profil.objects.filter(utilisateur=self.eleve).update(langue="en")
        self.client.logout()
        self.client.cookies.clear()
        reponse = self.client.post(reverse('connexion'), {"identifiant": "john", "password": "Orientation2026!"})
        self.assertEqual(reponse.cookies["django_language"].value, "en")

    def test_orientia_repond_en_anglais(self):
        from rag.assistant import generer_reponse
        with mock.patch('rag.assistant.generer_texte', return_value="ok") as appel:
            generer_reponse("Which schools?", [], None, langue="en")
        self.assertIn("anglais", appel.call_args[0][0])

    def test_bouton_mode_sombre_present(self):
        self.assertContains(self.client.get(reverse('accueil')), 'id="btnTheme"')


class RechercheDocumentsTests(TestCase):
    """Recherche plein texte dans les documents officiels (sans embeddings)."""

    def setUp(self):
        from django.contrib.postgres.search import SearchVector
        from rag.models import DocumentChunk
        DocumentChunk.objects.create(source="guide.pdf", contenu="Les écoles d'informatique forment des ingénieurs en génie logiciel.")
        DocumentChunk.objects.create(source="guide.pdf", contenu="La pisciculture et l'élevage sont enseignés en BTS agropastoral.")
        DocumentChunk.objects.update(recherche=SearchVector("contenu", config="french_unaccent"))

    def test_question_en_anglais_retrouve_le_passage_francais(self):
        from rag.assistant import rechercher_chunks_pertinents
        with mock.patch('rag.assistant.mots_cles_recherche', return_value=["informatique", "école", "génie logiciel"]):
            resultats = rechercher_chunks_pertinents("Which schools teach computer science?")
        self.assertIn("informatique", resultats[0].contenu)

    def test_sans_mots_cles_la_question_suffit(self):
        from rag.assistant import rechercher_chunks_pertinents
        with mock.patch('rag.assistant.mots_cles_recherche', side_effect=RuntimeError("API indisponible")):
            resultats = rechercher_chunks_pertinents("Quelles formations en élevage et pisciculture ?")
        self.assertIn("pisciculture", resultats[0].contenu)


class ChatFichiersEtVoixTests(TestCase):

    def setUp(self):
        from rag.models import DocumentChunk
        DocumentChunk.objects.create(source="guide.pdf", contenu="Texte officiel.")

    def test_question_avec_fichier_joint(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fichier = SimpleUploadedFile("releve.txt", "Maths : 15/20, Physique : 9/20".encode(), content_type="text/plain")
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}), \
                mock.patch('interface.views.rechercher_chunks_pertinents', return_value=[]), \
                mock.patch('rag.assistant.generer_texte', return_value="Bonne réponse") as appel:
            reponse = self.client.post(reverse('api_chat'), {"question": "Que penses-tu de mes notes ?", "fichier": fichier})
        self.assertEqual(reponse.json()["reponse"], "Bonne réponse")
        self.assertIn("Physique : 9/20", appel.call_args[0][0])

    def test_fichier_non_pris_en_charge(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fichier = SimpleUploadedFile("jeu.exe", b"MZ", content_type="application/octet-stream")
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}):
            reponse = self.client.post(reverse('api_chat'), {"question": "?", "fichier": fichier})
        self.assertEqual(reponse.status_code, 400)

    def test_transcription_vocale(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        audio = SimpleUploadedFile("voix.webm", b"a" * 2000, content_type="audio/webm")
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}), mock.patch('rag.ia.transcrire_audio', return_value="Quelles écoles à Douala ?"):
            reponse = self.client.post(reverse('api_transcrire'), {"audio": audio})
        self.assertEqual(reponse.json(), {"texte": "Quelles écoles à Douala ?"})


class ConfidentialiteEtComptesTests(TestCase):
    """Consentement, pages légales, export et suppression des données, mot de passe oublié."""

    def test_consentement_obligatoire_et_date_enregistree(self):
        reponse = self.client.post(reverse('inscription'), {"email": "awa@exemple.com", "username": "awa", "password": "Orientation2026!"})
        self.assertContains(reponse, "Accepte les conditions")
        self.assertFalse(User.objects.exists())
        self.client.post(reverse('inscription'), {"email": "awa@exemple.com", "username": "awa",
                                                  "password": "Orientation2026!", "consentement": "1"})
        self.assertIsNotNone(Profil.objects.get(utilisateur__username="awa").date_consentement)

    def test_pages_legales_en_francais_et_en_anglais(self):
        self.assertContains(self.client.get(reverse('confidentialite')), "Politique de confidentialité")
        self.assertContains(self.client.get(reverse('conditions')), "Conditions d'utilisation")
        self.client.post(reverse('changer_langue'), {"langue": "en", "suivant": "/"})
        self.assertContains(self.client.get(reverse('confidentialite')), "Privacy policy")
        self.assertContains(self.client.get(reverse('conditions')), "Terms of use")

    def test_export_de_mes_donnees(self):
        from espace.models import Note
        awa = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        Note.objects.create(utilisateur=awa, matiere="Maths", semestre=1, valeur=15, date=date(2026, 10, 1))
        self.client.force_login(awa)
        reponse = self.client.post(reverse('mes_donnees'), {"action": "telecharger"})
        self.assertIn("attachment", reponse["Content-Disposition"])
        donnees = reponse.json()
        self.assertEqual(donnees["compte"]["email"], "awa@exemple.com")
        self.assertEqual(donnees["notes"][0]["matiere"], "Maths")

    def test_suppression_du_compte_avec_confirmation(self):
        awa = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        self.client.force_login(awa)
        self.client.post(reverse('mes_donnees'), {"action": "supprimer", "confirmation": "SUPPRIMER", "password": "faux"})
        self.assertTrue(User.objects.filter(username="awa").exists())
        self.client.post(reverse('mes_donnees'), {"action": "supprimer", "confirmation": "supprimer", "password": "Orientation2026!"})
        self.assertFalse(User.objects.filter(username="awa").exists())

    def test_mot_de_passe_oublie_envoie_un_email(self):
        from django.core import mail
        User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        self.assertContains(self.client.get(reverse('connexion')), reverse('account_reset_password'))
        self.client.post(reverse('account_reset_password'), {"email": "awa@exemple.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("awa@exemple.com", mail.outbox[0].to)

    def test_annee_de_naissance_dans_l_accueil_progressif(self):
        from django.utils import timezone
        awa = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        self.client.force_login(awa)
        annee = timezone.now().year - 17
        self.client.post(reverse('bienvenue'), {"annee_naissance": str(annee)}, HTTP_X_REQUESTED_WITH="fetch")
        self.client.post(reverse('bienvenue'), {"annee_naissance": "1800"}, HTTP_X_REQUESTED_WITH="fetch")
        profil = Profil.objects.get(utilisateur=awa)
        self.assertEqual(profil.annee_naissance, annee)
        self.assertFalse(profil.est_majeur())


class HorsLigneEtCarteTests(TestCase):

    def test_service_worker_et_page_hors_ligne(self):
        reponse = self.client.get(reverse('service_worker'))
        self.assertEqual(reponse["Content-Type"], "application/javascript; charset=utf-8")
        self.assertEqual(reponse["Service-Worker-Allowed"], "/")
        self.assertContains(reponse, reverse('hors_ligne'))
        self.assertContains(self.client.get(reverse('hors_ligne')), "Pas de connexion")

    def test_carte_types_lisibles_et_positions_approximatives(self):
        from etablissements.models import Etablissement
        Etablissement.objects.create(nom="Institut X", type_etablissements="ipes", position_approximative=True,
                                     latitude=3.8, longitude=11.5)
        donnees = self.client.get(reverse('carte')).context["etablissements"]
        self.assertEqual((donnees[0]["type"], donnees[0]["approx"]), ("Institut privé (IPES)", True))

    def test_aucune_bibliotheque_chargee_depuis_un_service_exterieur(self):
        for nom in ('accueil', 'chat', 'carte'):
            page = self.client.get(reverse(nom)).content.decode()
            for domaine in ("cdn.jsdelivr.net", "unpkg.com", "cdnjs.cloudflare.com", "fonts.googleapis.com"):
                self.assertNotIn(domaine, page, f"{nom} : {domaine}")

    def test_limite_des_messages_vocaux(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings
        with override_settings(LIMITES_PAR_HEURE={'transcription': (1, 1)}), \
                mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}), mock.patch('rag.ia.transcrire_audio', return_value="ok"):
            codes = [self.client.post(reverse('api_transcrire'), {"audio": SimpleUploadedFile("v.webm", b"a" * 2000)}).status_code
                     for _ in range(2)]
        self.assertEqual(codes, [200, 429])


class TranscriptionTests(TestCase):
    """Sur du silence, Whisper invente des phrases (« Sous-titrage Société Radio-Canada ») : on ne les envoie pas."""

    def envoyer(self, contenu=b"a" * 2000):
        from django.core.files.uploadedfile import SimpleUploadedFile
        return self.client.post(reverse('api_transcrire'), {"audio": SimpleUploadedFile("voix.webm", contenu)})

    def test_phrases_fantomes_refusees(self):
        from rag.ia import est_phrase_fantome
        for texte in ("Sous-titrage Société Radio-Canada", " Sous-titres réalisés par la communauté d'Amara.org",
                      "Merci d'avoir regardé !", "Thank you for watching.", "you", ""):
            self.assertTrue(est_phrase_fantome(texte), texte)
        self.assertFalse(est_phrase_fantome("Quelles écoles d'ingénieurs à Douala ?"))
        self.assertFalse(est_phrase_fantome("Merci pour ta réponse, et pour le BTS ?"))

    def test_silence_transcrit_en_phrase_fantome(self):
        reponse_groq = mock.Mock(text=" Sous-titrage Société Radio-Canada")
        faux_client = mock.Mock()
        faux_client.audio.transcriptions.create.return_value = reponse_groq
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}), mock.patch('rag.ia.client', return_value=faux_client):
            reponse = self.envoyer()
        self.assertEqual(reponse.status_code, 422)
        self.assertIn("rien entendu", reponse.json()["erreur"])

    def test_enregistrement_trop_court_sans_appel_a_groq(self):
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "x"}), mock.patch('rag.ia.transcrire_audio') as appel:
            reponse = self.envoyer(b"")
        self.assertEqual(reponse.status_code, 400)
        appel.assert_not_called()


class TachesQuotidiennesTests(TestCase):
    """Route appelée chaque jour par Vercel Cron."""

    def test_refusee_sans_le_secret(self):
        from django.test import override_settings
        with override_settings(CRON_SECRET="s3cret"):
            self.assertEqual(self.client.get(reverse('taches_quotidiennes')).status_code, 401)
            self.assertEqual(self.client.get(reverse('taches_quotidiennes'), HTTP_AUTHORIZATION="Bearer faux").status_code, 401)
        with override_settings(CRON_SECRET=""):
            self.assertEqual(self.client.get(reverse('taches_quotidiennes'), HTTP_AUTHORIZATION="Bearer ").status_code, 401)

    def test_lance_le_nettoyage_et_les_rappels(self):
        from django.test import override_settings
        with override_settings(CRON_SECRET="s3cret"):
            reponse = self.client.get(reverse('taches_quotidiennes'), HTTP_AUTHORIZATION="Bearer s3cret")
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(set(reponse.json()), {"nettoyer_donnees", "envoyer_rappels_concours"})
        self.assertNotIn("erreur", " ".join(reponse.json().values()))
