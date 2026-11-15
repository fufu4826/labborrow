from django.core.management.base import BaseCommand

from notifications.models import NotificationStatus
from notifications.services import retry_failed


class Command(BaseCommand):
    help = "Resend failed LINE notifications (attempts < 3)."

    def handle(self, *args, **options):
        results = retry_failed()
        sent = sum(1 for r in results if r and r.status == NotificationStatus.SENT)
        self.stdout.write(f"Retried {len(results)} notification(s): {sent} sent, {len(results) - sent} not sent.")
