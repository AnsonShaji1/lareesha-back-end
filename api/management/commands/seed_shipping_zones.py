from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import ShippingZone, ShippingZonePinPrefix


class Command(BaseCommand):
    help = "Seed shipping zones + pincode prefixes (idempotent upsert)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to DB.",
        )

    @transaction.atomic
    def handle(self, *args, **kwargs):
        dry_run = bool(kwargs.get("dry_run"))

        zones_payload = [
            {
                "code": "local-ernakulam",
                "name": "Local Ernakulam",
                "base_fee": Decimal("60.00"),
                "free_shipping_min_order": Decimal("2500.00"),
                "priority": 10,
                "is_active": True,
                "is_fallback": False,
            },
            {
                "code": "kerala-non-local",
                "name": "Kerala Non-Local",
                "base_fee": Decimal("120.00"),
                "free_shipping_min_order": Decimal("3500.00"),
                "priority": 20,
                "is_active": True,
                "is_fallback": False,
            },
            {
                "code": "national-fallback",
                "name": "National Fallback",
                "base_fee": Decimal("180.00"),
                "free_shipping_min_order": Decimal("5000.00"),
                "priority": 999,
                "is_active": True,
                "is_fallback": True,
            },
        ]

        local_prefixes = ["682", "683"]
        kerala_prefixes = [
            "670",
            "671",
            "672",
            "673",
            "674",
            "675",
            "676",
            "677",
            "678",
            "679",
            "680",
            "681",
            "684",
            "685",
            "686",
            "690",
            "691",
            "695",
        ]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN: no database writes will be performed."))

        zone_by_code: dict[str, ShippingZone] = {}
        created_zones = 0
        updated_zones = 0

        for payload in zones_payload:
            code = payload["code"]
            defaults = {k: v for k, v in payload.items() if k != "code"}

            existing = ShippingZone.objects.filter(code=code).first()
            if existing is None:
                created_zones += 1
                if not dry_run:
                    zone = ShippingZone.objects.create(code=code, **defaults)
                else:
                    zone = ShippingZone(code=code, **defaults)
                zone_by_code[code] = zone
                continue

            changed = False
            for key, value in defaults.items():
                if getattr(existing, key) != value:
                    changed = True
                    break

            if changed:
                updated_zones += 1
                if not dry_run:
                    for key, value in defaults.items():
                        setattr(existing, key, value)
                    existing.save(update_fields=list(defaults.keys()) + ["updated_at"])

            zone_by_code[code] = existing

        # Ensure only one fallback zone is flagged.
        fallback_code = "national-fallback"
        fallback_zone = zone_by_code.get(fallback_code)
        if fallback_zone and not dry_run:
            ShippingZone.objects.exclude(id=fallback_zone.id).filter(is_fallback=True).update(is_fallback=False)

        # Upsert prefixes -> zones
        prefix_pairs = []
        prefix_pairs.extend([(p, "local-ernakulam") for p in local_prefixes])
        prefix_pairs.extend([(p, "kerala-non-local") for p in kerala_prefixes])

        created_prefixes = 0
        updated_prefixes = 0

        for prefix, zone_code in prefix_pairs:
            zone = zone_by_code.get(zone_code)
            if zone is None:
                raise RuntimeError(f"Missing zone for code: {zone_code}")

            existing = ShippingZonePinPrefix.objects.filter(prefix=prefix).select_related("zone").first()
            if existing is None:
                created_prefixes += 1
                if not dry_run:
                    ShippingZonePinPrefix.objects.create(prefix=prefix, zone=zone)
                continue

            if existing.zone_id != zone.id:
                updated_prefixes += 1
                if not dry_run:
                    existing.zone = zone
                    existing.save(update_fields=["zone"])

        self.stdout.write(
            self.style.SUCCESS(
                "Shipping zones seeded. "
                f"zones(created={created_zones}, updated={updated_zones}), "
                f"prefixes(created={created_prefixes}, updated={updated_prefixes})"
                + (" [dry-run]" if dry_run else "")
            )
        )

