from .donor import my_eligibility, my_request, record_answer
from .history import request_history
from .panel import donor_detail, open_requests, panel_summary, request_detail
from .request import request_progress, start_request
from .visitor import am_i_registered, register_donor, who_needs_blood

COORDINATOR = [panel_summary, request_detail, open_requests, donor_detail]
DONOR = [my_request, record_answer, my_eligibility]
PUBLIC = [who_needs_blood, am_i_registered, register_donor,
          start_request, request_progress]
VISITOR = PUBLIC

__all__ = [
          "COORDINATOR",
          "DONOR",
          "PUBLIC",
          "VISITOR",
          "am_i_registered",
          "donor_detail",
          "my_eligibility",
          "my_request",
          "open_requests",
          "panel_summary",
          "record_answer",
          "register_donor",
          "request_detail",
          "request_history",
          "request_progress",
          "start_request",
          "who_needs_blood",
]
