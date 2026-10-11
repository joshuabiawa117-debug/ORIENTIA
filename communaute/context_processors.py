def messages_non_lus(request):
    """Nombre de messages privés non lus, affiché dans le menu."""
    if not request.user.is_authenticated:
        return {}
    from .models import MessagePrive
    return {'nb_messages_non_lus': MessagePrive.objects.filter(destinataire=request.user, lu=False).count()}
