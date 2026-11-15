from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from borrowing.availability import STATUS_BADGE, display_status, free_now
from core.permissions import StaffRequiredMixin

from .forms import CategoryForm, EquipmentFilterForm, EquipmentForm, ImportForm
from .importer import build_template, import_equipment
from .models import Category, Equipment
from .services import TZ, availability_strip, filter_equipment, resize_image


class EquipmentListView(LoginRequiredMixin, TemplateView):
    template_name = "inventory/equipment_list.html"
    paginate_by = 12

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = EquipmentFilterForm(self.request.GET or None)
        qs = Equipment.objects.active().select_related("category")
        data = form.cleaned_data if form.is_bound and form.is_valid() else {}
        items = filter_equipment(qs, data)
        page = Paginator(items, self.paginate_by).get_page(self.request.GET.get("page"))
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(form=form, page_obj=page, equipment_list=page.object_list,
                   querystring=params.urlencode(), date_filter=data.get("date"))
        return ctx


class EquipmentDetailView(LoginRequiredMixin, DetailView):
    model = Equipment
    template_name = "inventory/equipment_detail.html"
    context_object_name = "eq"

    def get_queryset(self):
        qs = Equipment.objects.select_related("category")
        if not self.request.user.is_lab_staff:
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        eq = self.object
        status = display_status(eq)
        ctx.update(status=status, badge=STATUS_BADGE[status], free_qty=free_now(eq),
                   strip=availability_strip(eq, timezone.now().astimezone(TZ).date()))
        return ctx


class _EquipmentFormMixin(StaffRequiredMixin):
    model = Equipment
    form_class = EquipmentForm
    template_name = "inventory/equipment_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        if "image" in form.changed_data and self.object.image:
            resize_image(self.object.image)
        messages.success(self.request, _("Equipment saved."))
        return response


class EquipmentCreateView(_EquipmentFormMixin, CreateView):
    pass


class EquipmentUpdateView(_EquipmentFormMixin, UpdateView):
    pass


class EquipmentDeleteView(StaffRequiredMixin, DetailView):
    model = Equipment
    template_name = "inventory/equipment_confirm_delete.html"
    context_object_name = "eq"

    def post(self, request, *args, **kwargs):
        eq = self.get_object()
        eq.is_active = False
        eq.save(update_fields=["is_active", "updated_at"])
        messages.success(request, _("Equipment deleted."))
        return redirect("inventory:list")


class CategoryListView(StaffRequiredMixin, ListView):
    model = Category
    template_name = "inventory/category_list.html"


class _CategoryMixin(StaffRequiredMixin):
    model = Category
    form_class = CategoryForm
    template_name = "inventory/category_form.html"
    success_url = reverse_lazy("inventory:category_list")


class CategoryCreateView(_CategoryMixin, CreateView):
    pass


class CategoryUpdateView(_CategoryMixin, UpdateView):
    pass


class CategoryDeleteView(StaffRequiredMixin, View):
    def get(self, request, pk):
        return render(request, "inventory/category_confirm_delete.html",
                      {"object": get_object_or_404(Category, pk=pk)})

    def post(self, request, pk):
        category = get_object_or_404(Category, pk=pk)
        try:
            category.delete()
        except ProtectedError:
            messages.error(request, _("This category still has equipment and cannot be deleted."))
        else:
            messages.success(request, _("Category deleted."))
        return redirect("inventory:category_list")


class EquipmentImportView(StaffRequiredMixin, View):
    template_name = "inventory/import.html"

    def get(self, request):
        return render(request, self.template_name, {"form": ImportForm()})

    def post(self, request):
        form = ImportForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form})
        dry_run = form.cleaned_data["dry_run"]
        result = import_equipment(form.cleaned_data["file"], dry_run=dry_run)
        if result.ok and not dry_run:
            messages.success(request, _("Import complete: %(c)d created, %(u)d updated.")
                             % {"c": result.created, "u": result.updated})
            return redirect("inventory:list")
        return render(request, self.template_name, {"form": form, "result": result, "dry_run": dry_run})


class ImportTemplateView(StaffRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        response["Content-Disposition"] = 'attachment; filename="equipment_import_template.xlsx"'
        build_template().save(response)
        return response
