import hashlib
import hmac
import json
import logging
import os
import time
import uuid
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .limites import limite_atteinte, reponse_limite
from .models import Profil
from etablissements.models import Etablissement
from orientation.models import Filiere
from orientation.services import domaines_du_profil, ecoles_proches, position_par_defaut
from rag.assistant import ECHANGES_MEMORISES, generer_reponse, rechercher_chunks_pertinents, sources_de
from rag.models import DocumentChunk, EchangeChat

logger = logging.getLogger(__name__)

BACKEND_CLASSIQUE = 'django.contrib.auth.backends.ModelBackend'
LANGUES_DISPONIBLES = dict(settings.LANGUAGES)


def google_actif():
    """Le bouton Google n'est affiché que si les identifiants sont configurés dans config/.env."""
    return bool(os.getenv("GOOGLE_CLIENT_ID") and os.getenv("GOOGLE_CLIENT_SECRET"))


def profil_de(user):
    """Renvoie le profil de l'utilisateur (le crée s'il manque, ex. comptes créés avant les profils)."""
    profil, _cree = Profil.objects.get_or_create(utilisateur=user)
    return profil


def memoriser_langue(reponse, langue):
    """Enregistre la langue choisie dans le cookie lu par Django."""
    reponse.set_cookie(settings.LANGUAGE_COOKIE_NAME, langue, max_age=365 * 24 * 3600, samesite='Lax')
    return reponse


def adresse_sure(request, adresse, defaut='accueil'):
    """N'autorise la redirection que vers une page de notre propre site."""
    if adresse and url_has_allowed_host_and_scheme(adresse, allowed_hosts={request.get_host()}):
        return adresse
    return defaut


@require_POST
def changer_langue(request):
    """Bouton FR / EN : change la langue du site (et du profil si l'élève est connecté)."""
    langue = request.POST.get('langue')
    if langue not in LANGUES_DISPONIBLES:
        langue = settings.LANGUAGE_CODE
    if request.user.is_authenticated:
        Profil.objects.filter(utilisateur=request.user).update(langue=langue)
    return memoriser_langue(redirect(adresse_sure(request, request.POST.get('suivant'))), langue)


def accueil(request):
    return render(request, 'interface/accueil.html', {
        "nb_etablissements": Etablissement.objects.count(),
        "nb_documents": len([f for f in os.listdir(settings.BASE_DIR / "documents") if f.lower().endswith(".pdf")]),
    })


def echanges_de(request):
    """Échanges avec OrientIA qui appartiennent à la personne : son compte, ou sa session si elle n'a pas de compte."""
    if request.user.is_authenticated:
        return EchangeChat.objects.filter(utilisateur=request.user)
    if not request.session.session_key:
        return EchangeChat.objects.none()
    return EchangeChat.objects.filter(utilisateur=None, cle_session=request.session.session_key)


def lire_uuid(valeur):
    try:
        return uuid.UUID(str(valeur))
    except (TypeError, ValueError):
        return None


DEMARRAGE = str(int(time.time()))


def service_worker(request):
    """Service worker (mode hors ligne). Servi à la racine du site pour pouvoir gérer toutes les pages."""
    # La version change quand les fichiers du site changent (en production, leurs noms contiennent une empreinte)
    empreinte = "|".join(static(f) for f in ("css/style.css", "vendor/bootstrap/bootstrap.min.css", "img/favicon.svg"))
    version = hashlib.sha256((empreinte + (DEMARRAGE if settings.DEBUG else "")).encode()).hexdigest()[:12]
    reponse = render(request, 'interface/sw.js', {"version": version, "debug": settings.DEBUG},
                     content_type="application/javascript; charset=utf-8")
    reponse["Service-Worker-Allowed"] = "/"
    reponse["Cache-Control"] = "no-cache"
    return reponse


