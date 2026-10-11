"""Positions et distances, sans PostGIS.

Avec quelques centaines d'écoles, calculer les distances en Python est instantané. Cela évite les
bibliothèques géographiques (GDAL, GEOS) qu'un hébergeur comme Vercel ne fournit pas.
"""
from math import asin, cos, radians, sin, sqrt
from typing import NamedTuple

RAYON_TERRE_KM = 6371.0


class Position(NamedTuple):
    lat: float
    lon: float


def distance_km(a, b):
    """Distance « à vol d'oiseau » entre deux positions (formule de haversine), en kilomètres."""
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * RAYON_TERRE_KM * asin(sqrt(h))


def trier_par_distance(etablissements, position):
    """Ajoute à chaque établissement son attribut distance_km, puis les trie du plus proche au plus loin."""
    etablissements = list(etablissements)
    for e in etablissements:
        e.distance_km = distance_km(position, e.position)
    return sorted(etablissements, key=lambda e: e.distance_km)
