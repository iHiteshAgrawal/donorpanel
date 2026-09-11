import pytest

from donorpanel import seed as seeds
from donorpanel.domain import Donor
from donorpanel.storage import FileStore, ObjectStore, PanelRepository


def donor(donor_id="d1"):
    return Donor(donor_id=donor_id, name="Asha", blood_group="B+", region="IN-TN",
                 channel="telegram", address="x", consent=True)


@pytest.fixture
def two_actors(tmp_path):
    return (PanelRepository(store=FileStore(tmp_path, prefix="actors/alpha/")),
            PanelRepository(store=FileStore(tmp_path, prefix="actors/bravo/")))


def test_one_actor_cannot_see_another(two_actors):
    alpha, bravo = two_actors
    alpha.put_donor(donor("d-alpha"))
    assert alpha.get_donor("d-alpha") is not None
    assert bravo.get_donor("d-alpha") is None
    assert bravo.list_pool("IN-TN", "B+") == []


def test_keys_come_back_without_the_prefix(two_actors):
    alpha, _ = two_actors
    alpha.put_donor(donor("d-alpha"))
    keys = alpha.store.keys("donors/")
    assert keys == ["donors/d-alpha.json"]


def test_the_prefix_survives_a_pool_query(two_actors):
    alpha, bravo = two_actors
    alpha.put_donor(donor("d-alpha"))
    bravo.put_donor(donor("d-bravo"))
    assert [d.donor_id for d in alpha.list_pool("IN-TN", "B+")] == ["d-alpha"]
    assert [d.donor_id for d in bravo.list_pool("IN-TN", "B+")] == ["d-bravo"]


def test_a_fresh_namespace_reports_empty_then_seeds(two_actors):
    alpha, _ = two_actors
    assert seeds.is_empty(alpha)
    assert seeds.populate(alpha) == len(seeds.POOL)
    assert not seeds.is_empty(alpha)
    assert alpha.get_patient("p-ravi").name == "Ravi"
    assert len(alpha.list_pool("IN-TN", "B+")) == 4


def test_wiping_one_sandbox_leaves_the_other_alone(two_actors):
    alpha, bravo = two_actors
    seeds.populate(alpha)
    seeds.populate(bravo)
    seeds.wipe(alpha)
    assert seeds.is_empty(alpha)
    assert not seeds.is_empty(bravo)


def test_coordinates_are_reused_so_seeding_costs_no_geocoding(two_actors):
    alpha, bravo = two_actors
    seeds.populate(alpha, {"Coimbatore": (11.0, 76.9), "Chennai": (13.0, 80.2)})
    harvested = seeds.coordinates_from(alpha)
    assert harvested["Coimbatore"] == (11.0, 76.9)

    seeds.populate(bravo, harvested)
    assert bravo.get_donor("d-asha").lat == 11.0
    assert bravo.get_donor("d-arun").lat == 13.0


def test_the_s3_backend_prefixes_and_strips_the_same_way(store):
    scoped = ObjectStore(s3=store._s3, bucket=store._bucket, prefix="actors/zed/")
    scoped.put("donors/d1.json", {"name": "Asha"})
    assert scoped.keys("donors/") == ["donors/d1.json"]
    assert scoped.get("donors/d1.json") == {"name": "Asha"}
    # The unprefixed root must not see it.
    assert store.get("donors/d1.json") is None
    assert store.keys("actors/zed/donors/") == ["actors/zed/donors/d1.json"]
