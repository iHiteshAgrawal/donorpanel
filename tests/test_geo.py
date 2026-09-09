import pytest

from donorpanel.domain import Condition, Donor, Patient
from donorpanel.geo import GeocodeDenied, Geocoder, backfill, slug
from donorpanel.storage import FileStore, PanelRepository


class StubPlaces:
    def __init__(self, results=None, error=None):
        self.results = results or {}
        self.error = error
        self.queries = []

    def geocode(self, **kwargs):
        self.queries.append(kwargs["QueryText"])
        if self.error:
            raise self.error
        hit = self.results.get(kwargs["QueryText"])
        if hit is None:
            return {"ResultItems": []}
        lat, lon = hit
        return {"ResultItems": [{"Position": [lon, lat],
                                 "Address": {"Label": kwargs["QueryText"]}}]}


COIMBATORE = {"Coimbatore, IN-TN": (11.0168, 76.9558)}


@pytest.fixture
def repo(tmp_path):
    return PanelRepository(store=FileStore(tmp_path))


def test_slug_is_filesystem_safe():
    assert slug("Coimbatore, Tamil Nadu|IND") == "coimbatore-tamil-nadu-ind"


def test_position_is_read_as_longitude_first(repo):
    places = StubPlaces(COIMBATORE)
    found = Geocoder(client=places, store=repo.store).locate("Coimbatore, IN-TN")
    assert found == (11.0168, 76.9558)


def test_results_are_cached_so_the_api_is_called_once(repo):
    places = StubPlaces(COIMBATORE)
    geo = Geocoder(client=places, store=repo.store)
    geo.locate("Coimbatore, IN-TN")
    geo.locate("Coimbatore, IN-TN")
    assert places.queries == ["Coimbatore, IN-TN"]
    assert geo.calls == 1


def test_a_miss_is_cached_too(repo):
    places = StubPlaces({})
    geo = Geocoder(client=places, store=repo.store)
    assert geo.locate("Nowhere at all") is None
    assert geo.locate("Nowhere at all") is None
    assert len(places.queries) == 1


def test_blank_input_never_calls_the_api(repo):
    places = StubPlaces({})
    assert Geocoder(client=places, store=repo.store).locate("  ") is None
    assert places.queries == []


def test_permission_failure_is_reported_clearly(repo):
    from botocore.exceptions import ClientError

    denied = ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}},
                         "Geocode")
    geo = Geocoder(client=StubPlaces(error=denied), store=repo.store)
    with pytest.raises(GeocodeDenied):
        geo.locate("Coimbatore, IN-TN")


def test_backfill_fills_only_missing_coordinates(repo):
    repo.put_patient(Patient(patient_id="p1", name="Ravi",
                             condition=Condition.THALASSEMIA, blood_group="B+",
                             policy_id="thalassemia-india", region="IN-TN",
                             city="Coimbatore"))
    repo.put_donor(Donor(donor_id="d-known", name="A", blood_group="B+",
                         region="IN-TN", channel="telegram", address="x",
                         city="Coimbatore", lat=1.0, lon=2.0))
    repo.put_donor(Donor(donor_id="d-blank", name="B", blood_group="B+",
                         region="IN-TN", channel="telegram", address="x",
                         city="Coimbatore"))

    places = StubPlaces(COIMBATORE)
    report = backfill(repo, Geocoder(client=places, store=repo.store))

    assert report == {"filled": 2, "missed": 0, "skipped": 1, "api_calls": 1}
    assert repo.get_donor("d-blank").lat == 11.0168
    assert repo.get_donor("d-known").lat == 1.0
