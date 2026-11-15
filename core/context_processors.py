from .permissions import BORROWERS, STAFF, has_role


def nav(request):
    user = request.user
    return {
        "is_staff_role": has_role(user, STAFF),
        "is_borrower_role": has_role(user, BORROWERS),
    }
