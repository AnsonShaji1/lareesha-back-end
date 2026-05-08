from decimal import Decimal, InvalidOperation

from django.contrib import admin
from django.shortcuts import render

from .shipping import calculate_shipping_for_zone, resolve_shipping_zone_by_pincode


def shipping_quote_admin_view(request):
    """Staff-only page to test pincode → zone → shipping fee."""
    context = {
        **admin.site.each_context(request),
        'title': 'Shipping quote tester',
        'zip_code': '',
        'subtotal': '',
        'result': None,
        'error': None,
    }

    if request.method == 'POST':
        zip_code = (request.POST.get('zip_code') or '').strip()
        subtotal_raw = (request.POST.get('subtotal') or '').strip()

        context['zip_code'] = zip_code
        context['subtotal'] = subtotal_raw

        if not zip_code:
            context['error'] = 'Pincode is required.'
        else:
            try:
                subtotal = Decimal(subtotal_raw or '0')
                if subtotal < 0:
                    context['error'] = 'Subtotal must be zero or greater.'
                else:
                    zone = resolve_shipping_zone_by_pincode(zip_code)
                    shipping_fee = calculate_shipping_for_zone(zone, subtotal)
                    context['result'] = {
                        'zone_name': zone.name if zone else None,
                        'zone_code': zone.code if zone else None,
                        'base_fee': float(zone.base_fee) if zone else None,
                        'free_shipping_min_order': (
                            float(zone.free_shipping_min_order)
                            if zone and zone.free_shipping_min_order is not None
                            else None
                        ),
                        'is_fallback': zone.is_fallback if zone else True,
                        'subtotal_display': float(round(subtotal, 2)),
                        'shipping_display': float(round(shipping_fee, 2)),
                    }
            except (InvalidOperation, TypeError):
                context['error'] = 'Subtotal must be a valid number.'

    return render(request, 'admin/shipping_quote.html', context)


shipping_quote_admin_view = admin.site.admin_view(shipping_quote_admin_view)