def taches_quotidiennes(request):
    """Appelée chaque jour par Vercel Cron : nettoyage des données et rappels de concours.

    Vercel envoie l'en-tête « Authorization: Bearer <CRON_SECRET> » : sans ce secret, on refuse.
    """
    import io

    from django.core.management import call_command

    attendu = f"Bearer {settings.CRON_SECRET}"
    if not settings.CRON_SECRET or not hmac.compare_digest(request.headers.get("Authorization", ""), attendu):
        return JsonResponse({"erreur": "non autorisé"}, status=401)
    compte_rendu = {}
    for commande in ("nettoyer_donnees", "envoyer_rappels_concours"):
        sortie = io.StringIO()
        try:
            call_command(commande, stdout=sortie)
            compte_rendu[commande] = sortie.getvalue().strip()
        except Exception as erreur:
            logger.exception("Tâche quotidienne %s impossible", commande)
            compte_rendu[commande] = f"erreur : {erreur}"
    return JsonResponse(compte_rendu)


def hors_ligne(request):
    return render(request, 'interface/hors_ligne.html')


def page_legale(request, page):
    """Politique de confidentialité et conditions d'utilisation : un texte par langue."""
    langue = 'en' if get_language() == 'en' else 'fr'
    return render(request, f'interface/legal/{page}_{langue}.html')


def chat(request):
    """Page du chat. Un élève connecté peut rouvrir une ancienne conversation (?conversation=…)."""
    conversation = lire_uuid(request.GET.get("conversation")) if request.user.is_authenticated else None
    echanges = []
    if conversation:
        echanges = [
            {"id": e.pk, "question": e.question, "reponse": e.reponse, "sources": e.sources,
             "avis": e.avis, "document": e.nom_document}
            for e in echanges_de(request).filter(conversation=conversation)
        ]
    return render(request, 'interface/chat.html', {
        "conversation": str(conversation) if echanges else "",
        "echanges": echanges,
    })


@login_required
def historique_chat(request):
    """Les conversations passées de l'élève, la plus récente en haut."""
    conversations = {}
    for e in EchangeChat.objects.filter(utilisateur=request.user).order_by('-date'):
        conv = conversations.setdefault(e.conversation, {"id": e.conversation, "derniere": e.date, "nb": 0})
        conv["nb"] += 1
        conv["premiere_question"] = e.question  # ordre décroissant : la dernière affectée est la première question
    return render(request, 'interface/historique_chat.html', {"conversations": list(conversations.values())})


@login_required
@require_POST
def supprimer_conversation(request, conversation):
    EchangeChat.objects.filter(utilisateur=request.user, conversation=conversation).delete()
    messages.success(request, _("Conversation supprimée."))
    return redirect('historique_chat')


def cle_cache_reponse(question, langue):
    texte = " ".join(question.lower().split())
    return "reponse:" + hashlib.sha256(f"{langue}|{texte}".encode()).hexdigest()


