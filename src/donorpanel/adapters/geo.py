import re

import boto3
from botocore.exceptions import ClientError

from donorpanel.config import config

CACHE = "geo/{slug}.json"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")[:120]


class GeocodeDenied(RuntimeError):
    pass


class Geocoder:
    def __init__(self, client=None, store=None, country: str = "IND"):
        self._client = client
        self._store = store
        self.country = country
        self.calls = 0

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("geo-places", region_name=config.aws_region)
        return self._client

    @property
    def store(self):
        if self._store is None:
            from donorpanel.adapters.storage import store as default_store

            self._store = default_store()
        return self._store

    def locate(self, text: str) -> tuple[float, float] | None:
        if not text or not text.strip():
            return None
        key = CACHE.format(slug=slug(f"{text}|{self.country}"))

        cached = self.store.get(key)
        if cached is not None:
            hit = cached.get("hit")
            return (hit["lat"], hit["lon"]) if hit else None

        try:
            self.calls += 1
            response = self.client.geocode(
                QueryText=text,
                Filter={"IncludeCountries": [self.country]},
                MaxResults=1,
            )
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("AccessDeniedException", "AccessDenied"):
                raise GeocodeDenied(
                    "geo-places:Geocode is not permitted for this principal"
                ) from exc
            raise

        items = response.get("ResultItems") or []
        if not items or "Position" not in items[0]:
            self.store.put(key, {"query": text, "hit": None})
            return None

        # Position is GeoJSON order, longitude first. Reading it as lat/lon puts
        # every Indian donor somewhere in Somalia.
        lon, lat = items[0]["Position"][0], items[0]["Position"][1]
        label = (items[0].get("Address") or {}).get("Label") or items[0].get("Title")
        self.store.put(key, {"query": text, "hit": {"lat": lat, "lon": lon, "label": label}})
        return (lat, lon)


def backfill(repo, geocoder: Geocoder | None = None) -> dict[str, int]:
    geocoder = geocoder or Geocoder()
    filled, missed, skipped = 0, 0, 0

    patients = [repo.get_patient(key.rsplit("/", 1)[-1].removesuffix(".json"))
                for key in repo.store.keys("patients/")]
    donors = [repo.get_donor(key.rsplit("/", 1)[-1].removesuffix(".json"))
              for key in repo.store.keys("donors/")]

    for person, save in ((p, repo.put_patient) for p in patients if p):
        filled, missed, skipped = _fill(person, save, geocoder, filled, missed, skipped)
    for person, save in ((d, repo.put_donor) for d in donors if d):
        filled, missed, skipped = _fill(person, save, geocoder, filled, missed, skipped)

    return {"filled": filled, "missed": missed, "skipped": skipped,
            "api_calls": geocoder.calls}


def _fill(person, save, geocoder, filled, missed, skipped):
    if person.lat is not None and person.lon is not None:
        return filled, missed, skipped + 1
    where = ", ".join(x for x in (person.city, getattr(person, "region", None)) if x)
    found = geocoder.locate(where)
    if found is None:
        return filled, missed + 1, skipped
    person.lat, person.lon = found
    save(person)
    return filled + 1, missed, skipped
