import json
import logging
import os
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from etablissements.models import Etablissement
from interface.limites import limite_atteinte, reponse_limite
from interface.models import Profil

from .models import Annale, Concours, Filiere, ResultatTest
from .quiz import MATIERES_QUIZ, creer_quiz
from .services import domaines_du_profil, ecoles_proches, position_par_defaut
from .test_orientation import DESCRIPTIONS, QUESTIONS, calculer_scores

logger = logging.getLogger(__name__)


def profil_ou_none(request):
    if request.user.is_authenticated:
        return Profil.objects.filter(utilisateur=request.user).first()
    return None


# ---------- Fiches filières ----------

def filieres(request):
    q = request.GET.get('q', '').strip()
    domaine = request.GET.get('domaine', '')
    niveau = request.GET.get('niveau', '')

    liste = Filiere.objects.annotate(nb_ue=Count('unites', distinct=True), nb_ecoles=Count('etablissements', distinct=True))
    if q:
        liste = liste.filter(Q(nom__icontains=q) | Q(famille__icontains=q) | Q(debouches__icontains=q) | Q(unites__intitule__icontains=q)).distinct()
    if domaine:
        liste = liste.filter(domaine=domaine)
    if niveau:
        liste = liste.filter(niveau=niveau)

    # Domaines suggérés selon le profil de l'élève
    suggeres = domaines_du_profil(profil_ou_none(request))

    return render(request, 'orientation/filieres.html', {
        'filieres': liste,
        'q': q, 'domaine': domaine, 'niveau': niveau,
        'domaines': Filiere.DOMAINES, 'niveaux': Filiere.NIVEAUX,
        'suggeres': suggeres,
    })


def filiere(request, slug):
    fiche = get_object_or_404(Filiere, slug=slug)
    unites = list(fiche.unites.all())
    semestres = [(numero, list(ues)) for numero, ues in groupby(unites, key=lambda u: u.semestre)]
    totaux = fiche.unites.aggregate(credits=Sum('credits'), heures=Sum('heures'))

    profil = profil_ou_none(request)
    point, lieu = position_par_defaut(profil)
    ecoles = ecoles_proches(point, filiere=fiche)

    return render(request, 'orientation/filiere.html', {
        'fiche': fiche,
        'semestres': semestres,
        'totaux': totaux,
        'ecoles': ecoles,
        'lieu': lieu,
        'concours': fiche.concours.select_related('etablissement'),
        'sujets': fiche.sujets.select_related('auteur')[:5],
    })


# ---------- Calendrier des concours ----------

def concours(request):
    tous = list(Concours.objects.select_related('etablissement').prefetch_related('filieres'))
    ordre = {'ouvert': 0, 'bientot': 1, 'epreuves': 2, 'a_venir': 3, 'termine': 4}
    tous.sort(key=lambda c: (ordre[c.statut()[0]], c.date_cloture or timezone.localdate().replace(year=9999), c.nom))

    filtre = request.GET.get('statut', '')
    if filtre:
        tous = [c for c in tous if c.statut()[0] == filtre]

    suivis = set()
    if request.user.is_authenticated:
        suivis = set(request.user.concours_suivis.values_list('pk', flat=True))

    return render(request, 'orientation/concours.html', {
        'concours': tous,
        'suivis': suivis,
        'filtre': filtre,
        'aujourdhui': timezone.localdate(),
    })


@login_required
@require_POST
def suivre_concours(request, pk):
    """Active ou désactive les rappels pour un concours."""
    c = get_object_or_404(Concours, pk=pk)
    if c.abonnes.filter(pk=request.user.pk).exists():
        c.abonnes.remove(request.user)
        messages.success(request, _("Tu ne recevras plus de rappels pour « %(nom)s ».") % {"nom": c.nom})
    else:
        c.abonnes.add(request.user)
        messages.success(request, _("C'est noté ! Tu recevras un rappel par email avant chaque date clé de « %(nom)s ».") % {"nom": c.nom})
    return redirect(request.POST.get('suivant') or 'orientation:concours')


