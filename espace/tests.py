from datetime import date, time
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from orientation.models import Filiere, UniteEnseignement

from .models import ChoixFiliere, Creneau, Note, SeanceRevision, Tache
from .services import bilan_notes, minutes, plages_libres, proposer_emplois_du_temps


class EspaceMixin:
    def setUp(self):
        self.eleve = User.objects.create_user("awa", "awa@exemple.com", "Orientation2026!")
        self.client.force_login(self.eleve)
        self.filiere = Filiere.objects.create(nom="Aquaculture", slug="bts-aquaculture", domaine="agropastoral")
        self.maths = UniteEnseignement.objects.create(filiere=self.filiere, semestre=1, code="AQC112", intitule="Mathématiques", credits=4)
        self.bio = UniteEnseignement.objects.create(filiere=self.filiere, semestre=1, code="AQC114", intitule="Biologie", credits=6)


class FiliereTests(EspaceMixin, TestCase):

    def test_etudiant_voit_ses_matieres_et_leur_avancement(self):
        self.client.post(reverse('espace:filiere'), {"action": "statut", "statut": "etudiant"})
        self.client.post(reverse('espace:filiere'), {"action": "inscription", "filiere": self.filiere.pk, "semestre": 1})
        self.client.post(reverse('espace:filiere'), {"action": "avancement", "unite": self.maths.pk, "statut": "validee"})
        page = self.client.get(reverse('espace:filiere'))
        self.assertContains(page, "Biologie")
        self.assertEqual(page.context['progression'], 50)

    def test_bachelier_gere_ses_voeux(self):
        self.client.post(reverse('espace:filiere'), {"action": "choix", "rang": 1, "filiere": self.filiere.pk, "etape": "candidature"})
        voeu = ChoixFiliere.objects.get(utilisateur=self.eleve)
        self.assertEqual((voeu.rang, voeu.etape, voeu.avancement()), (1, "candidature", 60))
        self.client.post(reverse('espace:filiere'), {"action": "choix", "rang": 1, "filiere": self.filiere.pk, "etape": "admis"})
        self.assertEqual(ChoixFiliere.objects.get(utilisateur=self.eleve).avancement(), 100)
        self.assertEqual(ChoixFiliere.objects.count(), 1)


class SuiviTests(EspaceMixin, TestCase):

    def test_moyennes_ponderees_et_credits(self):
        Note.objects.create(utilisateur=self.eleve, matiere="Mathématiques", unite=self.maths, semestre=1, valeur=8, coefficient=1, date=date.today())
        Note.objects.create(utilisateur=self.eleve, matiere="Mathématiques", unite=self.maths, semestre=1, valeur=14, coefficient=2, date=date.today())
        Note.objects.create(utilisateur=self.eleve, matiere="Biologie", unite=self.bio, semestre=1, valeur=9, coefficient=1, date=date.today())
        semestre = bilan_notes(self.eleve)[0]
        maths = next(m for m in semestre['matieres'] if m['nom'] == "Mathématiques")
        self.assertEqual(maths['moyenne'], 12)          # (8 + 14×2) / 3
        self.assertEqual(semestre['credits_valides'], 4)  # Biologie < 10 : non validée
        self.assertAlmostEqual(float(semestre['moyenne']), (12 * 4 + 9 * 6) / 10)

    def test_note_hors_bareme_refusee(self):
        self.client.post(reverse('espace:suivi'), {"action": "note", "matiere": "Maths", "valeur": 25, "coefficient": 1,
                                                    "semestre": 1, "type_note": "devoir", "date": "2026-10-01"})
        self.assertFalse(Note.objects.exists())

    def test_taches(self):
        self.client.post(reverse('espace:suivi'), {"action": "tache", "titre": "Déposer mon dossier", "echeance": "2026-12-01"})
        tache = Tache.objects.get()
        self.client.post(reverse('espace:suivi'), {"action": "basculer_tache", "pk": tache.pk})
        tache.refresh_from_db()
        self.assertTrue(tache.faite)
        self.assertEqual(self.client.get(reverse('espace:suivi')).context['taches_pourcentage'], 100)


