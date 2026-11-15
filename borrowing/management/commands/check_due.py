from django.core.management.base import BaseCommand

from borrowing.services import run_due_checks


class Command(BaseCommand):
    help = "Mark overdue loans, send due reminders and expire unused bookings."

    def handle(self, *args, **options):
        counts = run_due_checks()
        self.stdout.write(
            f"overdue={counts['overdue']} due_soon={counts['due_soon']} expired={counts['expired']}")
