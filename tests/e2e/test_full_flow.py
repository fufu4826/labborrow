import pytest
from PIL import Image

from inventory.models import Category, Equipment
from tests.e2e.conftest import bkk_slot
from tests.factories import make_staff, make_student

PW = "pass12345!"
pytestmark = pytest.mark.django_db(transaction=True)


def _login(page, username):
    resp = page.goto("/accounts/login/")
    assert resp.status < 400
    page.fill("input[name=username]", username)
    page.fill("input[name=password]", PW)
    with page.expect_navigation():
        page.click("form:has(input[name=username]) button[type=submit]")
    assert "/accounts/login" not in page.url, page.inner_text("body")[:600]


class Checker:
    """Per-user helper: navigate, assert no error / overflow, screenshot every page."""

    def __init__(self, page, shots, prefix):
        self.page, self.shots, self.prefix, self.n = page, shots, prefix, 0

    def visit(self, url):
        resp = self.page.goto(url)
        assert resp.status < 400, f"{url} -> {resp.status}"
        self.check(url)

    def check(self, label):
        self.n += 1
        self.page.wait_for_load_state("load")
        name = label.strip("/").replace("/", "_").replace("?", "_").replace("=", "_")[:40] or "root"
        self.page.screenshot(path=str(self.shots / f"{self.prefix}_{self.n:02d}_{name}.png"), full_page=True)
        fits = self.page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert fits, f"horizontal overflow on {label} ({self.page.url})"
        body = self.page.content()
        assert "Traceback" not in body and "Server Error" not in body


def _post(page, selector):
    """Click a submit control and assert the resulting page is not an error."""
    with page.expect_navigation() as nav:
        page.click(selector)
    assert nav.value is None or nav.value.status < 400


def test_borrow_return_damage_flow(open_site, open_all_days, shots, tmp_path):
    cat = Category.objects.create(name_th="หมวดทดสอบ", name_en="Test cat")
    eq = Equipment.objects.create(asset_code="E2E-001", name_th="กล้องทดสอบ", category=cat, quantity_total=5)
    eq2 = Equipment.objects.create(asset_code="E2E-002", name_th="ขาตั้งทดสอบ", category=cat, quantity_total=3)
    student = make_student(language="th")
    staff = make_staff(language="th")

    # 1. student creates a request on a phone-sized screen
    sp = open_site(375, 812)
    _login(sp, student.username)
    s = Checker(sp, shots, "student")
    s.visit("/equipment/")
    sp.click(f"a[href='/equipment/{eq.pk}/']")
    sp.wait_for_load_state("load")
    s.check("equipment_detail")
    sp.click(f"a[href^='/borrow/request/new/'][href$='equipment={eq.pk}']")
    sp.wait_for_load_state("load")
    s.check("request_form")
    sp.fill("input[name='form-0-quantity']", "2")
    sp.fill("input[name=borrow_at]", bkk_slot(1))
    sp.fill("input[name=due_at]", bkk_slot(1, 2))
    sp.fill("input[name=purpose]", "e2e test purpose")
    _post(sp, "form.card button[type=submit]")
    s.check("after_submit")
    assert "/borrow/request/new" not in sp.url, sp.inner_text("body")[:500]
    s.visit("/borrow/mine/")
    assert "รออนุมัติ" in sp.inner_text("body")
    href = sp.locator("a[href^='/borrow/requests/']:visible").first.get_attribute("href")
    req_pk = int(href.strip("/").split("/")[-1])

    # 2. staff approves and hands over
    tp = open_site(1280, 900)
    _login(tp, staff.username)
    t = Checker(tp, shots, "staff")
    t.visit("/borrow/staff/requests/")
    t.visit(f"/borrow/requests/{req_pk}/")
    _post(tp, f"form[action='/borrow/requests/{req_pk}/approve/'] button")
    t.check("approved")
    t.visit(f"/borrow/requests/{req_pk}/")
    _post(tp, f"form[action='/borrow/requests/{req_pk}/hand-over/'] button")
    t.check("handed_over")

    # 3. staff receives the return: 1 good + 1 damaged + photo
    png = tmp_path / "condition.png"
    Image.new("RGB", (64, 64), (200, 30, 30)).save(png)
    t.visit(f"/borrow/requests/{req_pk}/return/")
    assert tp.locator("input[name^=good_]").count() == 1
    tp.fill("input[name^=good_]", "1")
    tp.fill("input[name^=damaged_]", "1")
    tp.set_input_files("input[name=images]", str(png))
    _post(tp, "form.card button[type=submit]")
    t.check("returned")
    assert "/return/" not in tp.url, tp.inner_text("body")[:500]

    # 4. student sees returned status and 1 unit out of service
    s.visit("/borrow/history/")
    assert "คืนแล้ว" in sp.inner_text("body")
    s.visit(f"/equipment/{eq.pk}/")
    assert sp.locator("dl.row dd").nth(2).inner_text().strip() == "1"
    assert Equipment.objects.get(pk=eq.pk).quantity_out_of_service == 1

    # 5. damage report on another item
    s.visit(f"/maintenance/new/?equipment={eq2.pk}")
    sp.select_option("select[name=equipment]", str(eq2.pk))
    sp.fill("input[name=quantity]", "1")
    sp.fill("input[name=problem]", "e2e broken leg")
    _post(sp, "form.card button[type=submit]")
    s.check("damage_submitted")
    assert "/maintenance/new" not in sp.url, sp.inner_text("body")[:500]
    s.visit("/maintenance/")


def test_permissions_and_dashboard(open_site, open_all_days, shots):
    student = make_student(language="th")
    staff = make_staff(language="th")
    sp = open_site(375, 812)
    _login(sp, student.username)
    assert sp.goto("/borrow/staff/requests/").status == 403

    tp = open_site(1280, 900)
    _login(tp, staff.username)
    Checker(tp, shots, "dash").visit("/reports/dashboard/")
    assert tp.locator("canvas").count() >= 1
