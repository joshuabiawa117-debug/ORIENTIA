"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import re

from django.conf import settings
from django.contrib import admin
from django.shortcuts import redirect
from django.templatetags.static import static as fichier_static
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    # Les navigateurs demandent toujours /favicon.ico : on renvoie vers le logo OrientIA
    # (adresse calculée à la demande : en production, le nom du fichier contient une empreinte)
    path('favicon.ico', lambda request: redirect(fichier_static('img/favicon.ico'), permanent=True)),
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('communaute/', include('communaute.urls')),
    path('mon-espace/', include('espace.urls')),
    path('', include('orientation.urls')),
    path('', include('interface.urls')),
]

# Annales envoyées depuis l'administration (static() ne fonctionne qu'en mode DEBUG, d'où la route explicite)
if settings.SERVIR_MEDIAS:
    urlpatterns += [
        re_path(r'^%s(?P<path>.*)$' % re.escape(settings.MEDIA_URL.lstrip('/')), serve, {'document_root': settings.MEDIA_ROOT}),
    ]
