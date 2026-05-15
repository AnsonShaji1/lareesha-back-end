from django.contrib import admin
from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
import json

from django.utils.html import format_html
from .models import (
    CatalogSeedJob,
    Category,
    Product,
    ProductImage,
    CartItem,
    WishlistItem,
    Order,
    OrderItem,
    StockReservation,
    Address,
    PaymentTransaction,
    ShippingZone,
    ShippingZonePinPrefix,
    UserProfile,
)
from .seed_catalog import validate_products_json
from .seed_catalog_queue import enqueue_catalog_seed_job


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 3
    fields = ['image', 'image_preview', 'order']
    readonly_fields = ['image_preview']
    verbose_name = 'Product Image'
    verbose_name_plural = 'Product Images'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 100px; max-width: 100px;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'image_preview', 'created_at']
    search_fields = ['name', 'slug']
    readonly_fields = ['slug', 'image_preview', 'created_at', 'updated_at']
    fields = ['name', 'slug', 'image', 'image_preview', 'created_at', 'updated_at']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 80px; max-width: 80px;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'new_in', 'original_price', 'sale_price', 'no_of_stock', 'reserved_stock_display', 'available_stock_display', 'tax_percentage', 'shipping_display', 'created_at']
    list_filter = ['category', 'new_in', 'is_free_shipping_eligible', 'created_at']
    search_fields = ['name', 'description']
    inlines = [ProductImageInline]
    fieldsets = (
        ('Basic Information', {'fields': ('name', 'description', 'category', 'new_in')}),
        ('Pricing', {'fields': ('original_price', 'sale_price')}),
        ('Inventory', {
            'fields': ('no_of_stock', 'reserved_stock_display', 'available_stock_display'),
            'description': 'Reserved stock is dynamically calculated. Available stock = Total stock - Reserved stock'
        }),
        ('Tax & Shipping Settings', {
            'fields': ('tax_percentage', 'is_free_shipping_eligible', 'shipping_cost'),
            'description': 'Set is_free_shipping_eligible to True (default) for free shipping. Uncheck it and set shipping_cost to charge custom shipping.'
        }),
    )
    readonly_fields = ['reserved_stock_display', 'available_stock_display']

    def reserved_stock_display(self, obj):
        """Display total reserved stock across all active orders"""
        reserved = obj.get_reserved_stock()
        if reserved > 0:
            return format_html('<span style="color: orange; font-weight: bold;">{} reserved</span>', reserved)
        return format_html('<span style="color: green;">0 reserved</span>')
    reserved_stock_display.short_description = 'Reserved Stock'

    def available_stock_display(self, obj):
        """Display available stock (total - reserved)"""
        available = obj.get_available_stock()
        if available <= 5 and available > 0:
            return format_html('<span style="color: #ff9800; font-weight: bold;">{} available (LOW)</span>', available)
        elif available == 0:
            return format_html('<span style="color: red; font-weight: bold;">OUT OF STOCK</span>')
        else:
            return format_html('<span style="color: green;">{} available</span>', available)
    available_stock_display.short_description = 'Available Stock'

    def shipping_display(self, obj):
        if obj.is_free_shipping_eligible:
            return format_html('<span style="color: green; font-weight: bold;">FREE</span>')
        else:
            return format_html('<span>₹{}</span>', obj.shipping_cost)
    shipping_display.short_description = 'Shipping'