def api_chat(request):
    """Reçoit une question (JSON, ou formulaire avec un fichier joint) et renvoie la réponse d'OrientIA.

    Renvoie aussi les documents consultés (sources), l'identifiant de l'échange (pour l'avis 👍/👎)
    et celui de la conversation : les questions suivantes s'appuient sur les échanges précédents.
    """
    from rag.ia import FichierRefuse, texte_du_fichier

    if request.method != "POST":
        return JsonResponse({"erreur": _("Méthode non autorisée")}, status=405)

    fichier = request.FILES.get("fichier")
    if request.content_type and request.content_type.startswith("multipart/"):
        donnees = request.POST
    else:
        try:
            donnees = json.loads(request.body)
        except ValueError:
            donnees = {}
        if not isinstance(donnees, dict):
            donnees = {}
    question = str(donnees.get("question", "")).strip()[:2000]
    conversation = lire_uuid(donnees.get("conversation")) or uuid.uuid4()

    if not question and fichier:
        question = _("Que peux-tu me dire sur ce document pour mon orientation ?")
    if not question:
        return JsonResponse({"erreur": _("Question vide")}, status=400)

    # Problèmes de configuration fréquents : on les explique clairement au lieu de planter
    if not os.getenv("GROQ_API_KEY"):
        return JsonResponse({"erreur": _("OrientIA n'est pas encore configuré : la clé GROQ_API_KEY est vide dans config/.env.")}, status=503)
    if not DocumentChunk.objects.exists():
        return JsonResponse({"erreur": _("Aucun document n'est indexé. Lance d'abord : python manage.py indexer_documents")}, status=503)

    minutes = limite_atteinte(request, 'chat')
    if minutes:
        return reponse_limite(request, minutes)

    # Un visiteur sans compte a besoin d'une session pour que la conversation garde sa mémoire
    if not request.user.is_authenticated and not request.session.session_key:
        request.session.create()

    # Mémoire : les derniers échanges de cette conversation (seulement ceux de la même personne)
    historique = list(echanges_de(request).filter(conversation=conversation).order_by('-date')[:ECHANGES_MEMORISES])[::-1]
    # Si l'élève est connecté, OrientIA adapte sa réponse à son profil
    profil = profil_de(request.user) if request.user.is_authenticated else None
    langue = get_language()

    # Question fréquente d'un visiteur (sans profil, sans fichier, en début de conversation) : réponse déjà connue ?
    cle_cache = cle_cache_reponse(question, langue) if not (profil or fichier or historique) else None
    en_cache = cache.get(cle_cache) if cle_cache else None

    if en_cache:
        reponse, sources = en_cache["reponse"], en_cache["sources"]
    else:
        try:
            document = texte_du_fichier(fichier) if fichier else ""
            chunks = rechercher_chunks_pertinents(question, question_precedente=historique[-1].question if historique else "")
            # OrientIA répond dans la langue du site (français ou anglais)
            reponse = generer_reponse(question, chunks, profil, langue=langue, document=document,
                                      nom_document=fichier.name if fichier else "",
                                      historique=[(e.question, e.reponse) for e in historique])
        except FichierRefuse as e:
            message = (_("Fichier trop lourd (%(n)s Mo maximum).") % {"n": settings.TAILLE_MAX_ENVOI_MO} if str(e) == "trop_lourd"
                       else _("Format non pris en charge : envoie une photo, un PDF ou un fichier texte."))
            return JsonResponse({"erreur": message}, status=400)
        except Exception:
            logger.exception("Erreur lors de l'appel à Groq")
            return JsonResponse({"erreur": _("OrientIA est momentanément indisponible. Réessaie dans quelques secondes.")}, status=503)
        sources = sources_de(chunks)
        if cle_cache:
            cache.set(cle_cache, {"reponse": reponse, "sources": sources}, settings.DUREE_CACHE_REPONSES)

    echange = EchangeChat.objects.create(
        conversation=conversation,
        utilisateur=request.user if request.user.is_authenticated else None,
        cle_session="" if request.user.is_authenticated else request.session.session_key,
        question=question, reponse=reponse, sources=sources, langue=langue,
        nom_document=fichier.name[:255] if fichier else "",
    )
    return JsonResponse({"reponse": reponse, "sources": sources, "echange": echange.pk, "conversation": str(conversation)})


@require_POST
def api_avis(request):
    """👍 / 👎 sur une réponse d'OrientIA. Recliquer sur le même bouton retire l'avis."""
    try:
        donnees = json.loads(request.body)
        echange_id, avis = int(donnees.get("echange")), int(donnees.get("avis"))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"erreur": _("Requête invalide.")}, status=400)
    if avis not in (1, -1):
        return JsonResponse({"erreur": _("Requête invalide.")}, status=400)
    echange = echanges_de(request).filter(pk=echange_id).first()
    if echange is None:
        return JsonResponse({"erreur": _("Échange introuvable.")}, status=404)
    echange.avis = None if echange.avis == avis else avis
    echange.save(update_fields=["avis"])
    return JsonResponse({"avis": echange.avis})


