from donorpanel.domain import Donor
from donorpanel.storage import FileStore, PanelRepository


def test_repository_works_on_the_local_backend(tmp_path):
    repo = PanelRepository(store=FileStore(tmp_path))
    repo.put_donor(Donor(donor_id="d1", name="Asha", blood_group="B+",
                         region="IN-TN", channel="telegram", address="123"))
    assert repo.get_donor("d1").name == "Asha"
    assert [d.donor_id for d in repo.list_pool("IN-TN", "B+")] == ["d1"]
