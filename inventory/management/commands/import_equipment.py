from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _

from inventory.importer import import_equipment


class Command(BaseCommand):
    help = "Import equipment from an .xlsx file."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, path, dry_run=False, **options):
        try:
            fh = open(path, "rb")
        except OSError as exc:
            raise CommandError(str(exc)) from exc
        with fh:
            result = import_equipment(fh, dry_run=dry_run)
        for row, msg in result.errors:
            self.stdout.write(f"row {row}: {msg}")
        self.stdout.write(_("Created: %(c)d, updated: %(u)d, errors: %(e)d") % {
            "c": result.created, "u": result.updated, "e": len(result.errors)})
        if dry_run:
            self.stdout.write(_("Dry run: nothing was saved."))
        if result.errors:
            raise CommandError(_("Import failed; nothing was saved."))