# ---------- Écoles proches ----------

def ecoles_pour_toi(request):
    profil = profil_ou_none(request)

    # Position : celle du navigateur si l'élève l'a partagée, sinon le chef-lieu de sa région
    point, lieu = None, None
    try:
        lat, lon = float(request.GET['lat']), float(request.GET['lon'])
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            point, lieu = Point(lon, lat, srid=4326), _("ta position actuelle")
    except (KeyError, ValueError):
        pass
    if point is None:
        point, lieu = position_par_defaut(profil)

    # Filière choisie, sinon les domaines du profil
    fiche = Filiere.objects.filter(slug=request.GET.get('filiere', '')).first()
    domaine = request.GET.get('domaine', '')
    domaines = [domaine] if domaine else ([] if fiche else domaines_du_profil(profil))

    ecoles = ecoles_proches(point, filiere=fiche, domaines=domaines)
    donnees_carte = [
        {
            'nom': e.nom, 'ville': e.ville or e.adresse,
            'lat': e.localisation.y, 'lon': e.localisation.x,
            'km': round(e.distance.km) if getattr(e, 'distance', None) is not None else None,
        }
        for e in ecoles
    ]

    return render(request, 'orientation/ecoles_proches.html', {
        'ecoles': ecoles,
        'donnees_carte': donnees_carte,
        'position': {'lat': point.y, 'lon': point.x} if point else None,
        'lieu': lieu,
        'fiche': fiche,
        'domaine': domaine,
        'domaines_actifs': domaines,
        'domaines': Filiere.DOMAINES,
        'toutes_filieres': Filiere.objects.filter(etablissements__isnull=False).distinct().order_by('nom'),
        'profil': profil,
    })


# ---------- Test d'orientation ----------

def test_orientation(request):
    if request.method == 'POST':
        choix = []
        for i in range(len(QUESTIONS)):
            try:
                choix.append(int(request.POST.get(f'q{i}', '')))
            except ValueError:
                choix.append(None)
        if sum(c is not None for c in choix) < len(QUESTIONS) // 2:
            messages.error(request, _("Réponds au moins à la moitié des questions pour obtenir un résultat."))
            return redirect('orientation:test')
        resultat = ResultatTest.objects.create(
            utilisateur=request.user if request.user.is_authenticated else None,
            scores=calculer_scores(choix),
        )
        # Un visiteur sans compte peut revoir son résultat pendant sa visite
        request.session['resultats_test'] = request.session.get('resultats_test', []) + [resultat.pk]
        return redirect('orientation:resultat_test', pk=resultat.pk)

    return render(request, 'orientation/test.html', {'questions': QUESTIONS})


def resultat_test(request, pk):
    resultat = get_object_or_404(ResultatTest, pk=pk)
    proprietaire = request.user.is_authenticated and resultat.utilisateur_id == request.user.id
    if not proprietaire and pk not in request.session.get('resultats_test', []):
        messages.error(request, _("Ce résultat n'est pas le tien."))
        return redirect('orientation:test')

    noms = dict(Filiere.DOMAINES)
    classement = sorted(resultat.scores.items(), key=lambda x: -x[1])
    podium = [
        {
            'domaine': d, 'nom': noms[d], 'score': score,
            'description': DESCRIPTIONS[d],
            'filieres': Filiere.objects.filter(domaine=d)[:4],
        }
        for d, score in classement[:3]
    ]
    return render(request, 'orientation/resultat_test.html', {
        'resultat': resultat,
        'podium': podium,
        'autres': [(noms[d], score) for d, score in classement[3:]],
        'question_orientia': _("Mon test d'orientation montre que je suis fait·e pour le domaine « %(domaine)s ». "
                               "Quelles études et quelles écoles me conseilles-tu ?") % {"domaine": podium[0]['nom']},
    })


