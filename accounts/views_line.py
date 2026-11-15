from django.conf import settings
from django.shortcuts import redirect
from django.views.generic import TemplateView

from core.permissions import RoleRequiredMixin
from notifications import linking


class LineLinkView(RoleRequiredMixin, TemplateView):
    template_name = "accounts/line_link.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        basic_id = settings.LINE_OA_BASIC_ID
        ctx.update(
            linked=bool(self.request.user.line_user_id),
            basic_id=basic_id,
            add_url=f"https://line.me/R/ti/p/{basic_id}" if basic_id else "",
            qr_url=f"https://qr-official.line.me/sid/L/{basic_id.lstrip('@')}.png" if basic_id else "",
        )
        return ctx

    def post(self, request, *args, **kwargs):
        user = request.user
        if request.POST.get("action") == "unlink":
            user.line_user_id = ""
            user.save(update_fields=["line_user_id"])
            return redirect("accounts:line_link")
        code = linking.create_link_code(user)
        return self.render_to_response(self.get_context_data(code=code, expires=user.line_link_expires))