class EmploiDuTempsTests(EspaceMixin, TestCase):

    def ajouter(self, type_creneau, jour, debut, fin, intitule=""):
        Creneau.objects.create(utilisateur=self.eleve, type_creneau=type_creneau, jour=jour, debut=debut, fin=fin, intitule=intitule)

    def test_les_cours_sont_retires_des_disponibilites(self):
        self.ajouter("dispo", 0, time(8), time(18))
        self.ajouter("cours", 0, time(10), time(12), "Maths")
        self.assertEqual(plages_libres(self.eleve)[0], [(8 * 60, 10 * 60), (12 * 60, 18 * 60)])

    def test_propositions_dans_les_plages_libres_sans_chevauchement(self):
        for jour in range(7):
            self.ajouter("dispo", jour, time(16), time(21))
        self.ajouter("cours", 2, time(16), time(18), "Biologie")
        propositions = proposer_emplois_du_temps(self.eleve)
        self.assertEqual([p['cle'] for p in propositions], ["equilibree", "intensive", "legere"])
        legere = propositions[2]
        self.assertFalse(any(s['jour'] == 6 for s in legere['seances']))  # dimanche libre
        for p in propositions:
            self.assertTrue(p['seances'])
            for s in p['seances']:
                self.assertGreaterEqual(minutes(s['debut']), 16 * 60)
                self.assertLessEqual(minutes(s['fin']), 21 * 60)
                self.assertFalse(s['jour'] == 2 and minutes(s['debut']) < 18 * 60)  # pas pendant le cours
        intensive, equilibree = propositions[1], propositions[0]
        self.assertGreater(intensive['total_heures'], equilibree['total_heures'])

    def test_choisir_une_proposition(self):
        self.ajouter("dispo", 1, time(14), time(18))
        self.client.post(reverse('espace:emploi_du_temps'), {"action": "choisir", "formule": "equilibree"})
        self.assertTrue(SeanceRevision.objects.filter(utilisateur=self.eleve, formule="equilibree").exists())
        self.assertContains(self.client.get(reverse('espace:emploi_du_temps')), "bloc-revision")

    def test_creneau_invalide_refuse(self):
        self.client.post(reverse('espace:emploi_du_temps'), {"action": "ajouter", "type_creneau": "cours", "jour": 0, "debut": "12:00", "fin": "10:00"})
        self.assertFalse(Creneau.objects.exists())

    def test_import_par_photo(self):
        lus = [{"type": "cours", "jour": 0, "debut": "08:00", "fin": "10:00", "intitule": "Maths"},
               {"type": "dispo", "jour": 5, "debut": "09:00", "fin": "12:00"},
               {"type": "cours", "jour": 9, "debut": "08:00", "fin": "10:00"}]  # jour impossible : ignoré
        photo = SimpleUploadedFile("edt.png", b"\x89PNG fausse image", content_type="image/png")
        with mock.patch.dict('os.environ', {"GROQ_API_KEY": "x"}), mock.patch('rag.ia.extraire_creneaux', return_value=lus) as extraction:
            self.client.post(reverse('espace:importer_emploi'), {"fichier": photo})
        self.assertIsNotNone(extraction.call_args.kwargs.get('image'))
        self.assertEqual(Creneau.objects.filter(utilisateur=self.eleve).count(), 2)

    def test_import_type_de_fichier_refuse(self):
        fichier = SimpleUploadedFile("virus.exe", b"MZ", content_type="application/octet-stream")
        with mock.patch.dict('os.environ', {"GROQ_API_KEY": "x"}):
            self.client.post(reverse('espace:importer_emploi'), {"fichier": fichier})
        self.assertFalse(Creneau.objects.exists())

    def test_pages_reservees_aux_comptes(self):
        self.client.logout()
        for nom in ('espace:filiere', 'espace:emploi_du_temps', 'espace:suivi'):
            self.assertEqual(self.client.get(reverse(nom)).status_code, 302, nom)
