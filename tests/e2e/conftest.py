"""Browser E2E fixtures. Enabled only with E2E=1 (keeps the default suite fast)."""
import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

# Playwright's sync API runs an event loop in this thread; allow ORM calls from the test body.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

SHOTS = Path(__file__).parent / "screenshots"
BKK = ZoneInfo("Asia/Bangkok")


def pytest_collection_modifyitems(config, items):
    if os.environ.get("E2E") == "1":
        return
    skip = pytest.mark.skip(reason="set E2E=1 to run browser end-to-end tests")
    for item in items:
        if "tests/e2e" in item.nodeid.replace("\\", "/"):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)
        yield b
        b.close()


@pytest.fixture
def open_site(browser, live_server):
    """Return open_site(width, height) -> a fresh page in its own context; closed at teardown."""
    contexts = []

    def _open(width, height):
        ctx = browser.new_context(viewport={"width": width, "height": height}, locale="th-TH",
                                  timezone_id="Asia/Bangkok", base_url=live_server.url)
        contexts.append(ctx)
        return ctx.new_page()

    yield _open
    for c in contexts:
        c.close()


@pytest.fixture
def shots():
    SHOTS.mkdir(exist_ok=True)
    return SHOTS


@pytest.fixture
def open_all_days(transactional_db):
    from core.models import SystemSetting

    s, _ = SystemSetting.objects.get_or_create(pk=1)
    s.open_weekdays = "0,1,2,3,4,5,6"
    s.open_time = datetime.time(0, 0)
    s.close_time = datetime.time(23, 59)
    s.save()
    return s


def bkk_slot(days=1, hours=0):
    """Now + days, rounded up to the next hour, (+hours) as YYYY-MM-DDTHH:MM in Asia/Bangkok."""
    t = datetime.datetime.now(BKK).replace(minute=0, second=0, microsecond=0)
    t += datetime.timedelta(days=days, hours=hours + 1)
    return t.strftime("%Y-%m-%dT%H:%M")
