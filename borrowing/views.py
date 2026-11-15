from datetime import datetime
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dates import WEEKDAYS_ABBR
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from core.models import SystemSetting
from core.permissions import ALL_ROLES, STAFF, borrower_required, has_role, role_required, staff_required
from inventory.models import Equipment
from inventory.services import resize_image

from . import services
from .forms import LOCAL, BookingForm, ConvertForm, HistoryFilterForm, ItemFormSet, RequestForm, ReturnForm
from .models import ON_LOAN, Booking, BookingStatus, BorrowRequest, RequestStatus
from .state import TransitionError, allowed_events

PAGE_SIZE = 20
ACTIVE_STATUSES = [RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.BORROWED, RequestStatus.OVERDUE]
HOLDING_STATUSES = ACTIVE_STATUSES
EVENT_COLORS = {
    "pending": "#ffc107", "approved": "#0dcaf0", "borrowed": "#0d6efd", "overdue": "#dc3545", "booking": "#198754",
}
all_roles = role_required(*ALL_ROLES)


# ---------------------------------------------------------------- helpers

def _is_staff(user):
    return has_role(user, STAFF)


def _messages_of(exc):
    return "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)


def _own_or_staff(model, user, pk):
    qs = model.objects.all()
    if not _is_staff(user):
        qs = qs.filter(user=user)
    return get_object_or_404(qs, pk=pk)


def _next_url(request, default):
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        return nxt
    return default


def _action(request, func, success, *args, **kwargs):
    """Run a service call, report the outcome through messages. Returns the result or None."""
    try:
        result = func(*args, **kwargs)
    except (ValidationError, TransitionError) as exc:
        messages.error(request, _messages_of(exc))
        return None
    messages.success(request, success)
    return result


def _parse_int(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if -(2 ** 63) <= value < 2 ** 63 else None


def _paginate(request, qs):
    page = Paginator(qs, PAGE_SIZE).get_page(_parse_int(request.GET.get("page")))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()


def _hours_help(settings):
    days = ", ".join(str(WEEKDAYS_ABBR[d]) for d in settings.weekday_list)
    return _("Open %(days)s, %(open)s-%(close)s.") % {
        "days": days, "open": settings.open_time.strftime("%H:%M") if not isinstance(settings.open_time, str)
        else settings.open_time[:5],
        "close": settings.close_time.strftime("%H:%M") if not isinstance(settings.close_time, str)
        else settings.close_time[:5],
    }


def _with_actions(objs, user):
    for obj in objs:
        obj.actions = allowed_events(obj, user)
    return objs


def _request_qs():
    return BorrowRequest.objects.select_related("user").prefetch_related("items__equipment")


# ---------------------------------------------------------------- calendar

@all_roles
@require_GET
def calendar(request):
    return render(request, "borrowing/calendar.html", {
        "equipment_list": Equipment.objects.active().order_by("asset_code"),
        "selected": str(_parse_int(request.GET.get("equipment")) or ""),
        "lang": "en" if get_language() == "en" else "th",
    })


def _parse_dt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace(" ", "+"))
    except ValueError:
        return None
    return timezone.make_aware(dt, LOCAL) if timezone.is_naive(dt) else dt


