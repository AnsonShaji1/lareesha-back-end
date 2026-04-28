from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import StockReservation, Order


class Command(BaseCommand):
    help = 'Clean up expired stock reservations'

    def handle(self, *args, **options):
        now = timezone.now()
        expired_reservations = StockReservation.objects.filter(expires_at__lt=now)
        count = expired_reservations.count()

        if count > 0:
            expired_order_ids = expired_reservations.values_list('order_id', flat=True).distinct()
            expired_reservations.delete()
            Order.objects.filter(id__in=expired_order_ids, payment_status='pending').update(
                status='cancelled',
                payment_status='failed',
                stock_reserved=False
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully cleaned up {count} expired stock reservations'))
        else:
            self.stdout.write(self.style.SUCCESS('No expired stock reservations found'))