@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'image_preview', 'order']
    list_filter = ['product']
    search_fields = ['product__name']
    readonly_fields = ['image_preview']

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height: 200px;" />', obj.image.url)
        return "No image"
    image_preview.short_description = 'Preview'


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'session_id', 'quantity', 'created_at']
    list_filter = ['created_at']
    search_fields = ['session_id', 'product__name']


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'session_id', 'created_at']
    list_filter = ['created_at']
    search_fields = ['session_id', 'product__name']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ['product', 'product_name', 'product_price', 'product_url', 'quantity', 'line_total']
    readonly_fields = ['line_total', 'product_url']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user', 'status', 'payment_status', 'stock_reservation_status', 'total', 'created_at']
    list_filter = ['status', 'payment_status', 'stock_reserved', 'created_at']
    search_fields = ['order_number', 'user__email', 'shipping_full_name', 'shipping_city']
    readonly_fields = ['order_number', 'created_at', 'updated_at', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature', 'stock_reservation_display', 'shipping_full_name', 'shipping_phone', 'shipping_email', 'shipping_address_line_1', 'shipping_address_line_2', 'shipping_city', 'shipping_state', 'shipping_zip_code', 'shipping_country']
    inlines = [OrderItemInline]
    fieldsets = (
        ('Order Information', {'fields': ('order_number', 'user', 'status')}),
        ('Shipping Address (Immutable)', {'fields': ('shipping_full_name', 'shipping_phone', 'shipping_email', 'shipping_address_line_1', 'shipping_address_line_2', 'shipping_city', 'shipping_state', 'shipping_zip_code', 'shipping_country'), 'description': 'Address is saved at order time and cannot be changed.'}),
        ('Pricing', {'fields': ('subtotal', 'shipping', 'tax', 'total')}),
        ('Stock Reservation', {
            'fields': ('stock_reserved', 'reservation_expires_at', 'stock_reservation_display'),
            'description': 'Shows if stock is reserved for this order and when the reservation expires.'
        }),
        ('Payment Information', {'fields': ('payment_status', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature')}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )

    def stock_reservation_status(self, obj):
        """Show if stock is reserved and its status"""
        if obj.stock_reserved and obj.reservation_expires_at:
            from django.utils import timezone
            if obj.reservation_expires_at > timezone.now():
                time_left = obj.reservation_expires_at - timezone.now()
                minutes = int(round(time_left.total_seconds() / 60))
                return format_html(
                    '<span style="color: blue; font-weight: bold;">Reserved - {}m left</span>',
                    minutes
                )
            else:
                return format_html('<span style="color: orange;">Reserved - EXPIRED</span>')
        else:
            return format_html('<span style="color: gray;">Not reserved</span>')
    stock_reservation_status.short_description = 'Stock Status'

    def stock_reservation_display(self, obj):
        """Detailed display of stock reservation info"""
        if not obj.stock_reserved:
            return format_html('<span style="color: gray;">No stock reserved for this order</span>')
        
        reservations = obj.stock_reservations.all()
        if not reservations.exists():
            return format_html('<span style="color: orange;">Reserved flag ON but no reservations found (expired/released)</span>')
        
        details = '<div style="margin: 10px 0;">'
        for res in reservations:
            from django.utils import timezone
            is_expired = res.expires_at <= timezone.now()
            style = 'color: red; font-weight: bold;' if is_expired else 'color: green;'
            status = 'EXPIRED' if is_expired else 'Active'
            details += f'<div style="{style}">• {res.product.name} x{res.quantity} - {status}</div>'
        details += '</div>'
        return format_html(details)
    stock_reservation_display.short_description = 'Reservation Details'


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'product_name', 'quantity', 'product_price', 'product_url', 'line_total']
    list_filter = ['order__created_at']
    search_fields = ['order__order_number', 'product__name']


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'expiration_status', 'created_at']
    list_filter = ['expires_at', 'created_at']
    search_fields = ['order__order_number', 'product__name']
    readonly_fields = ['created_at', 'expires_at', 'expiration_status']
    fieldsets = (
        ('Reservation Details', {'fields': ('order', 'product', 'quantity')}),
        ('Expiration', {
            'fields': ('expires_at', 'expiration_status'),
            'description': 'Expired reservations are automatically cleaned up when the product is viewed or API is called.'
        }),
        ('Timestamps', {'fields': ('created_at',)}),
    )

    def expiration_status(self, obj):
        """Show if reservation is active or expired"""
        from django.utils import timezone
        if not obj.expires_at:
            return format_html('<span style="color: gray;">Not set</span>')
        if obj.expires_at > timezone.now():
            time_left = obj.expires_at - timezone.now()
            minutes = int(round(time_left.total_seconds() / 60))
            return format_html('<span style="color: green; font-weight: bold;">Active - {}m left</span>', minutes)
        else:
            return format_html('<span style="color: red; font-weight: bold;">EXPIRED - Auto-cleanup pending</span>')
    expiration_status.short_description = 'Expiration Status'


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'user', 'phone', 'city', 'is_default', 'created_at']
    list_filter = ['is_default', 'country', 'state', 'created_at']
    search_fields = ['full_name', 'email', 'phone', 'user__email', 'city']
    readonly_fields = ['created_at', 'updated_at']
    fieldsets = (
        ('User', {'fields': ('user',)}),
        ('Contact Information', {'fields': ('full_name', 'phone', 'email')}),
        ('Address', {'fields': ('address_line_1', 'address_line_2', 'city', 'state', 'zip_code', 'country')}),
        ('Default', {'fields': ('is_default',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'phone', 'gender', 'updated_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'phone']
    list_filter = ['gender', 'updated_at']
    readonly_fields = ['updated_at']


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_id_display', 'order_number', 'user_email', 'total_display', 'status_display', 'transaction_date']
    list_filter = ['status', 'payment_method', 'transaction_date']
    search_fields = ['razorpay_payment_id', 'razorpay_order_id', 'order__order_number', 'user__email']
    readonly_fields = ['order', 'user', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature', 'transaction_date', 'created_at', 'updated_at']
    date_hierarchy = 'transaction_date'
    
    fieldsets = (
        ('Order Information', {'fields': ('order', 'user')}),
        ('Payment Amount', {'fields': ('subtotal', 'shipping', 'tax', 'total')}),
        ('Payment Details', {'fields': ('payment_method', 'razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature')}),
        ('Status', {'fields': ('status',)}),
        ('Timestamps', {'fields': ('transaction_date', 'created_at', 'updated_at')}),
    )
    
    def transaction_id_display(self, obj):
        """Display a short version of the transaction ID"""
        return format_html(
            '<span style="font-family: monospace; font-size: 11px;">{}</span>',
            obj.razorpay_payment_id[:16] + '...' if len(obj.razorpay_payment_id) > 16 else obj.razorpay_payment_id
        )
    transaction_id_display.short_description = 'Transaction ID'
    
    def order_number(self, obj):
        """Display order number"""
        return obj.order.order_number
    order_number.short_description = 'Order Number'
    
    def user_email(self, obj):
        """Display user email"""
        return obj.user.email
    user_email.short_description = 'User Email'
    
    def total_display(self, obj):
        """Display total amount with currency"""
        return format_html(
            '<span style="color: green; font-weight: bold;">₹{}</span>',
            f"{obj.total:.2f}"
        )
    total_display.short_description = 'Total Amount'
    
    def status_display(self, obj):
        """Display status with color coding"""
        status_colors = {
            'completed': 'green',
            'failed': 'red',
            'refunded': 'orange',
            'pending': 'blue',
        }
        color = status_colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_display.short_description = 'Status'
    
    def has_add_permission(self, request):
        """Prevent manual addition of payments via admin"""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of payment records for audit purposes"""
        return False


class ShippingZonePinPrefixInline(admin.TabularInline):
    model = ShippingZonePinPrefix
    extra = 1
    fields = ['prefix']


@admin.register(ShippingZone)
class ShippingZoneAdmin(admin.ModelAdmin):
    change_list_template = 'admin/api/shippingzone/change_list.html'

    list_display = ['name', 'code', 'base_fee', 'free_shipping_min_order', 'priority', 'is_fallback', 'is_active']
    list_filter = ['is_active', 'is_fallback']
    search_fields = ['name', 'code']
    inlines = [ShippingZonePinPrefixInline]
    fieldsets = (
        (
            'Zone Rule',
            {
                'fields': (
                    'name',
                    'code',
                    'base_fee',
                    'free_shipping_min_order',
                    'priority',
                    'is_active',
                    'is_fallback',
                ),
                'description': (
                    'Shipping is resolved from destination pincode prefix and then this zone rule is applied. '
                    'Lower priority value wins when multiple rules are eligible. '
                    'Keep exactly one active fallback zone for unknown pincodes.'
                ),
            },
        ),
    )


@admin.register(ShippingZonePinPrefix)
class ShippingZonePinPrefixAdmin(admin.ModelAdmin):
    list_display = ['prefix', 'zone', 'zone_priority']
    list_filter = ['zone']
    search_fields = ['prefix', 'zone__name', 'zone__code']
    fieldsets = (
        (
            'Prefix Mapping',
            {
                'fields': ('prefix', 'zone'),
                'description': (
                    'Use numeric prefixes only (3 to 6 digits). '
                    'Examples: 682 (city-level), 68203 (area-level). '
                    'Checkout picks the longest matching prefix first.'
                ),
            },
        ),
    )

    def zone_priority(self, obj):
        return obj.zone.priority
    zone_priority.short_description = 'Zone Priority'


class SeedCatalogForm(forms.Form):
    json_file = forms.FileField(
        required=True,
        help_text="Upload a JSON file containing a list of products (same shape as seed_db.py). Processing runs in the background.",
    )
    reset_catalog = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Delete all categories/products/images before seeding.",
    )
    reset_orders = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Delete all orders / payment transactions before seeding.",
    )


def _require_seed_admin(request: HttpRequest) -> None:
    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied


@admin.register(CatalogSeedJob)
class CatalogSeedJobAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "status",
        "progress_display",
        "total_products",
        "created_products",
        "created_images",
        "env",
        "created_by",
        "created_at",
    ]
    list_filter = ["status", "env"]
    readonly_fields = [
        "status",
        "json_file",
        "reset_catalog",
        "reset_orders",
        "total_products",
        "processed_products",
        "created_products",
        "created_categories",
        "created_images",
        "error_message",
        "item_errors",
        "rq_job_id",
        "env",
        "is_local_images",
        "created_by",
        "started_at",
        "completed_at",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def progress_display(self, obj):
        return f"{obj.progress_percent}%"
    progress_display.short_description = "Progress"


def seed_catalog_admin_view(request: HttpRequest) -> HttpResponse:
    _require_seed_admin(request)

    if request.method == "POST":
        form = SeedCatalogForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["json_file"]
            json_bytes = uploaded.read()  # type: ignore[union-attr]
            if not json_bytes or not json_bytes.strip():
                messages.error(request, "Uploaded file is empty. Please upload a valid JSON file.")
            else:
                try:
                    _, total_products = validate_products_json(json_bytes)
                    if total_products == 0:
                        messages.error(request, "JSON contains no products with a name.")
                    else:
                        env = getattr(settings, "ENV", "local")
                        is_local_images = env == "local"
                        job = CatalogSeedJob.objects.create(
                            reset_catalog=bool(form.cleaned_data.get("reset_catalog")),
                            reset_orders=bool(form.cleaned_data.get("reset_orders")),
                            total_products=total_products,
                            env=env,
                            is_local_images=is_local_images,
                            created_by=request.user,
                        )
                        job.json_file.save(
                            uploaded.name or "products.json",
                            ContentFile(json_bytes),
                            save=True,
                        )
                        rq_id = enqueue_catalog_seed_job(job.pk)
                        if rq_id:
                            job.rq_job_id = rq_id
                            job.save(update_fields=["rq_job_id"])
                        return redirect("admin:seed-catalog-job", pk=job.pk)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    messages.error(request, f"Invalid JSON file: {e}")
                except ValueError as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f"Could not start seed job: {e}")

    else:
        form = SeedCatalogForm()

    recent_jobs = CatalogSeedJob.objects.select_related("created_by").order_by("-created_at")[:15]

    context = {
        **admin.site.each_context(request),
        "title": "Seed catalog from JSON",
        "form": form,
        "env": getattr(settings, "ENV", "local"),
        "is_local_images": getattr(settings, "ENV", "local") == "local",
        "local_image_root": str(getattr(settings, "SEED_LOCAL_IMAGE_ROOT", "")),
        "recent_jobs": recent_jobs,
    }
    return TemplateResponse(request, "admin/seed_catalog.html", context)


def seed_catalog_job_view(request: HttpRequest, pk: int) -> HttpResponse:
    _require_seed_admin(request)
    job = get_object_or_404(CatalogSeedJob, pk=pk)

    context = {
        **admin.site.each_context(request),
        "title": f"Seed job #{job.pk}",
        "job": job,
        "status_url": reverse("admin:seed-catalog-job-status", kwargs={"pk": job.pk}),
        "seed_catalog_url": reverse("admin:seed-catalog"),
    }
    return TemplateResponse(request, "admin/seed_catalog_job.html", context)


def seed_catalog_job_status_view(request: HttpRequest, pk: int) -> JsonResponse:
    _require_seed_admin(request)
    job = get_object_or_404(CatalogSeedJob, pk=pk)
    return JsonResponse(
        {
            "id": job.pk,
            "status": job.status,
            "progress_percent": job.progress_percent,
            "total_products": job.total_products,
            "processed_products": job.processed_products,
            "created_products": job.created_products,
            "created_categories": job.created_categories,
            "created_images": job.created_images,
            "error_message": job.error_message,
            "item_errors": job.item_errors,
            "is_finished": job.is_finished,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }
    )


_original_get_urls = admin.site.get_urls


def _get_urls_with_seed():
    urls = _original_get_urls()
    custom = [
        path("seed-catalog/", admin.site.admin_view(seed_catalog_admin_view), name="seed-catalog"),
        path(
            "seed-catalog/jobs/<int:pk>/",
            admin.site.admin_view(seed_catalog_job_view),
            name="seed-catalog-job",
        ),
        path(
            "seed-catalog/jobs/<int:pk>/status/",
            admin.site.admin_view(seed_catalog_job_status_view),
            name="seed-catalog-job-status",
        ),
    ]
    return custom + urls


admin.site.get_urls = _get_urls_with_seed