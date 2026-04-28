from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import Product, ProductImage


@receiver(pre_delete, sender=ProductImage)
def delete_product_image_file(sender, instance, **kwargs):
    if instance.image:
        instance.image.delete(save=False)


@receiver(pre_delete, sender=Product)
def delete_all_product_image_files(sender, instance, **kwargs):
    # CASCADE can bulk-delete child rows without per-instance signals; remove files from storage here.
    for row in instance.images.all():
        if row.image:
            row.image.delete(save=False)
