from datetime import date, datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from etablissements.models import Etablissement
from interface.limites import limite_atteinte, message_limite
from orientation.models import Filiere, UniteEnseignement

from .models import JOURS, AvancementMatiere, ChoixFiliere, Creneau, Note, SeanceRevision, Tache
from .services import FORMULES, bilan_notes, parcours_de, positionner, proposer_emplois_du_temps


# ---------- Gestion de filière ----------

@login_required
def ma_filiere(request):
    parcours = parcours_de(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'statut' and request.POST.get('statut') in dict(parcours.STATUTS):
            parcours.statut = request.POST['statut']
            parcours.save()
        elif action == 'inscription':
            parcours.filiere = Filiere.objects.filter(pk=request.POST.get('filiere') or 0).first()
            parcours.etablissement = Etablissement.objects.filter(pk=request.POST.get('etablissement') or 0).first()
            try:
                parcours.semestre = min(max(int(request.POST.get('semestre', '')), 1), 10)
            except ValueError:
                parcours.semestre = None
            parcours.save()
            messages.success(request, _("Ta filière est enregistrée."))
        elif action == 'choix':
            filiere = Filiere.objects.filter(pk=request.POST.get('filiere') or 0).first()
            try:
                rang = int(request.POST.get('rang', ''))
            except ValueError:
                rang = 0
            if filiere and 1 <= rang <= 3:
                ChoixFiliere.objects.update_or_create(
                    utilisateur=request.user, rang=rang,
                    defaults={
                        'filiere': filiere,
                        'etablissement': Etablissement.objects.filter(pk=request.POST.get('etablissement') or 0).first(),
                        'etape': request.POST.get('etape') if request.POST.get('etape') in dict(ChoixFiliere.ETAPES) else 'renseigne',
                        'remarque': request.POST.get('remarque', '')[:255],
                    },
                )
                messages.success(request, _("Ton vœu n°%(rang)s est enregistré.") % {'rang': rang})
        elif action == 'supprimer_choix':
            ChoixFiliere.objects.filter(utilisateur=request.user, pk=request.POST.get('pk')).delete()
        elif action == 'avancement':
            unite = get_object_or_404(UniteEnseignement, pk=request.POST.get('unite'))
            if request.POST.get('statut') in dict(AvancementMatiere.STATUTS):
                AvancementMatiere.objects.update_or_create(
                    utilisateur=request.user, unite=unite, defaults={'statut': request.POST['statut']})
        return redirect('espace:filiere')

    # Matières du semestre en cours, avec leur avancement
    unites = []
    if parcours.filiere_id and parcours.semestre:
        statuts = dict(AvancementMatiere.objects.filter(utilisateur=request.user).values_list('unite_id', 'statut'))
        for ue in UniteEnseignement.objects.filter(filiere_id=parcours.filiere_id, semestre=parcours.semestre):
            unites.append({'ue': ue, 'statut': statuts.get(ue.pk, 'a_faire')})
    validees = sum(1 for u in unites if u['statut'] == 'validee')

    choix = {c.rang: c for c in ChoixFiliere.objects.filter(utilisateur=request.user).select_related('filiere', 'etablissement')}
    return render(request, 'espace/filiere.html', {
        'parcours': parcours,
        'filieres': Filiere.objects.order_by('nom'),
        'etablissements': Etablissement.objects.order_by('nom'),
        'unites': unites,
        'progression': round(100 * validees / len(unites)) if unites else 0,
        'semestres_dispo': sorted(set(UniteEnseignement.objects.filter(filiere_id=parcours.filiere_id).values_list('semestre', flat=True))) if parcours.filiere_id else [],
        'voeux': [(rang, choix.get(rang)) for rang in (1, 2, 3)],
        'etapes': ChoixFiliere.ETAPES,
        'statuts_matiere': AvancementMatiere.STATUTS,
    })


# ---------- Emploi du temps ----------

def lire_heure(valeur):
    try:
        return datetime.strptime(valeur, '%H:%M').time()
    except (TypeError, ValueError):
        return None


@login_required
def emploi_du_temps(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'ajouter':
            debut, fin = lire_heure(request.POST.get('debut')), lire_heure(request.POST.get('fin'))
            type_creneau = request.POST.get('type_creneau')
            try:
                jour = int(request.POST.get('jour', ''))
            except ValueError:
                jour = -1
            if type_creneau in ('cours', 'dispo') and 0 <= jour <= 6 and debut and fin and debut < fin:
                Creneau.objects.create(utilisateur=request.user, type_creneau=type_creneau, jour=jour,
                                       debut=debut, fin=fin, intitule=request.POST.get('intitule', '')[:120])
            else:
                messages.error(request, _("Créneau invalide : vérifie le jour et que l'heure de fin est après l'heure de début."))
        elif action == 'supprimer':
            Creneau.objects.filter(utilisateur=request.user, pk=request.POST.get('pk')).delete()
        elif action == 'choisir':
            proposition = next((p for p in proposer_emplois_du_temps(request.user) if p['cle'] == request.POST.get('formule')), None)
            if proposition:
                with transaction.atomic():
                    SeanceRevision.objects.filter(utilisateur=request.user).delete()
                    SeanceRevision.objects.bulk_create([
                        SeanceRevision(utilisateur=request.user, formule=proposition['cle'], **s) for s in proposition['seances']
                    ])
                messages.success(request, _("Ton emploi du temps « %(nom)s » est enregistré !") % {'nom': proposition['nom']})
            return redirect('espace:emploi_du_temps')
        elif action == 'effacer_planning':
            SeanceRevision.objects.filter(utilisateur=request.user).delete()
        suivant = 'espace:emploi_du_temps'
        return redirect(suivant)

    creneaux = list(Creneau.objects.filter(utilisateur=request.user))
    seances = list(SeanceRevision.objects.filter(utilisateur=request.user))

    def elements(liste, nature):
        return positionner([
            {'jour': x.jour, 'debut': x.debut, 'fin': x.fin, 'nature': nature, 'pk': x.pk,
             'titre': getattr(x, 'intitule', '') or getattr(x, 'matiere', '')}
            for x in liste
        ])

    grille = elements([c for c in creneaux if c.type_creneau == 'cours'], 'cours') + elements(seances, 'revision')
    if not seances:
        grille += elements([c for c in creneaux if c.type_creneau == 'dispo'], 'dispo')

    propositions = []
    if request.GET.get('propositions'):
        propositions = proposer_emplois_du_temps(request.user)
        for p in propositions:
            p['grille'] = positionner([{**s, 'nature': 'revision', 'titre': s['matiere']} for s in p['seances']])

    formule_choisie = next((f for f in FORMULES if seances and f['cle'] == seances[0].formule), None)
    return render(request, 'espace/emploi_du_temps.html', {
        'jours': JOURS,
        'heures': range(7, 21),
        'creneaux': creneaux,
        'grille': grille,
        'propositions': propositions,
        'nb_dispos': sum(1 for c in creneaux if c.type_creneau == 'dispo'),
        'formule_choisie': formule_choisie,
        'demande_propositions': bool(request.GET.get('propositions')),
    })


# ---------- Suivi : notes, avancement, tâches, démarches ----------

class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['matiere', 'semestre', 'valeur', 'coefficient', 'type_note', 'date']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


@login_required
def suivi(request):
    parcours = parcours_de(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'note':
            form = NoteForm(request.POST)
            if form.is_valid():
                note = form.save(commit=False)
                note.utilisateur = request.user
                # Relier la note à la matière officielle si son nom correspond
                if parcours.filiere_id:
                    note.unite = UniteEnseignement.objects.filter(filiere_id=parcours.filiere_id, intitule__iexact=note.matiere).first()
                note.save()
                messages.success(request, _("Note ajoutée."))
            else:
                messages.error(request, _("Note invalide : elle doit être comprise entre 0 et 20."))
        elif action == 'supprimer_note':
            Note.objects.filter(utilisateur=request.user, pk=request.POST.get('pk')).delete()
        elif action == 'tache':
            titre = request.POST.get('titre', '').strip()[:200]
            if titre:
                try:
                    echeance = date.fromisoformat(request.POST.get('echeance', ''))
                except ValueError:
                    echeance = None
                Tache.objects.create(utilisateur=request.user, titre=titre, echeance=echeance)
        elif action == 'basculer_tache':
            tache = get_object_or_404(Tache, utilisateur=request.user, pk=request.POST.get('pk'))
            tache.faite = not tache.faite
            tache.save(update_fields=['faite'])
        elif action == 'supprimer_tache':
            Tache.objects.filter(utilisateur=request.user, pk=request.POST.get('pk')).delete()
        return redirect('espace:suivi')

    taches = list(Tache.objects.filter(utilisateur=request.user))
    faites = sum(1 for t in taches if t.faite)

    # Avancement des matières du semestre (étudiant inscrit)
    avancement = None
    if parcours.filiere_id and parcours.semestre:
        unites = UniteEnseignement.objects.filter(filiere_id=parcours.filiere_id, semestre=parcours.semestre)
        statuts = dict(AvancementMatiere.objects.filter(utilisateur=request.user, unite__in=unites).values_list('unite_id', 'statut'))
        total = unites.count()
        avancement = {
            'total': total,
            'validees': sum(1 for s in statuts.values() if s == 'validee'),
            'en_cours': sum(1 for s in statuts.values() if s == 'en_cours'),
        }
        avancement['pourcentage'] = round(100 * avancement['validees'] / total) if total else 0

    matieres_suggerees = []
    if parcours.filiere_id and parcours.semestre:
        matieres_suggerees = list(UniteEnseignement.objects.filter(filiere_id=parcours.filiere_id, semestre=parcours.semestre)
                                  .values_list('intitule', flat=True))

    return render(request, 'espace/suivi.html', {
        'parcours': parcours,
        'bilan': bilan_notes(request.user),
        'notes': Note.objects.filter(utilisateur=request.user)[:30],
        'form_note': NoteForm(initial={'date': date.today(), 'semestre': parcours.semestre or 1}),
        'matieres_suggerees': matieres_suggerees,
        'taches': taches,
        'taches_pourcentage': round(100 * faites / len(taches)) if taches else 0,
        'aujourdhui': date.today(),
        'avancement': avancement,
        'voeux': ChoixFiliere.objects.filter(utilisateur=request.user).select_related('filiere', 'etablissement'),
    })


@login_required
@require_POST
def importer_emploi(request):
    """Ajoute des créneaux à partir d'une photo / d'un PDF d'emploi du temps ou d'une description (écrite ou dictée)."""
    import logging
    import os

    from rag.ia import FichierRefuse, extraire_creneaux, lire_fichier

    if not os.getenv("GROQ_API_KEY"):
        messages.error(request, _("L'import utilise OrientIA : ajoute la clé GROQ_API_KEY dans config/.env."))
        return redirect('espace:emploi_du_temps')

    fichier = request.FILES.get('fichier')
    texte = request.POST.get('texte', '').strip()
    if not fichier and not texte:
        messages.error(request, _("Choisis un fichier ou décris ton emploi du temps."))
        return redirect('espace:emploi_du_temps')

    minutes = limite_atteinte(request, 'import_emploi')
    if minutes:
        messages.error(request, message_limite(request, minutes))
        return redirect('espace:emploi_du_temps')

    try:
        creneaux = []
        if fichier:
            contenu, est_image, octets, type_mime = lire_fichier(fichier)
            creneaux += extraire_creneaux(image=(octets, type_mime)) if est_image else extraire_creneaux(texte=contenu)
        if texte:
            creneaux += extraire_creneaux(texte=texte)
    except FichierRefuse as e:
        messages.error(request, _("Fichier trop lourd (8 Mo maximum).") if str(e) == 'trop_lourd'
                       else _("Format non pris en charge : envoie une photo, un PDF ou un fichier texte."))
        return redirect('espace:emploi_du_temps')
    except Exception:
        logging.getLogger(__name__).exception("Import d'emploi du temps impossible")
        messages.error(request, _("OrientIA n'a pas réussi à lire ton emploi du temps. Réessaie ou ajoute les créneaux à la main."))
        return redirect('espace:emploi_du_temps')

    ajoutes = 0
    for c in creneaux:
        try:
            jour = int(c.get('jour'))
            debut, fin = lire_heure(str(c.get('debut', ''))[:5]), lire_heure(str(c.get('fin', ''))[:5])
        except (TypeError, ValueError, AttributeError):
            continue
        type_creneau = c.get('type') if c.get('type') in ('cours', 'dispo') else 'cours'
        if 0 <= jour <= 6 and debut and fin and debut < fin:
            Creneau.objects.get_or_create(utilisateur=request.user, type_creneau=type_creneau, jour=jour, debut=debut, fin=fin,
                                          defaults={'intitule': str(c.get('intitule') or '')[:120]})
            ajoutes += 1
    if ajoutes:
        messages.success(request, _("%(n)s créneau(x) ajouté(s) à ton emploi du temps. Vérifie-les dans la liste.") % {'n': ajoutes})
    else:
        messages.error(request, _("Aucun créneau trouvé. Précise les jours et les heures (ex : lundi 8h-10h maths)."))
    return redirect('espace:emploi_du_temps')
