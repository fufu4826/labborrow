"""Extract and compile translations without GNU gettext (not installed on Windows dev machines).

    python manage.py i18n extract    # update locale/<lang>/LC_MESSAGES/django.po, keeps existing msgstr
    python manage.py i18n compile    # write django.mo next to each .po
    python manage.py i18n stats      # translated / total per language

Extraction covers gettext, gettext_lazy, pgettext(_lazy), ngettext(_lazy) calls written as `_()` or by
name in .py files, and {% translate %} / {% blocktranslate %} in templates (through Django's own
`templatize`, the same path `makemessages` uses).
"""
import ast
import re
from pathlib import Path

import polib
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.translation.template import templatize

SINGULAR = {"_", "gettext", "gettext_lazy", "gettext_noop"}
CONTEXT = {"pgettext", "pgettext_lazy"}
PLURAL = {"ngettext", "ngettext_lazy"}
SKIP_DIRS = {".venv", "migrations", "tests", "staticfiles", "media", "node_modules", "__pycache__"}


def _const(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_python(source, filename):
    """Yield (msgctxt, msgid, msgid_plural, occurrence)."""
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else (
            node.func.attr if isinstance(node.func, ast.Attribute) else None)
        args = node.args
        where = (filename, str(node.lineno))
        if name in SINGULAR and args and _const(args[0]) is not None:
            yield None, _const(args[0]), None, where
        elif name in CONTEXT and len(args) >= 2 and _const(args[0]) and _const(args[1]) is not None:
            yield _const(args[0]), _const(args[1]), None, where
        elif name in PLURAL and len(args) >= 2 and _const(args[0]) is not None and _const(args[1]) is not None:
            yield None, _const(args[0]), _const(args[1]), where


_LIT = r"u?'(?:[^'\\]|\\.)*'"
_TEMPLATE_CALL = re.compile(
    rf"\b(?P<fn>npgettext|pgettext|ngettext|gettext)\((?P<a>{_LIT})(?:,\s*(?P<b>{_LIT}))?(?:,\s*(?P<c>{_LIT}))?")


def extract_templatized(code, filename):
    """templatize() output is not valid Python, so pick the gettext calls out with a regex."""
    for m in _TEMPLATE_CALL.finditer(code):
        lit = [ast.literal_eval(m.group(k)) if m.group(k) else None for k in ("a", "b", "c")]
        line = str(code.count("\n", 0, m.start()) + 1)
        where = (filename, line)
        fn = m.group("fn")
        if fn == "gettext":
            yield None, lit[0], None, where
        elif fn == "pgettext":
            yield lit[0], lit[1], None, where
        elif fn == "ngettext":
            yield None, lit[0], lit[1], where
        else:
            yield lit[0], lit[1], lit[2], where


def source_files(base):
    for path in sorted(base.rglob("*")):
        if any(part in SKIP_DIRS for part in path.relative_to(base).parts):
            continue
        if path.suffix in (".py", ".html", ".txt") and path.is_file():
            yield path


class Command(BaseCommand):
    help = "Extract / compile translations (pure Python, no GNU gettext needed)."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["extract", "compile", "stats"])

    def handle(self, action, **opts):
        base = Path(settings.BASE_DIR)
        langs = [code for code, _name in settings.LANGUAGES]
        locale_dir = Path(settings.LOCALE_PATHS[0])
        if action == "extract":
            self.extract(base, locale_dir, langs)
        elif action == "compile":
            self.compile(locale_dir, langs)
        else:
            self.stats(locale_dir, langs)

    def collect(self, base):
        found = {}
        for path in source_files(base):
            rel = path.relative_to(base).as_posix()
            text = path.read_text(encoding="utf-8-sig")
            if path.suffix == ".py":
                if rel.startswith("core/management/commands/i18n"):
                    continue
                entries = extract_python(text, rel)
            else:
                if "{%" not in text:
                    continue
                try:
                    code = templatize(text, origin=rel)
                except Exception as exc:  # noqa: BLE001 - report and continue
                    self.stderr.write(f"skip {rel}: {exc}")
                    continue
                entries = extract_templatized(code, rel)
            for ctx, msgid, plural, where in entries:
                if not msgid:
                    continue
                key = (ctx, msgid)
                entry = found.setdefault(key, {"plural": plural, "where": []})
                entry["where"].append(where)
        return found

    def extract(self, base, locale_dir, langs):
        found = self.collect(base)
        for lang in langs:
            po_path = locale_dir / lang / "LC_MESSAGES" / "django.po"
            po_path.parent.mkdir(parents=True, exist_ok=True)
            old = polib.pofile(str(po_path)) if po_path.exists() else None
            old_map = {(e.msgctxt, e.msgid): e for e in old} if old else {}
            po = polib.POFile(wrapwidth=0)
            po.metadata = {
                "Project-Id-Version": "labborrow",
                "Language": lang,
                "MIME-Version": "1.0",
                "Content-Type": "text/plain; charset=UTF-8",
                "Content-Transfer-Encoding": "8bit",
                "Plural-Forms": "nplurals=1; plural=0;" if lang == "th" else "nplurals=2; plural=(n != 1);",
            }
            for (ctx, msgid), info in sorted(found.items(), key=lambda kv: (kv[1]["where"][0], kv[0][1])):
                prev = old_map.get((ctx, msgid))
                entry = polib.POEntry(msgctxt=ctx, msgid=msgid, occurrences=info["where"][:3])
                if info["plural"]:
                    entry.msgid_plural = info["plural"]
                    n = 1 if lang == "th" else 2
                    entry.msgstr_plural = (prev.msgstr_plural if prev and prev.msgstr_plural
                                           else {i: "" for i in range(n)})
                else:
                    entry.msgstr = prev.msgstr if prev else ""
                if "python-format" in (prev.flags if prev else []) or "%(" in msgid:
                    entry.flags.append("python-format")
                po.append(entry)
            po.save(str(po_path))
            done = sum(1 for e in po if e.translated())
            self.stdout.write(f"{lang}: {len(po)} messages, {done} translated -> {po_path}")

    def compile(self, locale_dir, langs):
        for lang in langs:
            po_path = locale_dir / lang / "LC_MESSAGES" / "django.po"
            if not po_path.exists():
                raise CommandError(f"missing {po_path}; run extract first")
            po = polib.pofile(str(po_path))
            for entry in po:
                if entry.msgstr and "%(" in entry.msgid:
                    self._check_placeholders(entry, lang)
            po.save_as_mofile(str(po_path.with_suffix(".mo")))
            self.stdout.write(f"{lang}: compiled {sum(1 for e in po if e.translated())} messages")

    def _check_placeholders(self, entry, lang):
        import re
        want = sorted(re.findall(r"%\(\w+\)[sd]", entry.msgid))
        got = sorted(re.findall(r"%\(\w+\)[sd]", entry.msgstr))
        if want != got:
            raise CommandError(f"[{lang}] placeholder mismatch in {entry.msgid!r}: {got} != {want}")

    def stats(self, locale_dir, langs):
        for lang in langs:
            po_path = locale_dir / lang / "LC_MESSAGES" / "django.po"
            if po_path.exists():
                po = polib.pofile(str(po_path))
                self.stdout.write(f"{lang}: {po.percent_translated()}% ({len(po.translated_entries())}/{len(po)})")