@all_roles
@require_GET
def calendar_events(request):
    user = request.user
    staff = _is_staff(user)
    start, end = _parse_dt(request.GET.get("start")), _parse_dt(request.GET.get("end"))
    equipment_pk = _parse_int(request.GET.get("equipment"))
    bookings = Booking.objects.filter(status=BookingStatus.ACTIVE).select_related("equipment", "user")
    requests_ = BorrowRequest.objects.filter(status__in=HOLDING_STATUSES).select_related("user")
    if start:
        bookings = bookings.filter(end_at__gt=start)
        requests_ = requests_.filter(due_at__gt=start)
    if end:
        bookings = bookings.filter(start_at__lt=end)
        requests_ = requests_.filter(borrow_at__lt=end)
    if equipment_pk is not None:
        bookings = bookings.filter(equipment_id=equipment_pk)
        requests_ = requests_.filter(items__equipment_id=equipment_pk).distinct()
    requests_ = requests_.prefetch_related("items__equipment")

    def title(name, qty, owner, code):
        if staff:
            return f"{name} x{qty} - {owner.get_full_name() or owner.username}"
        if owner.pk == user.pk:
            return f"{name} x{qty} ({code})"
        return f"{name} - {_('Booked')}"

    events = []
    for b in bookings:
        mine = b.user_id == user.pk
        events.append({
            "id": f"b{b.pk}", "title": title(b.equipment.display_name, b.quantity, b.user, str(b)),
            "start": b.start_at.isoformat(), "end": b.end_at.isoformat(), "color": EVENT_COLORS["booking"],
            "url": reverse("borrowing:my_requests") if mine else "",
        })
    for r in requests_:
        mine = r.user_id == user.pk
        for item in r.items.all():
            if equipment_pk is not None and item.equipment_id != equipment_pk:
                continue
            events.append({
                "id": f"r{r.pk}-{item.pk}",
                "title": title(item.equipment.display_name, item.quantity, r.user, r.code),
                "start": r.borrow_at.isoformat(), "end": r.due_at.isoformat(),
                "color": EVENT_COLORS[r.status],
                "url": r.get_absolute_url() if (mine or staff) else "",
            })
    return JsonResponse(events, safe=False)


# ---------------------------------------------------------------- bookings

@borrower_required
def booking_create(request, equipment_pk):
    equipment = get_object_or_404(Equipment.objects.active(), pk=equipment_pk)
    settings = SystemSetting.load()
    form = BookingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            services.create_booking(request.user, equipment, d["quantity"], d["start_at"], d["end_at"], d["note"])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _("The booking was created."))
            return redirect("borrowing:my_requests")
    return render(request, "borrowing/booking_form.html", {
        "form": form, "equipment": equipment, "hours_help": _hours_help(settings), "settings": settings,
    })


@borrower_required
@require_POST
def booking_convert(request, pk):
    booking = get_object_or_404(Booking, pk=pk, user=request.user)
    form = ConvertForm(request.POST)
    if not form.is_valid():
        messages.error(request, _("Please state the purpose of the loan."))
        return redirect("borrowing:my_requests")
    req = _action(request, services.convert_booking, _("The booking was converted to a borrow request."),
                  booking, request.user, form.cleaned_data["purpose"])
    return redirect(req) if req else redirect("borrowing:my_requests")


@all_roles
@require_POST
def booking_cancel(request, pk):
    booking = _own_or_staff(Booking, request.user, pk)
    _action(request, services.cancel_booking, _("The booking was cancelled."), booking, request.user)
    return redirect(_next_url(request, reverse("borrowing:my_requests")))


# ---------------------------------------------------------------- requests (borrower)

@borrower_required
def request_create(request):
    settings = SystemSetting.load()
    if request.method == "POST":
        form = RequestForm(request.POST)
        formset = ItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            items = [(f.cleaned_data["equipment"], f.cleaned_data["quantity"])
                     for f in formset if f.cleaned_data.get("equipment")]
            d = form.cleaned_data
            try:
                req = services.create_request(request.user, items, d["borrow_at"], d["due_at"], d["purpose"])
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, _("The borrow request was submitted."))
                return redirect(req)
    else:
        form = RequestForm()
        initial = []
        pk = _parse_int(request.GET.get("equipment"))
        if pk is not None and Equipment.objects.active().filter(pk=pk).exists():
            initial = [{"equipment": pk, "quantity": 1}]
        formset = ItemFormSet(initial=initial)
    return render(request, "borrowing/request_form.html", {
        "form": form, "formset": formset, "settings": settings, "hours_help": _hours_help(settings),
    })


