from django.db.models.signals import pre_delete, post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Product, ProductImage, UserProfile


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


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """Make sure every user has a profile row for extra fields like phone/gender."""
    if created:
        UserProfile.objects.create(user=instance)
    else:
        # Backfill for existing users if missing.
        UserProfile.objects.get_or_create(user=instance)
