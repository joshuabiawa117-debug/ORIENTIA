from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from interface.models import Profil

from .models import Reponse, Sujet


class CommunauteTests(TestCase):

    def setUp(self):
        self.awa = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        self.paul = User.objects.create_user("paul", "paul@exemple.com", "Orientation2026!")
        self.sujet = Sujet.objects.create(auteur=self.awa, titre="Comment entrer à l'ENSP ?", contenu="Je suis en Tle C.")

    def test_liste_et_detail_publics(self):
        self.assertContains(self.client.get(reverse('communaute:liste')), "Comment entrer à l&#x27;ENSP ?")
        self.assertContains(self.client.get(reverse('communaute:detail', args=[self.sujet.pk])), "Je suis en Tle C.")

    def test_poser_une_question_demande_un_compte(self):
        reponse = self.client.get(reverse('communaute:nouveau'))
        self.assertEqual(reponse.status_code, 302)
        self.assertIn(reverse('connexion'), reponse.url)

    def test_poser_une_question(self):
        self.client.force_login(self.paul)
        reponse = self.client.post(reverse('communaute:nouveau'), {"titre": "BTS ou licence ?", "contenu": "J'hésite."})
        sujet = Sujet.objects.get(titre="BTS ou licence ?")
        self.assertRedirects(reponse, reverse('communaute:detail', args=[sujet.pk]))
        self.assertEqual(sujet.auteur, self.paul)

    def test_repondre_voter_et_meilleure_reponse(self):
        self.client.force_login(self.paul)
        self.client.post(reverse('communaute:repondre', args=[self.sujet.pk]), {"contenu": "Il faut un bac C ou D."})
        rep = Reponse.objects.get(sujet=self.sujet)

        # On ne vote pas pour soi-même
        self.assertEqual(self.client.post(reverse('communaute:voter', args=[rep.pk])).status_code, 400)
        # Seul l'auteur de la question choisit la meilleure réponse
        self.assertEqual(self.client.post(reverse('communaute:meilleure', args=[rep.pk])).status_code, 403)

        self.client.force_login(self.awa)
        self.assertEqual(self.client.post(reverse('communaute:voter', args=[rep.pk])).json(), {"aime": True, "votes": 1})
        self.assertEqual(self.client.post(reverse('communaute:voter', args=[rep.pk])).json(), {"aime": False, "votes": 0})
        self.client.post(reverse('communaute:meilleure', args=[rep.pk]))
        rep.refresh_from_db()
        self.assertTrue(rep.meilleure)
        self.assertTrue(self.sujet.est_resolu())

    def test_onglet_sans_reponse(self):
        Reponse.objects.create(sujet=Sujet.objects.create(auteur=self.awa, titre="Déjà répondu", contenu="..."),
                               auteur=self.paul, contenu="Oui")
        page = self.client.get(reverse('communaute:liste') + "?onglet=sans_reponse")
        self.assertContains(page, "Comment entrer")
        self.assertNotContains(page, "Déjà répondu")


class MessagesPrivesTests(TestCase):

    def setUp(self):
        self.awa = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        self.paul = User.objects.create_user("paul", "paul@exemple.com", "Orientation2026!")
        # Deux élèves mineurs : ils peuvent s'écrire
        Profil.objects.filter(utilisateur__in=[self.awa, self.paul]).update(annee_naissance=timezone.now().year - 17)

    def test_ecrire_a_un_membre_et_compteur_non_lus(self):
        self.client.force_login(self.awa)
        self.assertContains(self.client.get(reverse('communaute:membre', args=["paul"])), "Envoyer un message")
        self.client.post(reverse('communaute:conversation', args=["paul"]), {"contenu": "Salut Paul, tu es à l'ENSP ?"})

        self.client.force_login(self.paul)
        self.assertEqual(self.client.get(reverse('communaute:messagerie')).context['nb_messages_non_lus'], 1)
        self.assertContains(self.client.get(reverse('communaute:conversation', args=["awa"])), "tu es à l&#x27;ENSP ?")
        # Lu en ouvrant la conversation
        self.assertEqual(self.client.get(reverse('communaute:messagerie')).context['nb_messages_non_lus'], 0)

    def test_on_ne_lit_pas_les_messages_des_autres(self):
        from .models import MessagePrive
        MessagePrive.objects.create(expediteur=self.awa, destinataire=self.paul, contenu="secret")
        tiers = User.objects.create_user("tiers", "t@exemple.com", "Orientation2026!")
        self.client.force_login(tiers)
        self.assertNotContains(self.client.get(reverse('communaute:conversation', args=["paul"])), "secret")
        self.assertNotContains(self.client.get(reverse('communaute:messagerie')), "secret")

    def test_pas_de_message_a_soi_meme(self):
        self.client.force_login(self.awa)
        self.client.post(reverse('communaute:conversation', args=["awa"]), {"contenu": "moi"})
        from .models import MessagePrive
        self.assertFalse(MessagePrive.objects.exists())

    def test_messagerie_reservee_aux_comptes(self):
        self.assertEqual(self.client.get(reverse('communaute:messagerie')).status_code, 302)