@borrower_required
def my_requests(request):
    tab = "history" if request.GET.get("tab") == "history" else "active"
    mine = _request_qs().filter(user=request.user)
    if tab == "active":
        qs = mine.filter(status__in=ACTIVE_STATUSES).order_by("due_at")
    else:
        qs = mine.exclude(status__in=ACTIVE_STATUSES)
    page, querystring = _paginate(request, qs)
    _with_actions(page.object_list, request.user)
    bookings = list(Booking.objects.filter(user=request.user).select_related("equipment")
                    .order_by("status", "-start_at")[:30])
    bookings.sort(key=lambda b: (b.status != BookingStatus.ACTIVE, -b.start_at.timestamp()))
    _with_actions(bookings, request.user)
    return render(request, "borrowing/my_requests.html", {
        "tab": tab, "page_obj": page, "querystring": querystring, "bookings": bookings,
        "active_count": mine.filter(status__in=ACTIVE_STATUSES).count(),
    })


@all_roles
def request_detail(request, pk):
    req = get_object_or_404(_own_or_staff_qs(request.user), pk=pk)
    record = getattr(req, "return_record", None)
    timeline = [{"icon": "bi-plus-circle", "label": _("Request created"), "at": req.created_at, "by": req.user}]
    if req.decided_at:
        label = _("Rejected") if req.status == RequestStatus.REJECTED else _("Approved")
        timeline.append({"icon": "bi-check2-circle" if label == _("Approved") else "bi-x-circle",
                         "label": label, "at": req.decided_at, "by": req.decided_by, "note": req.reject_reason})
    if req.handed_over_at:
        timeline.append({"icon": "bi-box-arrow-right", "label": _("Handed over"), "at": req.handed_over_at,
                         "by": req.handed_over_by})
    if req.status == RequestStatus.OVERDUE and req.overdue_notified_at:
        timeline.append({"icon": "bi-exclamation-triangle", "label": _("Marked overdue"),
                         "at": req.overdue_notified_at, "by": None})
    if record:
        timeline.append({"icon": "bi-box-arrow-in-left", "label": _("Returned"), "at": record.returned_at,
                         "by": record.received_by})
    if req.cancelled_at:
        timeline.append({"icon": "bi-slash-circle", "label": _("Cancelled"), "at": req.cancelled_at,
                         "by": req.cancelled_by})
    return render(request, "borrowing/request_detail.html", {
        "req": req, "record": record, "timeline": timeline, "actions": allowed_events(req, request.user),
        "return_items": record.items.select_related("borrow_item__equipment") if record else [],
        "images": record.images.all() if record else [],
        "is_staff_user": _is_staff(request.user),
    })


def _own_or_staff_qs(user):
    qs = _request_qs().select_related("decided_by", "handed_over_by", "cancelled_by",
                                     "return_record", "return_record__received_by")
    return qs if _is_staff(user) else qs.filter(user=user)


@all_roles
@require_POST
def request_cancel(request, pk):
    req = _own_or_staff(BorrowRequest, request.user, pk)
    _action(request, services.cancel_request, _("The request was cancelled."), req, request.user)
    return redirect(_next_url(request, req.get_absolute_url()))


# ---------------------------------------------------------------- staff

