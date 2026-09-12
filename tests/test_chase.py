from datetime import date, datetime, timedelta, timezone

import pytest

from donorpanel.adapters.storage import FileStore, PanelRepository
from donorpanel.domain import (
    Condition,
    Contact,
    ContactStatus,
    Donor,
    Patient,
    Request,
    RequestStatus,
)
from donorpanel.services import chase

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


class Sender:
    """Stands in for every channel so a wave never touches the network."""

    def __init__(self):
        self.name = "telegram"
        self.sent = []

    async def send(self, message):
        from donorpanel.adapters.channels import DeliveryResult
        self.sent.append(message.recipient)
        return DeliveryResult(delivered=True, channel=self.name, reference="m1")

    async def poll(self):
        return []

    def available(self):
        return True


def wired(sender):
    return {"telegram": sender, "email": sender, "console": sender}


@pytest.fixture
def repo(tmp_path):
    store = PanelRepository(store=FileStore(tmp_path))
    store.put_patient(Patient(patient_id="p-ravi", name="Ravi",
                              condition=Condition.THALASSEMIA, blood_group="B+",
                              policy_id="thalassemia-india", region="IN-TN",
                              lat=11.0, lon=76.9))
    for i in range(6):
        store.put_donor(Donor(donor_id=f"d-{i}", name=f"Donor{i}", blood_group="B+",
                              region="IN-TN", channel="telegram",
                              address=f"chat-{i}", consent=True, lat=11.0, lon=76.9))
    row = Request(request_id="r-1", patient_id="p-ravi", policy_id="thalassemia-india",
                  units_needed=2, needed_by="2026-11-20")
    store.put_request(row)
    store.set_status("r-1", RequestStatus.DISPATCHED)
    store.put_drafts("r-1", [{"language": "en", "channel": "telegram",
                              "subject": None, "body": "Hello {name}"}])
    return store


def first_wave(repo, donors=("d-0", "d-1"), status=ContactStatus.SENT, hours_ago=30):
    when = (NOW - timedelta(hours=hours_ago)).isoformat()
    repo.put_contacts([
        Contact(request_id="r-1", donor_id=d, channel="telegram", rank=i + 1,
                status=status, contacted_at=when) for i, d in enumerate(donors)])


def test_a_second_wave_reaches_people_the_first_did_not(repo):
    first_wave(repo)
    sender = Sender()
    out = chase.chase(repo, now=NOW, channels=wired(sender))

    assert out["chased"] == 1
    reached = {c.donor_id for c in repo.list_contacts("r-1") if c.contacted_at}
    assert {"d-0", "d-1"} <= reached
    # The new wave went only to people who had not been asked.
    assert sender.sent and "chat-0" not in sender.sent and "chat-1" not in sender.sent


def test_nobody_is_asked_twice(repo):
    first_wave(repo)
    sender = Sender()
    chase.chase(repo, now=NOW, channels=wired(sender))
    assert len(sender.sent) == len(set(sender.sent))


def test_a_wave_that_is_not_due_yet_sends_nothing(repo):
    first_wave(repo, hours_ago=2)          # escalation_hours[1] is 24
    sender = Sender()
    assert chase.chase(repo, now=NOW, channels=wired(sender))["chased"] == 0
    assert sender.sent == []


def test_asking_stops_when_the_schedule_is_exhausted(repo):
    # thalassemia-india declares [0, 24, 48], so three waves is the end of it.
    for wave, donors in enumerate((("d-0",), ("d-1",), ("d-2",))):
        when = (NOW - timedelta(hours=100 - wave)).isoformat()
        repo.put_contacts([Contact(request_id="r-1", donor_id=d, channel="telegram",
                                   rank=wave + 1, status=ContactStatus.SENT,
                                   contacted_at=when) for d in donors])
    sender = Sender()
    assert chase.chase(repo, now=NOW, channels=wired(sender))["chased"] == 0


def test_a_request_with_enough_pledges_is_left_alone(repo):
    first_wave(repo, donors=("d-0", "d-1"), status=ContactStatus.PLEDGED)
    sender = Sender()
    assert chase.chase(repo, now=NOW, channels=wired(sender))["chased"] == 0


def test_a_request_waiting_on_a_human_is_not_chased_around(repo):
    first_wave(repo)
    repo.set_status("r-1", RequestStatus.AWAITING_APPROVAL)
    sender = Sender()
    assert chase.chase(repo, now=NOW, channels=wired(sender))["chased"] == 0


def test_a_declined_donor_is_never_asked_again(repo):
    first_wave(repo, donors=("d-0",), status=ContactStatus.DECLINED)
    sender = Sender()
    chase.chase(repo, now=NOW, channels=wired(sender))
    assert "chat-0" not in sender.sent


def test_a_past_request_closes_short_when_pledges_fall_short(repo):
    first_wave(repo)
    out = chase.close(repo, today=date(2026, 11, 25))
    assert out["closed"] == 1
    assert repo.get_request("r-1").status is RequestStatus.SHORT
    assert all(c.status is not ContactStatus.SENT for c in repo.list_contacts("r-1"))


def test_a_past_request_closes_fulfilled_when_they_are_covered(repo):
    first_wave(repo, donors=("d-0", "d-1"), status=ContactStatus.PLEDGED)
    chase.close(repo, today=date(2026, 11, 25))
    assert repo.get_request("r-1").status is RequestStatus.FULFILLED


def test_closing_frees_the_patient_for_the_next_forecast(repo):
    # An open request hides its patient from the forecast, so without close() every
    # patient becomes permanently invisible after their first request.
    from donorpanel.services import forecast

    first_wave(repo)
    assert forecast.due(repo, date(2026, 11, 25)) == []
    chase.close(repo, today=date(2026, 11, 25))
    assert [r["patient_id"] for r in forecast.due(repo, date(2026, 12, 12))] == ["p-ravi"]


def test_who_can_i_help_lists_every_recipient():
    """Asked "who can I help", Asha answered from memory and then claimed the tool had
    confirmed it. blood_compatibility only compares one pair, so it could not have."""
    from donorpanel.tools.visitor import who_can_i_help

    def recipients(group: str) -> list[str]:
        listed = who_can_i_help(group).split("can donate to: ")[1].split(".")[0]
        return [g.strip() for g in listed.split(",")]

    assert recipients("AB+") == ["AB+"]                    # narrowest donor
    assert len(recipients("O-")) == 8                      # universal donor
    assert recipients("A+") == ["A+", "AB+"]
    assert "INTERNAL" in who_can_i_help("C")
