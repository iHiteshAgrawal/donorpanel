from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Condition(str, Enum):
    THALASSEMIA = "thalassemia"
    SICKLE_CELL = "sickle_cell"
    RARE_PHENOTYPE = "rare_phenotype"
    OTHER = "other"


class Component(str, Enum):
    WHOLE_BLOOD = "whole_blood"
    PLATELETS = "platelets"
    PACKED_CELLS = "packed_cells"


class RequestSource(str, Enum):
    SCHEDULED = "scheduled"
    EMERGENCY = "emergency"


class RequestStatus(str, Enum):
    DRAFT = "draft"
    VERIFIED = "verified"
    REJECTED = "rejected"
    MATCHING = "matching"
    AWAITING_APPROVAL = "awaiting_approval"
    DISPATCHED = "dispatched"
    FULFILLED = "fulfilled"
    SHORT = "short"
    CLOSED = "closed"


class ContactStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    UNREACHABLE = "unreachable"
    PLEDGED = "pledged"
    DECLINED = "declined"
    NO_RESPONSE = "no_response"
    DONATED = "donated"


@dataclass
class Donor:
    donor_id: str
    name: str
    blood_group: str
    region: str
    channel: str
    address: str
    language: str = "en"
    antigens: list[str] = field(default_factory=list)
    city: str | None = None
    lat: float | None = None
    lon: float | None = None
    last_donation: str | None = None
    consent: bool = False
    reachable: bool = True
    last_contacted: str | None = None
    contacts_this_month: int = 0
    notes: str | None = None


@dataclass
class Patient:
    patient_id: str
    name: str
    condition: Condition
    blood_group: str
    policy_id: str
    region: str
    antigens_required: list[str] = field(default_factory=list)
    city: str | None = None
    hospital: str | None = None
    lat: float | None = None
    lon: float | None = None
    coordinator_channel: str | None = None
    coordinator_address: str | None = None
    dob: str | None = None

    def __post_init__(self) -> None:
        self.condition = Condition(self.condition)


@dataclass
class Request:
    request_id: str
    patient_id: str
    policy_id: str
    units_needed: int
    needed_by: str
    component: Component = Component.PACKED_CELLS
    source: RequestSource = RequestSource.SCHEDULED
    status: RequestStatus = RequestStatus.DRAFT
    units_pledged: int = 0
    rejection_reason: str | None = None
    review_reason: str | None = None
    prescription_ref: str | None = None
    created_at: str = field(default_factory=now)
    updated_at: str = field(default_factory=now)

    def __post_init__(self) -> None:
        self.component = Component(self.component)
        self.source = RequestSource(self.source)
        self.status = RequestStatus(self.status)


@dataclass
class Contact:
    request_id: str
    donor_id: str
    status: ContactStatus = ContactStatus.PENDING
    channel: str | None = None
    rank: int = 0
    contacted_at: str | None = None
    responded_at: str | None = None
    note: str | None = None
    body: str | None = None

    def __post_init__(self) -> None:
        self.status = ContactStatus(self.status)


@dataclass
class Credit:
    patient_id: str
    units_owed: int = 0
    units_repaid: int = 0

    @property
    def outstanding(self) -> int:
        return max(0, self.units_owed - self.units_repaid)


# Storage writes enums as their string values, so every read path would otherwise
# hand back raw strings. These are str enums, so comparisons still pass and the
# inconsistency stays invisible until something touches .value.
def to_item(obj: Any) -> dict[str, Any]:
    return {k: (v.value if isinstance(v, Enum) else v)
            for k, v in asdict(obj).items() if v is not None}


def days_since(iso_day: str | None) -> int | None:
    if not iso_day:
        return None
    return (datetime.now(timezone.utc).date() - date.fromisoformat(iso_day)).days