class ModerationTests(TestCase):
    """Signalements, masquage automatique, blocage, protection des mineurs et limites d'envoi."""

    def membre(self, nom, age=None, badge=""):
        user = User.objects.create_user(nom, f"{nom}@exemple.com", "Orientation2026!")
        Profil.objects.filter(utilisateur=user).update(
            annee_naissance=timezone.now().year - age if age else None, badge=badge)
        return User.objects.get(pk=user.pk)

    def setUp(self):
        from .models import Reponse, Sujet
        self.eleve = self.membre("awa", age=16)
        self.adulte = self.membre("marc", age=30)
        self.sujet = Sujet.objects.create(auteur=self.eleve, titre="BTS ou licence ?", contenu="J'hésite.")
        self.reponse = Reponse.objects.create(sujet=self.sujet, auteur=self.adulte, contenu="Envoie-moi 5000 F pour une admission")

    def ecrire(self, expediteur, destinataire, texte="Bonjour"):
        from .models import MessagePrive
        self.client.force_login(expediteur)
        self.client.post(reverse('communaute:conversation', args=[destinataire.username]), {"contenu": texte})
        return MessagePrive.objects.filter(expediteur=expediteur, destinataire=destinataire, contenu=texte).exists()

    def test_signaler_une_reponse(self):
        from .models import Signalement
        self.client.force_login(self.eleve)
        url = reverse('communaute:signaler', args=['reponse', self.reponse.pk])
        self.assertContains(self.client.get(url), "Envoie-moi 5000 F")
        self.client.post(url, {"motif": "arnaque", "details": "Il demande de l'argent"})
        signalement = Signalement.objects.get()
        self.assertEqual((signalement.membre_signale, signalement.reponse), (self.adulte, self.reponse))

    def test_trois_signalements_masquent_le_contenu(self):
        for i in range(3):
            self.client.force_login(self.membre(f"temoin{i}", age=17))
            self.client.post(reverse('communaute:signaler', args=['reponse', self.reponse.pk]), {"motif": "arnaque"})
        self.reponse.refresh_from_db()
        self.assertTrue(self.reponse.masque)
        self.assertNotContains(self.client.get(reverse('communaute:detail', args=[self.sujet.pk])), "5000 F")

    def test_question_masquee_invisible_pour_les_autres(self):
        self.sujet.masque = True
        self.sujet.save()
        self.assertNotContains(self.client.get(reverse('communaute:liste')), "BTS ou licence")
        self.assertEqual(self.client.get(reverse('communaute:detail', args=[self.sujet.pk])).status_code, 404)
        self.client.force_login(self.eleve)
        self.assertEqual(self.client.get(reverse('communaute:detail', args=[self.sujet.pk])).status_code, 200)

    def test_on_ne_signale_que_les_messages_recus(self):
        from .models import MessagePrive
        autre = self.membre("lea", age=16)
        message = MessagePrive.objects.create(expediteur=self.eleve, destinataire=autre, contenu="salut")
        self.client.force_login(self.adulte)
        self.assertEqual(self.client.get(reverse('communaute:signaler', args=['message', message.pk])).status_code, 404)

    def test_un_adulte_non_verifie_ne_peut_pas_ecrire_a_un_mineur(self):
        self.assertFalse(self.ecrire(self.adulte, self.eleve))
        self.assertFalse(self.ecrire(self.eleve, self.adulte))
        page = self.client.get(reverse('communaute:membre', args=[self.adulte.username]))
        self.assertContains(page, "Pour protéger les plus jeunes")

    def test_un_conseiller_verifie_peut_ecrire_a_un_mineur(self):
        conseiller = self.membre("conseil", age=40, badge="conseiller")
        self.assertTrue(self.ecrire(conseiller, self.eleve))
        self.assertTrue(self.ecrire(self.eleve, conseiller))

    def test_age_obligatoire_pour_ecrire(self):
        sans_age = self.membre("inconnu")
        self.assertFalse(self.ecrire(sans_age, self.eleve))

    def test_blocage_dans_les_deux_sens(self):
        camarade = self.membre("lea", age=17)
        self.client.force_login(self.eleve)
        self.client.post(reverse('communaute:bloquer', args=[camarade.username]))
        self.assertFalse(self.ecrire(camarade, self.eleve))
        self.assertFalse(self.ecrire(self.eleve, camarade))
        # Débloquer rétablit les messages
        self.client.force_login(self.eleve)
        self.client.post(reverse('communaute:bloquer', args=[camarade.username]))
        self.assertTrue(self.ecrire(camarade, self.eleve))

    def test_limite_de_messages_par_heure(self):
        from django.test import override_settings
        camarade = self.membre("lea", age=17)
        with override_settings(LIMITES_PAR_HEURE={'message_prive': (0, 2)}):
            envoyes = [self.ecrire(self.eleve, camarade, f"message {i}") for i in range(3)]
        self.assertEqual(envoyes, [True, True, False])

    def test_badge_seulement_s_il_est_attribue(self):
        Profil.objects.filter(utilisateur=self.adulte).update(type_profil='contributeur')
        page = self.client.get(reverse('communaute:detail', args=[self.sujet.pk]))
        self.assertNotContains(page, "bi-patch-check-fill")
        Profil.objects.filter(utilisateur=self.adulte).update(badge='contributeur')
        self.assertContains(self.client.get(reverse('communaute:detail', args=[self.sujet.pk])), "Contributeur vérifié")
