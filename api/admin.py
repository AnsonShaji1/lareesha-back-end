from django.contrib import admin
from django.utils.html import format_html
from .models import Category, Product, ProductImage, CartItem, WishlistItem, Order, OrderItem, StockReservation, Address, PaymentTransaction


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