# ---------- Annales et quiz ----------

def annales(request):
    concours_id = request.GET.get('concours', '')
    liste = Annale.objects.select_related('concours')
    if concours_id.isdigit():
        liste = liste.filter(concours_id=concours_id)
    return render(request, 'orientation/annales.html', {
        'annales': liste,
        'concours': Concours.objects.order_by('nom'),
        'concours_id': concours_id,
        'matieres': MATIERES_QUIZ,
    })


@require_POST
def generer_quiz(request):
    """Demande à OrientIA 5 questions d'entraînement (QCM) sur une matière."""
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'erreur': _("Requête invalide.")}, status=400)
    matiere = data.get('matiere', '')
    if matiere not in MATIERES_QUIZ:
        return JsonResponse({'erreur': _("Choisis une matière dans la liste.")}, status=400)
    concours_choisi = Concours.objects.filter(pk=data.get('concours') or 0).first()

    if not os.getenv("GROQ_API_KEY"):
        return JsonResponse({'erreur': _("Les quiz utilisent OrientIA : ajoute la clé GROQ_API_KEY dans config/.env.")}, status=503)
    minutes = limite_atteinte(request, 'quiz')
    if minutes:
        return reponse_limite(request, minutes)

    try:
        questions = creer_quiz(matiere, concours_choisi.nom if concours_choisi else None, langue=get_language())
    except Exception:
        logger.exception("Erreur lors de la génération du quiz")
        return JsonResponse({'erreur': _("OrientIA n'a pas pu préparer le quiz. Réessaie dans quelques secondes.")}, status=503)
    return JsonResponse({'questions': questions})


# ---------- Comparateur et favoris ----------

def comparateur(request):
    profil = profil_ou_none(request)
    ids = [i for i in request.GET.getlist('ecoles') if i.isdigit()][:3]
    if not ids and profil:
        ids = [str(pk) for pk in profil.ecoles_favorites.values_list('pk', flat=True)[:3]]

    point, lieu = position_par_defaut(profil)
    ecoles = Etablissement.objects.filter(pk__in=ids).prefetch_related('filieres', 'concours')
    if point is not None:
        ecoles = ecoles.annotate(distance=Distance('localisation', point))
    ecoles = ecoles.annotate(nb_questions=Count('sujets', distinct=True))
    # Garder l'ordre choisi par l'élève
    ecoles = sorted(ecoles, key=lambda e: ids.index(str(e.pk)))

    favoris = set(profil.ecoles_favorites.values_list('pk', flat=True)) if profil else set()
    noms = [e.nom for e in ecoles]
    question = None
    if len(noms) >= 2:
        question = _("Aide-moi à choisir entre %(ecoles)s et %(derniere)s : quelles différences et laquelle me conseilles-tu ?") % {
            "ecoles": ", ".join(noms[:-1]), "derniere": noms[-1]}
    return render(request, 'orientation/comparateur.html', {
        'ecoles': ecoles,
        'selections': (ids + ['', '', ''])[:3],
        'question_orientia': question,
        'toutes': Etablissement.objects.order_by('nom'),
        'favoris': favoris,
        'lieu': lieu,
    })


@login_required
@require_POST
def basculer_favori(request, pk):
    ecole = get_object_or_404(Etablissement, pk=pk)
    profil, _cree = Profil.objects.get_or_create(utilisateur=request.user)
    if profil.ecoles_favorites.filter(pk=pk).exists():
        profil.ecoles_favorites.remove(ecole)
        messages.success(request, _("« %(nom)s » retirée de tes favoris.") % {"nom": ecole.nom})
    else:
        profil.ecoles_favorites.add(ecole)
        messages.success(request, _("« %(nom)s » ajoutée à tes favoris.") % {"nom": ecole.nom})
    return redirect(request.POST.get('suivant') or 'orientation:comparateur')
