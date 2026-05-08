from decimal import Decimal
import re

from .models import ShippingZone, ShippingZonePinPrefix


def _normalized_pincode(zip_code: str) -> str:
    digits = re.sub(r'\D', '', zip_code or '')
    return digits[:6]


def resolve_shipping_zone_by_pincode(zip_code: str):
    """Resolve the best matching zone from a 3-6 digit prefix, else fallback zone."""
    normalized = _normalized_pincode(zip_code)
    if len(normalized) >= 3:
        for length in range(min(len(normalized), 6), 2, -1):
            candidate = normalized[:length]
            mapping = (
                ShippingZonePinPrefix.objects.select_related('zone')
                .filter(prefix=candidate, zone__is_active=True)
                .order_by('zone__priority')
                .first()
            )
            if mapping:
                return mapping.zone

    return (
        ShippingZone.objects.filter(is_active=True, is_fallback=True)
        .order_by('priority', 'id')
        .first()
    )


def calculate_shipping_for_address(address, subtotal: Decimal) -> Decimal:
    """Calculate shipping for destination address based on configured zone rules."""
    if not address:
        return Decimal('0.00')

    zone = resolve_shipping_zone_by_pincode(address.zip_code)
    return calculate_shipping_for_zone(zone, subtotal)


def calculate_shipping_for_zone(zone, subtotal: Decimal) -> Decimal:
    """Apply shipping fee and free-shipping threshold for a resolved zone."""
    if not zone:
        return Decimal('0.00')

    if zone.free_shipping_min_order is not None and subtotal >= zone.free_shipping_min_order:
        return Decimal('0.00')

    return zone.base_fee
