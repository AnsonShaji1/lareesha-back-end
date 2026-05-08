from django.db import migrations
from decimal import Decimal


def seed_shipping_zones(apps, schema_editor):
    ShippingZone = apps.get_model('api', 'ShippingZone')
    ShippingZonePinPrefix = apps.get_model('api', 'ShippingZonePinPrefix')

    local_zone, _ = ShippingZone.objects.update_or_create(
        code='local-ernakulam',
        defaults={
            'name': 'Local Ernakulam',
            'base_fee': Decimal('60.00'),
            'free_shipping_min_order': Decimal('2500.00'),
            'priority': 10,
            'is_active': True,
            'is_fallback': False,
        },
    )

    kerala_zone, _ = ShippingZone.objects.update_or_create(
        code='kerala-non-local',
        defaults={
            'name': 'Kerala Non-Local',
            'base_fee': Decimal('120.00'),
            'free_shipping_min_order': Decimal('3500.00'),
            'priority': 20,
            'is_active': True,
            'is_fallback': False,
        },
    )

    national_zone, _ = ShippingZone.objects.update_or_create(
        code='national-fallback',
        defaults={
            'name': 'National Fallback',
            'base_fee': Decimal('180.00'),
            'free_shipping_min_order': Decimal('5000.00'),
            'priority': 999,
            'is_active': True,
            'is_fallback': True,
        },
    )

    # Ensure only one fallback is active.
    ShippingZone.objects.exclude(id=national_zone.id).filter(is_fallback=True).update(is_fallback=False)

    local_prefixes = ['682', '683']
    kerala_prefixes = [
        '670', '671', '672', '673', '674', '675', '676', '677', '678', '679',
        '680', '681', '684', '685', '686', '690', '691', '695',
    ]

    for prefix in local_prefixes:
        ShippingZonePinPrefix.objects.update_or_create(
            prefix=prefix,
            defaults={'zone': local_zone},
        )

    for prefix in kerala_prefixes:
        ShippingZonePinPrefix.objects.update_or_create(
            prefix=prefix,
            defaults={'zone': kerala_zone},
        )


def unseed_shipping_zones(apps, schema_editor):
    ShippingZone = apps.get_model('api', 'ShippingZone')
    ShippingZonePinPrefix = apps.get_model('api', 'ShippingZonePinPrefix')

    prefixes_to_remove = [
        '682', '683',
        '670', '671', '672', '673', '674', '675', '676', '677', '678', '679',
        '680', '681', '684', '685', '686', '690', '691', '695',
    ]
    ShippingZonePinPrefix.objects.filter(prefix__in=prefixes_to_remove).delete()

    ShippingZone.objects.filter(code__in=['local-ernakulam', 'kerala-non-local', 'national-fallback']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_shippingzone_shippingzonepinprefix'),
    ]

    operations = [
        migrations.RunPython(seed_shipping_zones, unseed_shipping_zones),
    ]