@staff_required
def staff_requests(request):
    tab = request.GET.get("tab", "pending")
    tabs = {
        "pending": Q(status=RequestStatus.PENDING),
        "approved": Q(status=RequestStatus.APPROVED),
        "loan": Q(status__in=ON_LOAN),
        "all": Q(),
    }
    if tab not in tabs:
        tab = "pending"
    base = _request_qs()
    counts = base.aggregate(
        pending=Count("pk", filter=tabs["pending"]), approved=Count("pk", filter=tabs["approved"]),
        loan=Count("pk", filter=tabs["loan"]), all=Count("pk"))
    qs = base.filter(tabs[tab])
    q = request.GET.get("q", "").strip()
    if q:
        cond = (Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) | Q(user__username__icontains=q)
                | Q(items__equipment__name_th__icontains=q) | Q(items__equipment__name_en__icontains=q)
                | Q(items__equipment__asset_code__icontains=q))
        digits = q.upper().replace("REQ-", "").strip()
        pk = _parse_int(digits)
        if pk is not None:
            cond |= Q(pk=pk)
            if len(digits) > 4:
                suffix_pk = _parse_int(digits[4:])
                if suffix_pk is not None:
                    cond |= Q(pk=suffix_pk)
        qs = qs.filter(cond).distinct()
    qs = qs.order_by("due_at" if tab == "loan" else "-created_at")
    page, querystring = _paginate(request, qs)
    now = timezone.now()
    for r in page.object_list:
        r.is_late = r.status == RequestStatus.OVERDUE or (r.status == RequestStatus.BORROWED and r.due_at < now)
        r.actions = allowed_events(r, request.user)
    return render(request, "borrowing/staff_requests.html", {
        "tab": tab, "counts": counts, "page_obj": page, "q": q,
        "querystring": urlencode({k: v for k, v in request.GET.items() if k not in ("page",)}),
        "tab_querystring": querystring,
    })


def _staff_post(request, pk, func, success, *extra):
    req = get_object_or_404(BorrowRequest, pk=pk)
    _action(request, func, success, req, request.user, *extra)
    return redirect(_next_url(request, req.get_absolute_url()))


@staff_required
@require_POST
def request_approve(request, pk):
    return _staff_post(request, pk, services.approve, _("The request was approved."))


@staff_required
@require_POST
def request_reject(request, pk):
    reason = request.POST.get("reason", "").strip()
    return _staff_post(request, pk, services.reject, _("The request was rejected."), reason)


@staff_required
@require_POST
def request_hand_over(request, pk):
    return _staff_post(request, pk, services.hand_over, _("The equipment was handed over."))


@staff_required
def request_return(request, pk):
    req = get_object_or_404(_request_qs(), pk=pk)
    if req.status not in ON_LOAN:
        messages.error(request, _("This request is not on loan."))
        return redirect(req)
    items = req.items.select_related("equipment").order_by("equipment_id", "pk")
    form = ReturnForm(request.POST or None, request.FILES or None, items=items)
    if request.method == "POST" and form.is_valid():
        try:
            record = services.receive_return(req, request.user, form.results(), form.cleaned_data["note"],
                                             form.cleaned_data["images"])
        except (ValidationError, TransitionError) as exc:
            form.add_error(None, _messages_of(exc))
        else:
            for image in record.images.all():
                try:
                    resize_image(image.image)
                except Exception:  # noqa: BLE001 - a failed resize must not undo a completed return
                    pass
            messages.success(request, _("The return was recorded."))
            return redirect(req)
    return render(request, "borrowing/request_return.html", {"req": req, "form": form})


@all_roles
def history(request):
    staff = _is_staff(request.user)
    form = HistoryFilterForm(request.GET or None, show_user=staff)
    qs = _request_qs()
    if not staff:
        qs = qs.filter(user=request.user)
    if form.is_valid():
        d = form.cleaned_data
        if d.get("date_from"):
            qs = qs.filter(borrow_at__date__gte=d["date_from"])
        if d.get("date_to"):
            qs = qs.filter(borrow_at__date__lte=d["date_to"])
        if d.get("status"):
            qs = qs.filter(status=d["status"])
        if d.get("equipment"):
            qs = qs.filter(items__equipment=d["equipment"])
        user_q = (d.get("user") or "").strip()
        if staff and user_q:
            qs = qs.filter(Q(user__first_name__icontains=user_q) | Q(user__last_name__icontains=user_q)
                           | Q(user__username__icontains=user_q) | Q(user__student_id__icontains=user_q))
    page, querystring = _paginate(request, qs.distinct().order_by("-borrow_at"))
    return render(request, "borrowing/history.html", {
        "form": form, "page_obj": page, "querystring": querystring, "is_staff_user": staff,
    })
