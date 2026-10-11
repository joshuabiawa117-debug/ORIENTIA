"""Droits de l'élève sur ses données : tout télécharger, ou supprimer son compte."""
import json

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

# Données exportées : (titre dans le fichier, relation depuis l'utilisateur, champs gardés)
SECTIONS = [
    ("parcours", "parcours", ["statut", "filiere__nom", "etablissement__nom", "semestre"]),
    ("voeux", "choix_filieres", ["rang", "filiere__nom", "etablissement__nom", "etape", "remarque"]),
    ("avancement_matieres", "avancements", ["unite__intitule", "statut"]),
    ("notes", "notes", ["matiere", "semestre", "valeur", "coefficient", "type_note", "date"]),
    ("taches", "taches", ["titre", "echeance", "faite"]),
    ("emploi_du_temps", "creneaux", ["type_creneau", "jour", "debut", "fin", "intitule"]),
    ("seances_revision", "seances", ["jour", "debut", "fin", "matiere"]),
    ("tests_orientation", "resultats_test", ["scores", "date"]),
    ("concours_suivis", "concours_suivis", ["nom"]),
    ("questions_communaute", "sujets", ["titre", "contenu", "date_creation"]),
    ("reponses_communaute", "reponses", ["sujet__titre", "contenu", "date_creation"]),
    ("conversations_orientia", "echanges_chat", ["conversation", "question", "reponse", "sources", "nom_document", "avis", "date"]),
]


def lignes(queryset, champs):
    """Valeurs des champs demandés ; un champ absent du modèle est simplement ignoré."""
    modele_champs = {f.name for f in queryset.model._meta.get_fields()}
    gardes = [c for c in champs if c.split("__")[0] in modele_champs]
    return list(queryset.values(*gardes))


def exporter(user):
    from communaute.models import MessagePrive
    from interface.views import profil_de

    profil = profil_de(user)
    donnees = {
        "export_du": timezone.now(),
        "compte": {"nom_utilisateur": user.username, "email": user.email, "prenom": user.first_name,
                   "inscription": user.date_joined, "derniere_connexion": user.last_login},
        "profil": {
            "langue": profil.langue, "sous_systeme": profil.sous_systeme, "serie_bac": profil.serie_bac,
            "centres_interet": profil.centres_interet, "region": profil.region, "projet_etudes": profil.projet_etudes,
            "ecole_souhaitee": profil.ecole_souhaitee, "annee_naissance": profil.annee_naissance,
            "badge": profil.badge, "consentement": profil.date_consentement,
            "ecoles_favorites": list(profil.ecoles_favorites.values_list("nom", flat=True)),
        },
    }
    for titre, relation, champs in SECTIONS:
        gestionnaire = getattr(user, relation, None)
        if gestionnaire is None:
            continue
        if hasattr(gestionnaire, "all"):
            donnees[titre] = lignes(gestionnaire.all(), champs)
        else:  # relation un-à-un (parcours)
            donnees[titre] = lignes(type(gestionnaire).objects.filter(pk=gestionnaire.pk), champs)
    donnees["messages_prives"] = [
        {"de": m.expediteur.username, "a": m.destinataire.username, "contenu": m.contenu, "date": m.date}
        for m in MessagePrive.objects.filter(Q(expediteur=user) | Q(destinataire=user)).select_related("expediteur", "destinataire")
    ]
    return donnees


@login_required
def mes_donnees(request):
    """Page « Mes données » : téléchargement et suppression du compte."""
    if request.method == "POST" and request.POST.get("action") == "telecharger":
        contenu = json.dumps(exporter(request.user), cls=DjangoJSONEncoder, ensure_ascii=False, indent=2)
        reponse = HttpResponse(contenu, content_type="application/json; charset=utf-8")
        reponse["Content-Disposition"] = f'attachment; filename="orientia-mes-donnees-{request.user.username}.json"'
        return reponse

    if request.method == "POST" and request.POST.get("action") == "supprimer":
        confirmation = request.POST.get("confirmation", "").strip().upper()
        mot_de_passe_ok = not request.user.has_usable_password() or request.user.check_password(request.POST.get("password", ""))
        if confirmation not in ("SUPPRIMER", "DELETE") or not mot_de_passe_ok:
            messages.error(request, _("Suppression annulée : tape SUPPRIMER et ton mot de passe pour confirmer."))
            return redirect("mes_donnees")
        user = request.user
        logout(request)
        user.delete()  # supprime aussi profil, notes, messages, conversations... (suppression en cascade)
        messages.success(request, _("Ton compte et toutes tes données ont été supprimés. Bonne continuation !"))
        return redirect("accueil")

    return render(request, "interface/mes_donnees.html")
