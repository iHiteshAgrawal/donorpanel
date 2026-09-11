import pytest

from donorpanel.adapters.channels import Channel, DeliveryResult, Inbound
from donorpanel.adapters.storage import FileStore, PanelRepository
from donorpanel.domain import Contact, ContactStatus, Donor, Request, RequestStatus
from donorpanel.services import outreach

DRAFTS = [
    {"language": "ta", "channel": "telegram", "subject": None, "body": "Vanakkam {name}, Ravi needs B+."},
    {"language": "hi", "channel": "email", "subject": "Ravi needs B+", "body": "Namaste {name}."},
]


class Recorder(Channel):
    def __init__(self, name="telegram", delivered=True, boom=False):
        self.name = name
        self.delivered = delivered
        self.boom = boom
        self.sent = []

    async def send(self, message):
        if self.boom:
            raise RuntimeError("socket exploded")
        self.sent.append(message)
        return DeliveryResult(delivered=self.delivered, channel=self.name,
                              reference="mid-1" if self.delivered else None,
                              error=None if self.delivered else "chat not found")

    async def poll(self) -> list[Inbound]:
        return []

    def available(self) -> bool:
        return True


@pytest.fixture
def repo(tmp_path):
    store = PanelRepository(store=FileStore(tmp_path))
    store.put_request(Request(request_id="r-1", patient_id="p-ravi",
                              policy_id="thalassemia-india", units_needed=2,
                              needed_by="2026-10-01"))
    store.put_drafts("r-1", DRAFTS)
    return store


def cohort(repo, rows=(("d-one", "telegram", "ta"), ("d-two", "email", "hi"))):
    contacts = []
    for rank, (donor_id, channel, language) in enumerate(rows, start=1):
        repo.put_donor(Donor(donor_id=donor_id, name=f"{donor_id.upper()} Person",
                             blood_group="B+", region="IN-TN", channel=channel,
                             address=f"{donor_id}-handle", language=language, consent=True))
        contacts.append(Contact(request_id="r-1", donor_id=donor_id, channel=channel, rank=rank))
    repo.put_contacts(contacts)


def test_each_donor_gets_the_draft_for_their_language_and_channel(repo):
    cohort(repo)
    telegram, email = Recorder("telegram"), Recorder("email")
    out = outreach.deliver(repo, "r-1", channels={"telegram": telegram, "email": email})

    assert out["delivered_count"] == 2 and out["failed_count"] == 0
    assert telegram.sent[0].body == "Vanakkam D-ONE, Ravi needs B+."
    assert telegram.sent[0].recipient == "d-one-handle"
    assert email.sent[0].subject == "Ravi needs B+"
    assert email.sent[0].body == "Namaste D-TWO."


def test_delivery_is_recorded_on_each_contact(repo):
    cohort(repo)
    outreach.deliver(repo, "r-1", channels={"telegram": Recorder("telegram"),
                                            "email": Recorder("email")})
    contacts = {c.donor_id: c for c in repo.list_contacts("r-1")}
    assert contacts["d-one"].status is ContactStatus.SENT
    assert contacts["d-one"].contacted_at is not None
    assert contacts["d-one"].note == "mid-1"
    assert "Vanakkam" in contacts["d-one"].body
    assert repo.get_request("r-1").status is RequestStatus.DISPATCHED


def test_an_unconfigured_channel_is_a_clean_per_donor_failure(repo):
    cohort(repo)
    out = outreach.deliver(repo, "r-1", channels={"telegram": Recorder("telegram")})

    assert out["delivered_count"] == 1 and out["failed_count"] == 1
    rows = {r["donor_id"]: r for r in out["outreach"]}
    assert rows["d-two"]["detail"] == "email channel not configured"
    contacts = {c.donor_id: c for c in repo.list_contacts("r-1")}
    assert contacts["d-two"].status is ContactStatus.UNREACHABLE


def test_a_raising_channel_never_breaks_the_run(repo):
    cohort(repo, rows=(("d-one", "telegram", "ta"),))
    out = outreach.deliver(repo, "r-1", channels={"telegram": Recorder(boom=True)})
    assert out["delivered_count"] == 0
    assert "socket exploded" in out["outreach"][0]["detail"]


def test_nothing_delivered_leaves_the_request_for_a_human(repo):
    cohort(repo, rows=(("d-one", "telegram", "ta"),))
    outreach.deliver(repo, "r-1", channels={"telegram": Recorder(delivered=False)})
    assert repo.get_request("r-1").status is RequestStatus.AWAITING_APPROVAL


def test_only_successful_sends_spend_the_contact_budget(repo):
    cohort(repo)
    outreach.deliver(repo, "r-1", channels={"telegram": Recorder("telegram"),
                                            "email": Recorder("email", delivered=False)})
    assert repo.get_donor("d-one").contacts_this_month == 1
    assert repo.get_donor("d-one").last_contacted is not None
    assert repo.get_donor("d-two").contacts_this_month == 0


def test_no_drafts_sends_nothing(repo):
    cohort(repo)
    repo.put_drafts("r-1", [])
    out = outreach.deliver(repo, "r-1", channels={"telegram": Recorder("telegram")})
    assert out["delivered_count"] == 0 and out["problem"] == "no drafts to send"


def test_draft_falls_back_to_the_channel_when_the_language_has_none(repo):
    cohort(repo, rows=(("d-three", "telegram", "kn"),))
    telegram = Recorder("telegram")
    outreach.deliver(repo, "r-1", channels={"telegram": telegram})
    assert telegram.sent[0].body.startswith("Vanakkam")
