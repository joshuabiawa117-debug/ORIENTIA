from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Exists, OuterRef, Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l
from django.views.decorators.http import require_POST

from etablissements.models import Etablissement
from interface.limites import limite_atteinte, message_limite
from interface.views import adresse_sure
from orientation.models import Filiere

from .models import Blocage, MessagePrive, Reponse, Signalement, Sujet
from .moderation import masquer_si_trop_signale, raison_refus_message


class SujetForm(forms.ModelForm):
    class Meta:
        model = Sujet
        fields = ['titre', 'contenu', 'filiere', 'etablissement']
        labels = {
            'titre': _l('Ta question'),
            'contenu': _l('Donne quelques détails'),
            'filiere': _l('Filière concernée (facultatif)'),
            'etablissement': _l('École concernée (facultatif)'),
        }
        widgets = {
            'titre': forms.TextInput(attrs={'placeholder': _l("Ex : Quelles matières faut-il travailler pour le concours de l'ENSP ?"), 'maxlength': 200}),
            'contenu': forms.Textarea(attrs={'rows': 6, 'placeholder': _l("Explique ta situation : ta série, ce que tu as déjà trouvé, ce qui te bloque…")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['filiere'].queryset = Filiere.objects.order_by('nom')
        self.fields['filiere'].empty_label = _('— Aucune en particulier —')
        self.fields['etablissement'].queryset = Etablissement.objects.order_by('nom')
        self.fields['etablissement'].empty_label = _('— Aucune en particulier —')
        for champ in self.fields.values():
            champ.widget.attrs['class'] = 'field-input'


def liste(request):
    sujets = (Sujet.objects.filter(masque=False)
              .select_related('auteur', 'filiere', 'etablissement')
              .annotate(nb_reponses=Count('reponses', filter=Q(reponses__masque=False), distinct=True),
                        resolu=Exists(Reponse.objects.filter(sujet=OuterRef('pk'), meilleure=True))))

    q = request.GET.get('q', '').strip()
    domaine = request.GET.get('domaine', '')
    onglet = request.GET.get('onglet', 'recentes')

    if q:
        sujets = sujets.filter(Q(titre__icontains=q) | Q(contenu__icontains=q))
    if domaine:
        sujets = sujets.filter(filiere__domaine=domaine)
    if onglet == 'sans_reponse':
        sujets = sujets.filter(nb_reponses=0)
    elif onglet == 'resolues':
        sujets = sujets.filter(resolu=True)

    return render(request, 'communaute/liste.html', {
        'sujets': sujets[:50],
        'q': q,
        'domaine': domaine,
        'onglet': onglet,
        'domaines': Filiere.DOMAINES,
        'nb_total': Sujet.objects.filter(masque=False).count(),
        'nb_membres': Sujet.objects.filter(masque=False).values('auteur').distinct().count(),
    })


@login_required
def nouveau(request):
    form = SujetForm(request.POST or None, initial={
        'filiere': request.GET.get('filiere'),
        'etablissement': request.GET.get('etablissement'),
    })
    if request.method == 'POST' and form.is_valid():
        minutes = limite_atteinte(request, 'sujet')
        if minutes:
            messages.error(request, message_limite(request, minutes))
            return render(request, 'communaute/nouveau.html', {'form': form})
        sujet = form.save(commit=False)
        sujet.auteur = request.user
        sujet.save()
        messages.success(request, _("Ta question est en ligne ! Les autres élèves vont pouvoir te répondre."))
        return redirect('communaute:detail', pk=sujet.pk)
    return render(request, 'communaute/nouveau.html', {'form': form})


def detail(request, pk):
    sujet = get_object_or_404(Sujet.objects.select_related('auteur__profil', 'filiere', 'etablissement'), pk=pk)
    # Une question masquée par la modération n'est visible que par son auteur et l'équipe
    if sujet.masque and request.user != sujet.auteur and not request.user.is_staff:
        raise Http404
    reponses = (sujet.reponses.filter(masque=False).select_related('auteur__profil')
                .annotate(nb_votes=Count('votes')))
    mes_votes = set()
    if request.user.is_authenticated:
        mes_votes = set(request.user.reponses_aimees.filter(sujet=sujet).values_list('pk', flat=True))
    similaires = []
    if sujet.filiere_id:
        similaires = Sujet.objects.filter(filiere=sujet.filiere, masque=False).exclude(pk=sujet.pk)[:4]
    return render(request, 'communaute/detail.html', {
        'sujet': sujet,
        'reponses': reponses,
        'mes_votes': mes_votes,
        'similaires': similaires,
    })


@login_required
@require_POST
def repondre(request, pk):
    sujet = get_object_or_404(Sujet, pk=pk)
    contenu = request.POST.get('contenu', '').strip()
    minutes = limite_atteinte(request, 'reponse') if len(contenu) >= 2 else None
    if len(contenu) < 2:
        messages.error(request, _("Ta réponse est vide."))
    elif minutes:
        messages.error(request, message_limite(request, minutes))
    else:
        Reponse.objects.create(sujet=sujet, auteur=request.user, contenu=contenu[:5000])
        messages.success(request, _("Merci pour ta réponse !"))
    return redirect('communaute:detail', pk=pk)


@login_required
@require_POST
def voter(request, pk):
    """Ajoute ou retire un « utile » sur une réponse (appel en arrière-plan)."""
    reponse = get_object_or_404(Reponse, pk=pk)
    if reponse.auteur_id == request.user.id:
        return JsonResponse({'erreur': _("Tu ne peux pas voter pour ta propre réponse.")}, status=400)
    if reponse.votes.filter(pk=request.user.pk).exists():
        reponse.votes.remove(request.user)
        aime = False
    else:
        reponse.votes.add(request.user)
        aime = True
    return JsonResponse({'aime': aime, 'votes': reponse.votes.count()})


@login_required
@require_POST
def meilleure(request, pk):
    """L'auteur de la question choisit la meilleure réponse (une seule à la fois)."""
    reponse = get_object_or_404(Reponse.objects.select_related('sujet'), pk=pk)
    if reponse.sujet.auteur_id != request.user.id:
        return HttpResponseForbidden(_("Seul l'auteur de la question peut choisir la meilleure réponse."))
    deja = reponse.meilleure
    reponse.sujet.reponses.update(meilleure=False)
    if not deja:
        reponse.meilleure = True
        reponse.save(update_fields=['meilleure'])
    return redirect('communaute:detail', pk=reponse.sujet_id)


# ---------- Profils des membres et messages privés ----------

def membre(request, username):
    """Page publique d'un membre : ses questions, ses réponses et un bouton pour lui écrire."""
    from django.contrib.auth import get_user_model
    personne = get_object_or_404(get_user_model().objects.select_related('profil'), username=username, is_active=True)
    contexte = {
        'membre': personne,
        'sujets': personne.sujets.filter(masque=False)[:10],
        'nb_reponses': personne.reponses.filter(masque=False).count(),
        'nb_meilleures': personne.reponses.filter(meilleure=True, masque=False).count(),
    }
    if request.user.is_authenticated and request.user != personne:
        contexte['refus_message'] = raison_refus_message(request.user, personne)
        contexte['age_manquant'] = not getattr(getattr(request.user, 'profil', None), 'annee_naissance', None)
        contexte['bloque'] = Blocage.objects.filter(bloqueur=request.user, bloque=personne).exists()
    return render(request, 'communaute/membre.html', contexte)


@login_required
def messagerie(request):
    """Boîte de réception : une ligne par conversation, la plus récente en haut."""
    conversations = {}
    for m in (MessagePrive.objects.filter(Q(expediteur=request.user) | Q(destinataire=request.user))
              .select_related('expediteur', 'destinataire').order_by('-date')):
        autre = m.destinataire if m.expediteur_id == request.user.id else m.expediteur
        conv = conversations.setdefault(autre.pk, {'autre': autre, 'dernier': m, 'non_lus': 0})
        if m.destinataire_id == request.user.id and not m.lu:
            conv['non_lus'] += 1
    return render(request, 'communaute/messagerie.html', {'conversations': list(conversations.values())})


@login_required
def conversation(request, username):
    """Fil de discussion privé avec un membre ; envoi d'un nouveau message."""
    from django.contrib.auth import get_user_model

    autre = get_object_or_404(get_user_model().objects.select_related('profil'), username=username, is_active=True)
    if autre == request.user:
        messages.error(request, _("Tu ne peux pas t'écrire à toi-même."))
        return redirect('communaute:messagerie')
    refus = raison_refus_message(request.user, autre)

    if request.method == 'POST':
        contenu = request.POST.get('contenu', '').strip()
        minutes = limite_atteinte(request, 'message_prive') if contenu and not refus else None
        if refus:
            messages.error(request, refus)
        elif minutes:
            messages.error(request, message_limite(request, minutes))
        elif contenu:
            MessagePrive.objects.create(expediteur=request.user, destinataire=autre, contenu=contenu[:3000])
        return redirect('communaute:conversation', username=username)

    fil = (MessagePrive.objects.filter(Q(expediteur=request.user, destinataire=autre) | Q(expediteur=autre, destinataire=request.user))
           .select_related('expediteur'))
    # Les messages reçus sont maintenant lus
    fil.filter(destinataire=request.user, lu=False).update(lu=True)
    return render(request, 'communaute/conversation.html', {
        'autre': autre, 'fil': fil, 'refus_message': refus,
        'bloque': Blocage.objects.filter(bloqueur=request.user, bloque=autre).exists(),
    })


# ---------- Signalements et blocages ----------

class SignalementForm(forms.Form):
    motif = forms.ChoiceField(choices=Signalement.MOTIFS, widget=forms.RadioSelect, label=_l("Pourquoi signales-tu ce contenu ?"))
    details = forms.CharField(required=False, max_length=1000, label=_l("Précisions (facultatif)"),
                              widget=forms.Textarea(attrs={'rows': 3, 'class': 'field-input'}))


@login_required
def signaler(request, type_contenu, pk):
    """Signale une question, une réponse, un message privé reçu ou un membre à l'équipe de modération."""
    from django.contrib.auth import get_user_model

    if type_contenu == 'sujet':
        objet = get_object_or_404(Sujet, pk=pk)
        membre_signale, retour, apercu = objet.auteur, reverse('communaute:detail', args=[objet.pk]), objet.titre
    elif type_contenu == 'reponse':
        objet = get_object_or_404(Reponse, pk=pk)
        membre_signale, retour, apercu = objet.auteur, reverse('communaute:detail', args=[objet.sujet_id]), objet.contenu
    elif type_contenu == 'message':
        # On ne peut signaler qu'un message qu'on a reçu
        objet = get_object_or_404(MessagePrive, pk=pk, destinataire=request.user)
        membre_signale = objet.expediteur
        retour, apercu = reverse('communaute:conversation', args=[objet.expediteur.username]), objet.contenu
    elif type_contenu == 'membre':
        objet = None
        membre_signale = get_object_or_404(get_user_model(), pk=pk)
        retour, apercu = reverse('communaute:membre', args=[membre_signale.username]), membre_signale.username
    else:
        raise Http404

    if membre_signale == request.user:
        messages.error(request, _("Tu ne peux pas te signaler toi-même."))
        return redirect(retour)

    form = SignalementForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        signalement = Signalement(auteur=request.user, membre_signale=membre_signale,
                                  motif=form.cleaned_data['motif'], details=form.cleaned_data['details'])
        if type_contenu in ('sujet', 'reponse', 'message'):
            setattr(signalement, type_contenu, objet)
        signalement.save()
        if type_contenu in ('sujet', 'reponse'):
            masquer_si_trop_signale(objet)
        messages.success(request, _("Merci. L'équipe OrientIA va examiner ce signalement."))
        return redirect(retour)
    return render(request, 'communaute/signaler.html', {
        'form': form, 'apercu': apercu, 'retour': retour, 'membre_signale': membre_signale,
    })


@login_required
@require_POST
def bloquer(request, username):
    """Bloque ou débloque un membre : plus aucun message privé possible entre vous."""
    from django.contrib.auth import get_user_model
    autre = get_object_or_404(get_user_model(), username=username)
    if autre == request.user:
        return redirect('communaute:membre', username=username)
    blocage = Blocage.objects.filter(bloqueur=request.user, bloque=autre)
    if blocage.exists():
        blocage.delete()
        messages.success(request, _("Tu as débloqué ce membre."))
    else:
        Blocage.objects.create(bloqueur=request.user, bloque=autre)
        messages.success(request, _("Ce membre est bloqué : il ne peut plus t'écrire."))
    return redirect(adresse_sure(request, request.POST.get('suivant'), reverse('communaute:membre', args=[username])))
