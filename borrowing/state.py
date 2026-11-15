"""The only place that changes Booking / BorrowRequest status (docs/02-state-machine.md).

`transition(obj, event, actor, **data)` checks that the event is allowed from the current status and that
`actor` may perform it, writes status + audit fields, saves and returns `obj`. It does not send
notifications and does not touch stock; services do that inside the same transaction.
`actor=None` means the system (scheduled job).
"""
from datetime import timedelta

from django.utils import timezone
from django.utils.translation import gettext as _

from core.models import SystemSetting
from core.permissions import STAFF, has_role

from .models import Booking, BookingStatus, BorrowRequest, RequestStatus


class TransitionError(Exception):
    """Event not allowed (wrong status, wrong actor or missing data). Message is user-facing."""


R = RequestStatus
B = BookingStatus

# event: (allowed source statuses, target status, who)
REQUEST_EVENTS = {
    "approve": ({R.PENDING}, R.APPROVED, "staff"),
    "reject": ({R.PENDING}, R.REJECTED, "staff"),
    "cancel": ({R.PENDING, R.APPROVED}, R.CANCELLED, "owner_or_staff"),
    "hand_over": ({R.APPROVED}, R.BORROWED, "staff"),
    "mark_overdue": ({R.BORROWED}, R.OVERDUE, "system"),
    # Staff extended due_at (e.g. in the admin): the next check_due puts the loan back to "on loan".
    "clear_overdue": ({R.OVERDUE}, R.BORROWED, "system"),
    "receive_return": ({R.BORROWED, R.OVERDUE}, R.RETURNED, "staff"),
}

BOOKING_EVENTS = {
    "cancel": ({B.ACTIVE}, B.CANCELLED, "owner_or_staff"),
    "convert": ({B.ACTIVE}, B.CONVERTED, "owner"),
    "expire": ({B.ACTIVE}, B.EXPIRED, "system"),
}


def _is_staff(actor):
    return actor is not None and has_role(actor, STAFF)


def _check_actor(who, obj, actor):
    if who == "system":
        if actor is not None and not _is_staff(actor):
            raise TransitionError(_("You are not allowed to do this."))
        return
    if actor is None:
        raise TransitionError(_("You are not allowed to do this."))
    is_owner = obj.user_id == actor.pk
    if who == "staff" and not _is_staff(actor):
        raise TransitionError(_("Only lab staff can do this."))
    if who == "owner" and not is_owner:
        raise TransitionError(_("Only the owner can do this."))
    if who == "owner_or_staff" and not (is_owner or _is_staff(actor)):
        raise TransitionError(_("You are not allowed to do this."))


def _check_cancel_window(start_at, actor):
    """Borrowers may cancel only until `cancel_before_hours` before the start; staff any time."""
    if _is_staff(actor):
        return
    limit = start_at - timedelta(hours=SystemSetting.load().cancel_before_hours)
    if timezone.now() > limit:
        raise TransitionError(_("It is too late to cancel. Please contact the lab staff."))


def allowed_events(obj, actor):
    """Events `actor` may trigger on `obj` now (used to show action buttons)."""
    table = REQUEST_EVENTS if isinstance(obj, BorrowRequest) else BOOKING_EVENTS
    result = []
    for event, (sources, _target, who) in table.items():
        if obj.status not in sources or who == "system":
            continue
        try:
            _check_actor(who, obj, actor)
            if event == "cancel":
                _check_cancel_window(obj.borrow_at if isinstance(obj, BorrowRequest) else obj.start_at, actor)
        except TransitionError:
            continue
        result.append(event)
    return result


def transition(obj, event, actor=None, **data):
    now = timezone.now()
    if isinstance(obj, BorrowRequest):
        table = REQUEST_EVENTS
    elif isinstance(obj, Booking):
        table = BOOKING_EVENTS
    else:
        raise TypeError(f"no state machine for {type(obj).__name__}")
    if event not in table:
        raise TransitionError(_("Unknown action."))
    sources, target, who = table[event]
    if obj.status not in sources:
        raise TransitionError(_("This action is not possible in status “%(status)s”.")
                              % {"status": obj.get_status_display()})
    _check_actor(who, obj, actor)

    fields = ["status", "updated_at"]
    if isinstance(obj, BorrowRequest):
        if event in ("approve", "reject"):
            if event == "reject":
                reason = (data.get("reason") or "").strip()
                if not reason:
                    raise TransitionError(_("Please give a reason for the rejection."))
                obj.reject_reason = reason[:255]
                fields.append("reject_reason")
            obj.decided_by, obj.decided_at = actor, now
            fields += ["decided_by", "decided_at"]
        elif event == "cancel":
            _check_cancel_window(obj.borrow_at, actor)
            obj.cancelled_by, obj.cancelled_at = actor, now
            fields += ["cancelled_by", "cancelled_at"]
        elif event == "hand_over":
            obj.handed_over_by, obj.handed_over_at = actor, now
            fields += ["handed_over_by", "handed_over_at"]
        elif event == "mark_overdue":
            obj.overdue_notified_at = now
            fields.append("overdue_notified_at")
        elif event == "clear_overdue":
            obj.overdue_notified_at = obj.reminder_sent_at = None
            fields += ["overdue_notified_at", "reminder_sent_at"]
    else:
        if event == "cancel":
            _check_cancel_window(obj.start_at, actor)
            obj.cancelled_by, obj.cancelled_at = actor, now
            fields += ["cancelled_by", "cancelled_at"]

    obj.status = target
    obj.save(update_fields=fields)
    return obj