TAILLE_MIN_AUDIO = 1000  # octets : en dessous, l'enregistrement ne contient pas de parole


@require_POST
def api_transcrire(request):
    """Transforme un message vocal en texte (bouton micro du chat et de l'emploi du temps)."""
    from rag.ia import transcrire_audio

    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"erreur": _("Aucun enregistrement reçu.")}, status=400)
    if audio.size < TAILLE_MIN_AUDIO:
        return JsonResponse({"erreur": _("Enregistrement trop court : clique sur le micro, parle, puis clique à nouveau.")}, status=400)
    if audio.size > settings.TAILLE_MAX_ENVOI_MO * 1024 * 1024:
        return JsonResponse({"erreur": _("Enregistrement trop long.")}, status=400)
    if not os.getenv("GROQ_API_KEY"):
        return JsonResponse({"erreur": _("OrientIA n'est pas encore configuré : la clé GROQ_API_KEY est vide dans config/.env.")}, status=503)

    minutes = limite_atteinte(request, 'transcription')
    if minutes:
        return reponse_limite(request, minutes)
    try:
        texte = transcrire_audio(audio, langue=get_language())
    except Exception:
        logger.exception("Transcription vocale impossible")
        return JsonResponse({"erreur": _("Je n'ai pas réussi à comprendre l'enregistrement. Réessaie en parlant plus près du micro.")}, status=503)
    if not texte:
        # Silence, ou phrase « fantôme » inventée par Whisper : on n'envoie rien à OrientIA
        return JsonResponse({"erreur": _("Je n'ai rien entendu. Parle plus près du micro, puis réessaie.")}, status=422)
    return JsonResponse({"texte": texte})


def types_etablissements():
    """Libellé affiché de chaque type d'établissement (dans la langue de l'élève)."""
    return {
        'universite': _("Université d'État"),
        'grande_ecole': _("Grande école publique"),
        'ipes': _("Institut privé (IPES)"),
        'institut': _("Institut"),
    }


def carte(request):
    libelles = types_etablissements()
    donnees = [
        {
            "nom": e.nom,
            "type": libelles.get(e.type_etablissements, e.type_etablissements.capitalize()),
            "adresse": e.adresse,
            "region": e.region,
            "approx": e.position_approximative,
            "lat": e.latitude,
            "lon": e.longitude,
        }
        for e in Etablissement.objects.order_by('nom')
    ]
    return render(request, 'interface/carte.html', {"etablissements": donnees})


def envoyer_confirmation_email(request, user):
    """Enregistre l'adresse auprès d'allauth (utile pour « mot de passe oublié ») et envoie le lien de confirmation."""
    from allauth.account.utils import setup_user_email
    try:
        adresse = setup_user_email(request, user, [])
        if adresse and settings.EMAIL_ACTIF:
            adresse.send_confirmation(request, signup=True)
    except Exception:
        # L'inscription ne doit jamais échouer à cause de l'email : on le note dans le journal
        logger.exception("Envoi de l'email de confirmation impossible")


