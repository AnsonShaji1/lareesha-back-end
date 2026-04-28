from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.utils.text import slugify
from api.models import Category, Product, ProductImage
import os


class Command(BaseCommand):
    help = 'Seed database with initial product data'

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
        self.stdout.write('Seeding database...')
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
                    '/home/anson/Desktop/lareesha_img/1.jpg',
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
                    '/home/anson/Desktop/lareesha_img/2.jpg',
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
                    '/home/anson/Desktop/lareesha_img/3.jpg',
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
                    '/home/anson/Desktop/lareesha_img/4.jpg',
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
                    '/home/anson/Desktop/lareesha_img/5.jpg'
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
                    '/home/anson/Desktop/lareesha_img/6.jpg'
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
                    '/home/anson/Desktop/lareesha_img/7.jpg'
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
                    '/home/anson/Desktop/lareesha_img/8.jpg'
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
                    '/home/anson/Desktop/lareesha_img/9.jpg'
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
                    '/home/anson/Desktop/lareesha_img/10.jpg'
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
                    '/home/anson/Desktop/lareesha_img/11.jpg'
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
                    '/home/anson/Desktop/lareesha_img/12.jpg'
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
                    '/home/anson/Desktop/lareesha_img/13.jpg'
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
                    '/home/anson/Desktop/lareesha_img/14.jpg'
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
                    '/home/anson/Desktop/lareesha_img/15.jpg'
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
                    '/home/anson/Desktop/lareesha_img/16.jpg'
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
                    '/home/anson/Desktop/lareesha_img/17.jpg'
                ]
            }
        ]

        for product_data in products_data:
            images = product_data.pop('images', [])
            product = Product.objects.create(**product_data)
            
            for idx, source_image_path in enumerate(images):
                if not os.path.isfile(source_image_path):
                    self.stdout.write(
                        self.style.WARNING(f'Image file not found: {source_image_path}')
                    )
                    continue
                extension = os.path.splitext(source_image_path)[1] or ".jpg"
                image_name = f"{product.id}_{idx}{extension}"
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
            
            self.stdout.write(self.style.SUCCESS(f'Created product: {product.name}'))

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))
