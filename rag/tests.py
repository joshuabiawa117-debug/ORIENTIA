import os
import uuid
from datetime import timedelta
from unittest import mock

import groq
import httpx
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchVector
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .assistant import bloc_historique, rechercher_chunks_pertinents, sources_de, titre_source
from .decoupage import decouper
from .models import DocumentChunk, EchangeChat


class DecoupageTests(TestCase):

    def test_passages_courts_et_sans_perte(self):
        texte = "\n\n".join(f"Paragraphe {i}. " + "La filière BTS forme des techniciens supérieurs. " * 8 for i in range(12))
        passages = decouper(texte, taille=500, chevauchement=50)
        self.assertGreater(len(passages), 5)
        self.assertTrue(all(0 < len(p) <= 560 for p in passages))  # 500 + la reprise du passage précédent
        for i in range(12):
            self.assertTrue(any(f"Paragraphe {i}." in p for p in passages), i)

    def test_reprise_de_la_fin_du_passage_precedent(self):
        passages = decouper(" ".join(f"mot{i}" for i in range(400)), taille=200, chevauchement=40)
        fin_du_premier = passages[0].split()[-1]
        self.assertIn(fin_du_premier, passages[1].split()[:8])

    def test_mot_tres_long_coupe_quand_meme(self):
        self.assertTrue(all(len(p) <= 500 for p in decouper("x" * 1200, chevauchement=0)))


class SourcesEtRechercheTests(TestCase):

    def test_titre_lisible_des_sources(self):
        self.assertEqual(titre_source("Guide_Orientation_Post_Bac_Cameroun.pdf"), "Guide Orientation Post Bac Cameroun")
        chunks = [DocumentChunk(source="a_b.pdf"), DocumentChunk(source="c.pdf"), DocumentChunk(source="a_b.pdf")]
        self.assertEqual(sources_de(chunks), ["a b", "c"])

    def test_recherche_insensible_aux_accents(self):
        DocumentChunk.objects.create(source="guide.pdf", contenu="L'école d'ingénieurs forme des ingénieurs en génie civil.")
        DocumentChunk.objects.create(source="guide.pdf", contenu="La pisciculture est enseignée en BTS.")
        DocumentChunk.objects.update(recherche=SearchVector("contenu", config="french_unaccent"))
        with mock.patch("rag.assistant.mots_cles_recherche", return_value=[]):
            resultats = rechercher_chunks_pertinents("ecole ingenieur genie civil")
        self.assertIn("génie civil", resultats[0].contenu)

    def test_historique_resume_les_reponses_longues(self):
        texte = bloc_historique([("Quelles filières ?", "x" * 5000), ("Et la 2e ?", "Le BTS.")])
        self.assertIn("Élève : Et la 2e ?", texte)
        self.assertLess(len(texte), 2000)


class ModeleDeSecoursTests(TestCase):

    def test_bascule_sur_le_modele_de_secours_si_groq_echoue(self):
        from . import ia
        reponse_ok = mock.Mock(choices=[mock.Mock(message=mock.Mock(content="Réponse de secours"))])
        erreur = groq.APIConnectionError(request=httpx.Request("POST", "https://api.groq.com"))
        faux_client = mock.Mock()
        faux_client.chat.completions.create.side_effect = [erreur, reponse_ok]
        with mock.patch.object(ia, "client", return_value=faux_client):
            self.assertEqual(ia.generer_texte("Bonjour"), "Réponse de secours")
        modeles = [appel.kwargs["model"] for appel in faux_client.chat.completions.create.call_args_list]
        self.assertEqual(modeles, [ia.MODELE_CHAT, ia.MODELE_SECOURS])