def inscription(request):
    """Inscription minimale : le profil (série, intérêts, région) est demandé après, dans l'accueil progressif."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    contexte = {"google_actif": google_actif()}

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip().lower()
        password = request.POST.get("password", "")

        erreurs = []
        if not username or not email or not password:
            erreurs.append(_("Tous les champs sont obligatoires."))
        if not request.POST.get("consentement"):
            erreurs.append(_("Accepte les conditions d'utilisation et la politique de confidentialité pour créer ton compte."))
        if username and User.objects.filter(username__iexact=username).exists():
            erreurs.append(_("Ce nom d'utilisateur est déjà pris."))
        if email and User.objects.filter(email__iexact=email).exists():
            erreurs.append(_("Un compte existe déjà avec cet email. Connecte-toi plutôt."))
        if password:
            try:
                validate_password(password, User(username=username, email=email))
            except ValidationError as e:
                erreurs.extend(e.messages)

        if erreurs:
            contexte.update({"erreurs": erreurs, "username_saisi": username, "email_saisi": email,
                             "consentement_coche": bool(request.POST.get("consentement"))})
            return render(request, 'interface/inscription.html', contexte)

        user = User.objects.create_user(username=username, email=email, password=password)
        # La langue dans laquelle l'élève s'est inscrit devient celle de son profil ; on garde la date du consentement
        Profil.objects.filter(utilisateur=user).update(langue=get_language(), date_consentement=timezone.now())
        envoyer_confirmation_email(request, user)
        login(request, user, backend=BACKEND_CLASSIQUE)
        return redirect('bienvenue')

    return render(request, 'interface/inscription.html', contexte)


def connexion(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    contexte = {"google_actif": google_actif()}

    if request.method == "POST":
        identifiant = request.POST.get("identifiant", "").strip()
        password = request.POST.get("password", "")

        # On accepte le nom d'utilisateur ou l'email
        username = identifiant
        if "@" in identifiant:
            compte = User.objects.filter(email__iexact=identifiant).first()
            if compte:
                username = compte.username

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user, backend=BACKEND_CLASSIQUE)
            # On retrouve le site dans la langue enregistrée dans son profil
            reponse = redirect(adresse_sure(request, request.GET.get("next"), 'dashboard'))
            return memoriser_langue(reponse, profil_de(user).langue)

        contexte.update({
            "erreur": _("Identifiant ou mot de passe incorrect."),
            "identifiant_saisi": identifiant,
        })

    return render(request, 'interface/connexion.html', contexte)


def deconnexion(request):
    logout(request)
    return redirect('accueil')


@login_required
def bienvenue(request):
    """Accueil progressif : chaque étape est enregistrée dès qu'on clique sur « Suivant », et tout peut être passé.

    La première question (francophone / anglophone) choisit la langue des questions suivantes
    et les séries proposées (Baccalauréat ou GCE A Level).
    """
    profil = profil_de(request.user)

    if request.method == "POST":
        ancienne_langue = profil.langue
        ancien_sous_systeme = profil.sous_systeme
        # Valeurs autorisées pour chaque champ (None = texte libre)
        valeurs_autorisees = {
            "sous_systeme": dict(Profil.SOUS_SYSTEMES),
            "type_profil": dict(Profil.TYPE_PROFIL_CHOICES),
            "serie_bac": dict(Profil.SERIE_BAC_CHOICES),
            "region": Profil.REGIONS,
            "centres_interet": None,
            "projet_etudes": None,
            "ecole_souhaitee": None,
        }
        for champ, autorisees in valeurs_autorisees.items():
            valeur = request.POST.get(champ, "").strip()[:255]
            if valeur and (autorisees is None or valeur in autorisees):
                setattr(profil, champ, valeur)
        annee = request.POST.get("annee_naissance", "")
        if annee.isdigit() and int(annee) in Profil.annees_de_naissance():
            profil.annee_naissance = int(annee)

        # Quand l'élève choisit son sous-système, la langue suit : anglophone → anglais, francophone → français
        if profil.sous_systeme and profil.sous_systeme != ancien_sous_systeme:
            profil.langue = 'en' if profil.sous_systeme == 'anglophone' else 'fr'
        if profil.sous_systeme:
            # Une série de l'autre sous-système n'a plus de sens : on l'efface
            series_valides = dict(Profil.SERIES_GCE if profil.sous_systeme == 'anglophone' else Profil.SERIES_BAC)
            if profil.serie_bac and profil.serie_bac != 'autre' and profil.serie_bac not in series_valides:
                profil.serie_bac = ''
        if request.POST.get("terminer"):
            profil.accueil_termine = True
        profil.save()

        langue_changee = profil.langue != ancienne_langue or profil.langue != get_language()
        # Appel en arrière-plan (étape intermédiaire) : on renvoie la progression,
        # et on demande de recharger la page si la langue vient de changer
        if request.headers.get("X-Requested-With") == "fetch":
            reponse = JsonResponse({"progression": profil.progression(), "recharger": langue_changee})
        else:
            reponse = redirect('dashboard')
        return memoriser_langue(reponse, profil.langue)

    anglophone = profil.sous_systeme == 'anglophone'
    return render(request, 'interface/bienvenue.html', {
        "profil": profil,
        "series": (Profil.SERIES_GCE if anglophone else Profil.SERIES_BAC) + [('autre', _('Autre / En cours de détermination'))],
        "regions": [(r, Profil.NOMS_REGIONS[r]) for r in Profil.REGIONS],
        # Centres d'intérêt : valeur enregistrée (en français) et libellé affiché dans la langue de l'élève
        "interets": [
            ["Mathématiques", _("Mathématiques")], ["Informatique", _("Informatique")],
            ["Physique-Chimie", _("Physique-Chimie")], ["Biologie", _("Biologie")],
            ["Santé / Médecine", _("Santé / Médecine")], ["Agriculture", _("Agriculture")],
            ["Génie civil", _("Génie civil")], ["Économie / Gestion", _("Économie / Gestion")],
            ["Commerce", _("Commerce")], ["Droit", _("Droit")], ["Langues", _("Langues")],
            ["Lettres", _("Lettres")], ["Communication", _("Communication")], ["Arts", _("Arts")],
        ],
        "ecoles": Etablissement.objects.order_by("nom").values_list("nom", flat=True),
        "annees_naissance": Profil.annees_de_naissance(),
        "idees_projet": [
            _("Faire une grande école"), _("Aller à l'université"), _("Faire un BTS / HND"),
            _("Devenir ingénieur·e"), _("Travailler dans la santé"), _("Je ne sais pas encore"),
        ],
        "etape_depart": request.GET.get("etape", "1"),
    })


@login_required
def dashboard(request):
    profil = profil_de(request.user)
    if not profil.accueil_termine:
        return redirect('bienvenue')
    # Idées de questions personnalisées selon le profil
    premier_interet = profil.centres_interet.split(",")[0].strip() if profil.centres_interet else _("informatique")
    diplome = profil.get_serie_bac_display() if profil.serie_bac and profil.serie_bac != 'autre' else _("mon bac")
    idees = [
        _("Comment entrer à %(ecole)s ?") % {"ecole": profil.ecole_souhaitee} if profil.ecole_souhaitee
        else _("Quelles écoles après %(diplome)s ?") % {"diplome": diplome},
        _("Comment se passent les concours d'entrée ?"),
        _("Quels métiers en %(domaine)s ?") % {"domaine": premier_interet.lower()},
    ]
    # Concours suivis, du plus urgent au moins urgent
    concours_suivis = sorted(
        request.user.concours_suivis.select_related('etablissement'),
        key=lambda c: c.prochaine_echeance()[1] if c.prochaine_echeance() else date.max,
    )

    # Écoles les plus proches dans les domaines de l'élève
    point, lieu = position_par_defaut(profil)
    domaines = domaines_du_profil(profil)
    ecoles = ecoles_proches(point, domaines=domaines, limite=3) if point is not None and domaines else []

    # Dernier test d'orientation : les 3 domaines en tête
    dernier_test = request.user.resultats_test.first()
    noms_domaines = dict(Filiere.DOMAINES)
    domaines_test = [(noms_domaines[d], dernier_test.scores[d]) for d in dernier_test.domaines_principaux(3)] if dernier_test else []

    return render(request, 'interface/dashboard.html', {
        "profil": profil,
        "idees": idees,
        "concours_suivis": concours_suivis,
        "ecoles": ecoles,
        "lieu": lieu,
        "dernier_test": dernier_test,
        "domaines_test": domaines_test,
        "favoris": profil.ecoles_favorites.all(),
    })
