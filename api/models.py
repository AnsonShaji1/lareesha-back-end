from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify


class Address(models.Model):
    """User address model for shipping and billing"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    full_name = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    address_line_1 = models.CharField(max_length=255, help_text="Street address")
    address_line_2 = models.CharField(max_length=255, blank=True, null=True, help_text="Apartment, suite, etc.")
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zip_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='India')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.full_name} - {self.address_line_1}, {self.city}"

    def save(self, *args, **kwargs):
        # Ensure only one default address per user
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True, blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Auto-populate slug from name if not set.
        # If the slug (and therefore category) already exists, block creation.
        if not self.slug:
            base_slug = slugify(self.name or '') or 'category'
            if Category.objects.filter(slug=base_slug).exclude(pk=self.pk).exists():
                from django.core.exceptions import ValidationError
                raise ValidationError({'name': 'Category already exists.'})
            self.slug = base_slug
        super().save(*args, **kwargs)


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    sale_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    new_in = models.BooleanField(default=False, help_text="Mark product to be shown in New In listing")
    no_of_stock = models.IntegerField(default=0)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=8.0, help_text="Tax percentage for this product (e.g., 5, 8, 12)")
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Shipping cost in rupees. Set 0 for free shipping, or custom amount")
    is_free_shipping_eligible = models.BooleanField(default=True, help_text="If True, this product qualifies for free shipping")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def get_reserved_stock(self):
        from django.utils import timezone
        from django.db.models import Sum
        
        # AUTO-CLEANUP: Delete expired stock reservations when calculating available stock
        # This ensures stock is automatically released after 15-minute TTL without manual intervention
        expired_reservations = StockReservation.objects.filter(
            product=self,
            expires_at__lt=timezone.now()
        )
        
        if expired_reservations.exists():
            # Get orders with expired reservations
            expired_order_ids = expired_reservations.values_list('order_id', flat=True).distinct()
            # Delete the reservations
            expired_reservations.delete()
            # Cancel any pending orders these reservations belonged to
            Order.objects.filter(
                id__in=expired_order_ids,
                payment_status='pending'
            ).update(
                status='cancelled',
                payment_status='failed',
                stock_reserved=False
            )
        
        # Calculate reserved stock from non-expired reservations only
        reserved = StockReservation.objects.filter(
            product=self,
            expires_at__gt=timezone.now()
        ).aggregate(total=Sum('quantity'))['total'] or 0
        return reserved

    def get_available_stock(self):
        return self.no_of_stock - self.get_reserved_stock()


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name='images', on_delete=models.CASCADE)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.product.name} - Image {self.order}"

    @property
    def image_url(self):
        if self.image:
            return self.image.url
        return None


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='cart_items')
    session_id = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'product']),
            models.Index(fields=['session_id', 'product']),
        ]

    def __str__(self):
        return f"Cart: {self.product.name} x {self.quantity}"


class WishlistItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='wishlist_items')
    session_id = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'product']),
            models.Index(fields=['session_id', 'product']),
        ]

    def __str__(self):
        return f"Wishlist: {self.product.name}"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('on_the_way', 'On the Way'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ]
    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('authorized', 'Authorized'),
        ('captured', 'Captured'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    order_number = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Denormalized Shipping Address (stored at order time, immutable after creation)
    shipping_full_name = models.CharField(max_length=100, default='')
    shipping_phone = models.CharField(max_length=20, default='')
    shipping_email = models.EmailField(default='')
    shipping_address_line_1 = models.CharField(max_length=255, help_text="Street address", default='')
    shipping_address_line_2 = models.CharField(max_length=255, blank=True, default='', help_text="Apartment, suite, etc.")
    shipping_city = models.CharField(max_length=100, default='')
    shipping_state = models.CharField(max_length=100, default='')
    shipping_zip_code = models.CharField(max_length=20, default='')
    shipping_country = models.CharField(max_length=100, default='India')
    
    # Order Financial Details
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping = models.DecimalField(max_digits=10, decimal_places=2)
    tax = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    stock_reserved = models.BooleanField(default=False)
    reservation_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_number} {self.user.email}"

    def calculate_totals(self):
        """Calculate order totals based on items with product-specific tax and shipping rates."""
        from decimal import Decimal
        
        subtotal = Decimal('0.00')
        shipping = Decimal('0.00')
        tax = Decimal('0.00')
        
        # Calculate subtotal, tax per item, and shipping
        items = self.items.all()
        
        for item in items:
            item_subtotal = item.product_price * item.quantity
            subtotal += item_subtotal
            
            # Add product-specific tax
            item_tax = (item_subtotal * item.product.tax_percentage) / 100
            tax += item_tax
            
            # Add product-specific shipping (only if product doesn't have free shipping)
            if not item.product.is_free_shipping_eligible:
                shipping += item.product.shipping_cost * item.quantity
        
        total = subtotal + shipping + tax
        
        return {
            'subtotal': round(subtotal, 2),
            'shipping': round(shipping, 2),
            'tax': round(tax, 2),
            'total': round(total, 2),
        }


class PaymentTransaction(models.Model):
    """Store payment transaction details for audit and record-keeping purposes"""
    PAYMENT_METHOD_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=False, related_name='payment_transactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_transactions')
    
    # Payment Amount Details
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, help_text="Subtotal before tax and shipping")
    shipping = models.DecimalField(max_digits=10, decimal_places=2, help_text="Shipping amount")
    tax = models.DecimalField(max_digits=10, decimal_places=2, help_text="Tax amount")
    total = models.DecimalField(max_digits=10, decimal_places=2, help_text="Total amount paid")
    
    # Razorpay Transaction Details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='razorpay')
    razorpay_order_id = models.CharField(max_length=100, db_index=True)
    razorpay_payment_id = models.CharField(max_length=100, db_index=True)
    razorpay_signature = models.CharField(max_length=255)
    
    # Transaction Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed', db_index=True)
    
    # Timestamps
    transaction_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['razorpay_order_id']),
            models.Index(fields=['razorpay_payment_id']),
            models.Index(fields=['user', 'transaction_date']),
        ]

    def __str__(self):
        return f"Payment {self.razorpay_payment_id} - Order {self.order.order_number} - ₹{self.total}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    product_name = models.CharField(max_length=255)
    product_price = models.DecimalField(max_digits=10, decimal_places=2)
    product_url = models.CharField(max_length=500, blank=True, default='', help_text="URL to product details page")
    quantity = models.IntegerField()

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def line_total(self):
        if self.product_price is None or self.quantity is None:
            return 0
        return self.product_price * self.quantity


class StockReservation(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='stock_reservations')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['product', 'expires_at']),
        ]

    def __str__(self):
        return f"Reserved: {self.product.name} x {self.quantity} for Order {self.order.order_number}"