@mock.patch.dict(os.environ, {"GROQ_API_KEY": "test"})
@mock.patch("interface.views.rechercher_chunks_pertinents", return_value=[DocumentChunk(source="Guide_BTS.pdf", contenu="…")])
class ApiChatMemoireTests(TestCase):
    """Mémoire de conversation, sources, avis et limites d'utilisation."""

    def setUp(self):
        DocumentChunk.objects.create(source="guide.pdf", contenu="Texte officiel.")
        self.awa = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")

    def poser(self, question, conversation=None):
        return self.client.post(reverse("api_chat"), {"question": question, "conversation": conversation},
                                content_type="application/json")

    def test_reponse_avec_sources_et_echange_enregistre(self, _recherche):
        with mock.patch("rag.assistant.generer_texte", return_value="Voici les BTS."):
            data = self.poser("Quels BTS ?").json()
        self.assertEqual(data["reponse"], "Voici les BTS.")
        self.assertEqual(data["sources"], ["Guide BTS"])
        echange = EchangeChat.objects.get(pk=data["echange"])
        self.assertEqual((echange.question, str(echange.conversation)), ("Quels BTS ?", data["conversation"]))

    def test_la_question_suivante_connait_les_echanges_precedents(self, _recherche):
        self.client.force_login(self.awa)
        with mock.patch("rag.assistant.generer_texte", return_value="Le BTS Aquaculture et le BTS Génie rural."):
            conversation = self.poser("Quels BTS en agriculture ?").json()["conversation"]
        with mock.patch("rag.assistant.generer_texte", return_value="Il dure 2 ans.") as appel:
            self.poser("Et le 2e, il dure combien de temps ?", conversation)
        prompt = appel.call_args[0][0]
        self.assertIn("Élève : Quels BTS en agriculture ?", prompt)
        self.assertIn("BTS Génie rural", prompt)

    def test_on_ne_peut_pas_lire_la_conversation_d_un_autre(self, _recherche):
        autre = User.objects.create_user("paul", "paul@exemple.com", "Orientation2026!")
        secret = EchangeChat.objects.create(conversation=uuid.uuid4(), utilisateur=autre, question="Mon secret", reponse="…")
        self.client.force_login(self.awa)
        with mock.patch("rag.assistant.generer_texte", return_value="ok") as appel:
            self.poser("Et alors ?", str(secret.conversation))
        self.assertNotIn("Mon secret", appel.call_args[0][0])
        self.assertNotContains(self.client.get(reverse("chat") + f"?conversation={secret.conversation}"), "Mon secret")

    def test_avis_sur_une_reponse(self, _recherche):
        with mock.patch("rag.assistant.generer_texte", return_value="ok"):
            echange = self.poser("Quels BTS ?").json()["echange"]
        url = reverse("api_avis")
        self.assertEqual(self.client.post(url, {"echange": echange, "avis": -1}, content_type="application/json").json(), {"avis": -1})
        # Recliquer sur le même bouton retire l'avis
        self.assertEqual(self.client.post(url, {"echange": echange, "avis": -1}, content_type="application/json").json(), {"avis": None})
        # Un autre visiteur ne peut pas noter cette réponse
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.post(url, {"echange": echange, "avis": 1}, content_type="application/json").status_code, 404)

    def test_reponse_frequente_d_un_visiteur_mise_en_cache(self, _recherche):
        with mock.patch("rag.assistant.generer_texte", return_value="Réponse") as appel:
            self.poser("Qu'est-ce qu'un IPES ?")
            self.client.cookies.clear()
            self.assertEqual(self.poser("qu'est-ce   qu'un IPES ?").json()["reponse"], "Réponse")
        self.assertEqual(appel.call_count, 1)

    @override_settings(LIMITES_PAR_HEURE={"chat": (2, 3)})
    def test_limite_par_heure(self, _recherche):
        with mock.patch("rag.assistant.generer_texte", return_value="ok"):
            codes = [self.poser(f"Question {i}").status_code for i in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_historique_et_suppression(self, _recherche):
        self.client.force_login(self.awa)
        with mock.patch("rag.assistant.generer_texte", return_value="ok"):
            conversation = self.poser("Comment entrer à l'ENSP ?").json()["conversation"]
        page = self.client.get(reverse("historique_chat"))
        self.assertContains(page, "Comment entrer à l&#x27;ENSP ?")
        self.assertContains(self.client.get(reverse("chat") + f"?conversation={conversation}"), "Comment entrer")
        self.client.post(reverse("supprimer_conversation", args=[conversation]))
        self.assertFalse(EchangeChat.objects.exists())


class NettoyageDonneesTests(TestCase):

    def test_conversations_de_visiteurs_supprimees_apres_30_jours(self):
        awa = User.objects.create_user("awa", "awa@exemple.com", "x")
        vieux = EchangeChat.objects.create(conversation=uuid.uuid4(), question="vieux", reponse="…")
        recent = EchangeChat.objects.create(conversation=uuid.uuid4(), question="récent", reponse="…")
        du_compte = EchangeChat.objects.create(conversation=uuid.uuid4(), utilisateur=awa, question="élève", reponse="…")
        EchangeChat.objects.filter(pk__in=[vieux.pk, du_compte.pk]).update(date=timezone.now() - timedelta(days=40))
        call_command("nettoyer_donnees", stdout=open(os.devnull, "w"))
        self.assertEqual(set(EchangeChat.objects.values_list("question", flat=True)), {"récent", "élève"})
