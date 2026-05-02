from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils.text import slugify
from api.models import Category, Product, ProductImage
import os
import boto3
from urllib.parse import urlparse, urljoin
from urllib.request import urlopen


class Command(BaseCommand):
    help = 'Seed database with initial product data'

    def add_arguments(self, parser):
        parser.add_argument(
            "--is-local",
            action="store_true",
            help="When set, read images from local filesystem. Default uses Cloudflare/R2 paths.",
        )

    def _env_bool(self, name: str, default: bool = False) -> bool:
        value = os.environ.get(name)
        if value is None:
            return default
        return value.strip().lower() in ("1", "true", "yes", "y", "on")

    def _is_r2_media_enabled(self) -> bool:
        """Whether default media storage points to R2/S3 backend."""
        try:
            default_storage = settings.STORAGES.get("default", {})
            backend = default_storage.get("BACKEND", "")
            return backend == "storages.backends.s3boto3.S3Boto3Storage"
        except Exception:
            return False

    def _normalize_remote_image_name(self, source_image_path: str) -> str:
        """
        Convert R2 path/url into storage object name.
        Examples:
          /lareesha/test/4.jpg -> lareesha/test/4.jpg
          https://<r2-public>/lareesha/test/4.jpg -> lareesha/test/4.jpg
        """
        if not source_image_path:
            return ""

        image_name = source_image_path.strip()
        if image_name.startswith("http://") or image_name.startswith("https://"):
            image_name = urlparse(image_name).path
        media_url = (getattr(settings, "MEDIA_URL", "") or "").strip()
        if media_url and image_name.startswith(media_url):
            image_name = image_name[len(media_url):]

        normalized = image_name.lstrip("/")
        bucket_name = (os.environ.get("AWS_STORAGE_BUCKET_NAME") or "").strip().strip("/")
        if bucket_name and normalized.startswith(f"{bucket_name}/"):
            normalized = normalized[len(bucket_name) + 1:]
        return normalized

    def _get_r2_client(self):
        endpoint_url = (os.environ.get("AWS_S3_ENDPOINT_URL") or "").strip()
        access_key = (os.environ.get("AWS_ACCESS_KEY_ID") or "").strip()
        secret_key = (os.environ.get("AWS_SECRET_ACCESS_KEY") or "").strip()
        if not (endpoint_url and access_key and secret_key):
            return None
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=os.environ.get("AWS_S3_REGION_NAME", "us-east-1"),
        )

    def _build_remote_image_url(self, source_image_path: str) -> str:
        """Build full remote URL for a Cloudflare/R2 object path."""
        image_path = (source_image_path or "").strip()
        if image_path.startswith("http://") or image_path.startswith("https://"):
            return image_path

        # If input path includes bucket prefix (e.g. /lareesha/test/1.jpg),
        # strip it for public R2 URL paths that are typically /test/1.jpg.
        bucket_name = (os.environ.get("AWS_STORAGE_BUCKET_NAME") or "").strip().strip("/")
        normalized_path = image_path.lstrip("/")
        if bucket_name and normalized_path.startswith(f"{bucket_name}/"):
            normalized_path = normalized_path[len(bucket_name) + 1:]

        public_base = (os.environ.get("R2_PUBLIC_URL") or getattr(settings, "MEDIA_URL", "") or "").strip()
        if not public_base.startswith("http://") and not public_base.startswith("https://"):
            return ""

        return urljoin(public_base.rstrip("/") + "/", normalized_path)

    def load_remote_image(self, source_image_path: str, image_name: str):
        """Download image from R2 (S3 API first, then public URL fallback)."""
        object_key = self._normalize_remote_image_name(source_image_path)
        bucket_name = (os.environ.get("AWS_STORAGE_BUCKET_NAME") or "").strip()
        r2_client = self._get_r2_client()

        if r2_client and bucket_name and object_key:
            try:
                obj = r2_client.get_object(Bucket=bucket_name, Key=object_key)
                return ContentFile(obj["Body"].read(), name=image_name)
            except Exception as e:
                self.stdout.write(
                    self.style.WARNING(f'Failed to fetch R2 object {bucket_name}/{object_key}: {e}')
                )

        remote_url = self._build_remote_image_url(source_image_path)
        if not remote_url:
            self.stdout.write(self.style.WARNING(f'Unable to build remote URL for: {source_image_path}'))
            return None

        try:
            with urlopen(remote_url) as response:
                return ContentFile(response.read(), name=image_name)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Failed to download image from {remote_url}: {e}'))
            return None

    def load_local_image(self, image_path, image_name):
        """Load image from local path and return ContentFile object."""
        try:
            with open(image_path, "rb") as image_file:
                return ContentFile(image_file.read(), name=image_name)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Failed to load image from {image_path}: {e}'))
        return None

    def get_local_images(self, images_dir):
        """Return sorted list of supported image files in a directory."""
        allowed_extensions = (".jpg", ".jpeg", ".png", ".webp", ".gif")
        if not os.path.isdir(images_dir):
            return []

        images = []
        for file_name in sorted(os.listdir(images_dir)):
            if file_name.lower().endswith(allowed_extensions):
                images.append(os.path.join(images_dir, file_name))
        return images

    def handle(self, *args, **kwargs):
        is_local = kwargs.get("is_local") or self._env_bool("SEED_IMAGES_LOCAL", default=False)
        self.stdout.write(f'Seeding database... (is_local={is_local})')
        # Instance.delete() so FileField + signals remove files from R2 (QuerySet.delete() skips this).
        for image in list(ProductImage.objects.all()):
            image.delete()
        Product.objects.all().delete()
        Category.objects.all().delete()

        def get_or_create_category(name: str) -> Category:
            base_name = (name or '').strip() or 'Uncategorized'
            base_slug = slugify(base_name) or 'uncategorized'
            # Important: we want ONE category per name.
            # The previous implementation always generated a new unique slug,
            # which created duplicates like necklaces, necklaces-2, necklaces-3, etc.
            existing = Category.objects.filter(name=base_name).first()
            if existing:
                return existing

            slug = base_slug
            i = 2
            while Category.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{i}"
                i += 1

            return Category.objects.create(name=base_name, slug=slug)

        products_data = [
            {
                'name': 'AD Stone white chocker with earrings',
                'description': 'AD stone white choker with matching earrings.',
                'original_price': 369.00,
                'sale_price': 369.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/1.jpg',
                ]
            },
            {
                'name': 'Gold heart drop choker',
                'description': 'Gold heart drop choker with elegant detailing.',
                'original_price': 249.00,
                'sale_price': 249.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/2.jpg',
                ]
            },
            {
                'name': 'Pink stone choker with earrings',
                'description': 'Pink stone choker set with matching earrings.',
                'original_price': 899.00,
                'sale_price': 899.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/3.jpg',
                ]
            },
            {
                'name': 'Green stone choker with earrings',
                'description': 'Green stone choker set with matching earrings.',
                'original_price': 899.00,
                'sale_price': 899.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/4.jpg',
                ]
            },
            {
                'name': 'Violet Stone choker with earrings',
                'description': 'Violet stone choker set with matching earrings.',
                'original_price': 899.00,
                'sale_price': 899.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/5.jpg'
                ]
            },
            {
                'name': 'Pearl stone drop necklace',
                'description': 'Pearl stone drop necklace with classic styling.',
                'original_price': 199.00,
                'sale_price': 199.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/6.jpg'
                ]
            },
            {
                'name': 'Green and maroon mango necklace with earrings',
                'description': 'Green and maroon mango necklace set with matching earrings.',
                'original_price': 499.00,
                'sale_price': 499.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/7.jpg'
                ]
            },
            {
                'name': 'Antique mango necklace with earrings',
                'description': 'Antique mango necklace set with matching earrings.',
                'original_price': 449.00,
                'sale_price': 449.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/8.jpg'
                ]
            },
            {
                'name': 'Lotus necklace with earrings',
                'description': 'Lotus necklace set with matching earrings.',
                'original_price': 299.00,
                'sale_price': 299.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/9.jpg'
                ]
            },
            {
                'name': 'Royal Tricolor Stone Choker',
                'description': 'Royal tricolor stone choker with matching earrings.',
                'original_price': 899.00,
                'sale_price': 899.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/10.jpg'
                ]
            },
            {
                'name': 'Multi colour stone choker with earrings',
                'description': 'Multi colour stone choker set with matching earrings.',
                'original_price': 899.00,
                'sale_price': 899.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/11.jpg'
                ]
            },
            {
                'name': 'Choker with pearl droplets',
                'description': 'Choker with pearl droplets and matching earrings.',
                'original_price': 329.00,
                'sale_price': 329.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/12.jpg'
                ]
            },
            {
                'name': 'Necklace set with earrings',
                'description': 'Necklace set with matching earrings.',
                'original_price': 349.00,
                'sale_price': 349.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/13.jpg'
                ]
            },
            {
                'name': 'Coin with multi colour stone choker with earrings',
                'description': 'Coin style multi colour stone choker with matching earrings.',
                'original_price': 449.00,
                'sale_price': 449.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/14.jpg'
                ]
            },
            {
                'name': 'Palak with pearl droplet necklace and earrings',
                'description': 'Palak necklace with pearl droplets and matching earrings.',
                'original_price': 799.00,
                'sale_price': 799.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/15.jpg'
                ]
            },
            {
                'name': 'Maroon and Green rain droplet necklace and earrings',
                'description': 'Maroon and green rain droplet necklace set with matching earrings.',
                'original_price': 329.00,
                'sale_price': 329.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/16.jpg'
                ]
            },
            {
                'name': 'Mango motif kemp necklace with earrings',
                'description': 'Mango motif kemp necklace set with matching earrings.',
                'original_price': 569.00,
                'sale_price': 569.00,
                'tax_percentage': 0,
                'category': get_or_create_category('Necklaces'),
                'new_in': True,
                'no_of_stock': 10,
                'images': [
                    '/test/17.jpg'
                ]
            }
        ]

        for product_data in products_data:
            images = product_data.pop('images', [])
            product = Product.objects.create(**product_data)
            
            for idx, source_image_path in enumerate(images):
                extension = os.path.splitext(source_image_path)[1] or ".jpg"
                image_name = f"{product.id}_{idx}{extension}"

                if is_local:
                    if not os.path.isfile(source_image_path):
                        self.stdout.write(
                            self.style.WARNING(f'Image file not found locally: {source_image_path}')
                        )
                        continue

                    image_content = self.load_local_image(source_image_path, image_name)

                    if image_content:
                        ProductImage.objects.create(
                            product=product,
                            image=image_content,
                            order=idx
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Loaded local image {os.path.basename(source_image_path)} for: {product.name}'
                            )
                        )
                    else:
                        self.stdout.write(self.style.WARNING(f'Skipped image for: {product.name}'))
                    continue

                else:
                    image_content = self.load_remote_image(source_image_path, image_name)
                    if image_content:
                        ProductImage.objects.create(
                            product=product,
                            image=image_content,
                            order=idx
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Loaded R2 image {source_image_path} as {image_name} for: {product.name}'
                            )
                        )
                    else:
                        self.stdout.write(self.style.WARNING(f'Skipped image for: {product.name}'))
            
            self.stdout.write(self.style.SUCCESS(f'Created product: {product.name}'))

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
