from donorpanel.domain import compatible_groups, distance_km, ineligible_reason, score
from donorpanel.domain.models import Donor


def donor(**kw):
    base = {"donor_id": "d1", "name": "A", "blood_group": "B+", "region": "IN-TN",
            "channel": "telegram", "address": "x", "consent": True, "reachable": True}
    base.update(kw)
    return Donor(**base)


def test_b_positive_can_receive_from_four_groups():
    assert set(compatible_groups("B+")) == {"O-", "O+", "B-", "B+"}


def test_o_negative_can_only_receive_o_negative():
    assert compatible_groups("O-") == ("O-",)


def test_ab_positive_is_universal_recipient():
    assert len(compatible_groups("AB+")) == 8


def test_unknown_group_yields_nothing():
    assert compatible_groups("Z+") == ()


def test_distance_between_coimbatore_and_chennai():
    km = distance_km(11.0168, 76.9558, 13.0827, 80.2707)
    assert 380 < km < 460


def test_distance_is_none_without_coordinates():
    assert distance_km(11.0, 76.0, None, None) is None


def test_consent_is_required():
    assert ineligible_reason(donor(consent=False), {}, []) == "no consent on file"


def test_unreachable_donors_are_excluded():
    assert "unreachable" in ineligible_reason(donor(reachable=False), {}, [])


def test_donation_interval_is_enforced():
    from datetime import datetime, timedelta, timezone
    recent = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    reason = ineligible_reason(donor(last_donation=recent),
                               {"min_days_between_donations": 90}, [])
    assert "needs 90" in reason


def test_a_rested_donor_passes():
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc).date() - timedelta(days=200)).isoformat()
    assert ineligible_reason(donor(last_donation=old),
                             {"min_days_between_donations": 90}, []) is None


def test_missing_antigen_excludes():
    reason = ineligible_reason(donor(antigens=["C"]), {}, ["Ro"])
    assert reason == "missing antigen Ro"


def test_contact_fatigue_lowers_the_score():
    fresh, _ = score(donor(), {}, prefer_repeat=False)
    tired, parts = score(donor(contacts_this_month=3), {}, prefer_repeat=False)
    assert tired < fresh
    assert parts["contact_fatigue"] == -36.0


def test_nearby_donors_outrank_distant_ones():
    near, _ = score(donor(lat=11.02, lon=76.96), {}, 11.0168, 76.9558)
    far, _ = score(donor(lat=13.08, lon=80.27), {}, 11.0168, 76.9558)
    assert near > far
