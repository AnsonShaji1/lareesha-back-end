from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from .models import Address, Category, Product, ProductImage, CartItem, WishlistItem, Order, OrderItem, PaymentTransaction


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'date_joined']
        read_only_fields = ['id', 'date_joined']


class AddressSerializer(serializers.ModelSerializer):
    """Serializer for user addresses"""
    class Meta:
        model = Address
        fields = [
            'id', 'full_name', 'phone', 'email', 'address_line_1', 
            'address_line_2', 'city', 'state', 'zip_code', 'country',
            'is_default', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class RegisterSerializer(serializers.ModelSerializer):
    password1 = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True, label='Confirm Password')

    class Meta:
        model = User
        fields = ['email', 'password1', 'password2', 'first_name', 'last_name']
        extra_kwargs = {'first_name': {'required': True}, 'email': {'required': True}}

    def validate(self, attrs):
        if attrs['password1'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def create(self, validated_data):
        validated_data.pop('password2')
        password = validated_data.pop('password1')
        user = User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=password,
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        return user


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ['id', 'image_url', 'order']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        url = obj.image.url
        if url.startswith('http://') or url.startswith('https://'):
            return url
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'image_url']

    def get_image_url(self, obj):
        if not obj.image:
            return None
        url = obj.image.url
        if url.startswith('http://') or url.startswith('https://'):
            return url
        request = self.context.get('request')
        if request is not None:
            return request.build_absolute_uri(url)
        return url


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    available_stock = serializers.SerializerMethodField()
    category = CategorySerializer(read_only=True)
    category_slug = serializers.SlugField(source='category.slug', read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'description', 'original_price', 'sale_price',
            'category', 'category_slug',
            'new_in', 'no_of_stock', 'available_stock',
            'images', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_available_stock(self, obj):
        """Returns stock available for purchase (actual - reserved)"""
        return obj.get_available_stock()

    def to_representation(self, instance):
        self.fields['images'].context.update(self.context)
        self.fields['category'].context.update(self.context)
        representation = super().to_representation(instance)
        representation['images'] = [img['image_url'] for img in representation['images'] if img.get('image_url')]
        if isinstance(representation.get('category'), dict) and 'image_url' in representation['category']:
            representation['category']['imageUrl'] = representation['category'].pop('image_url')
        representation['originalPrice'] = representation.pop('original_price')
        representation['salePrice'] = representation.pop('sale_price')
        representation['newIn'] = representation.pop('new_in')
        representation['noOfStock'] = representation.pop('no_of_stock')
        representation['availableStock'] = representation.pop('available_stock')
        return representation


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = CartItem
        fields = ['id', 'product', 'product_id', 'quantity', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']


class WishlistItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = WishlistItem
        fields = ['id', 'product', 'product_id', 'created_at']
        read_only_fields = ['created_at']


class OrderItemSerializer(serializers.ModelSerializer):
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'product_price', 'product_url', 'product_image', 'quantity', 'line_total']
        read_only_fields = ['line_total']
    
    def get_product_image(self, obj):
        """Get the first product image URL"""
        try:
            first_image = obj.product.images.first()
            if first_image and first_image.image:
                url = first_image.image.url
                if url.startswith('http://') or url.startswith('https://'):
                    return url
                request = self.context.get('request')
                if request is not None:
                    return request.build_absolute_uri(url)
                return url
        except:
            pass
        return None


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'order_number', 
            'shipping_full_name', 'shipping_phone', 'shipping_email',
            'shipping_address_line_1', 'shipping_address_line_2',
            'shipping_city', 'shipping_state', 'shipping_zip_code', 'shipping_country',
            'subtotal', 'shipping', 'tax', 'total', 'status', 'payment_status', 
            'razorpay_order_id', 'stock_reserved', 'reservation_expires_at', 
            'items', 'created_at', 'updated_at'
        ]
        read_only_fields = ['order_number', 'razorpay_order_id', 'reservation_expires_at', 'created_at', 'updated_at']
    
    def to_representation(self, instance):
        """Convert denormalized fields to match frontend expectations"""
        representation = super().to_representation(instance)
        
        # Map denormalized shipping fields to frontend format
        representation['first_name'] = instance.shipping_full_name.split()[0] if instance.shipping_full_name else ''
        representation['last_name'] = ' '.join(instance.shipping_full_name.split()[1:]) if len(instance.shipping_full_name.split()) > 1 else ''
        representation['phone'] = representation.pop('shipping_phone')
        representation['email'] = representation.pop('shipping_email')
        representation['address'] = representation.pop('shipping_address_line_1')
        representation['apartment'] = representation.pop('shipping_address_line_2')
        representation['city'] = representation.pop('shipping_city')
        representation['state'] = representation.pop('shipping_state')
        representation['zip_code'] = representation.pop('shipping_zip_code')
        representation['country'] = representation.pop('shipping_country')
        
        return representation


class CreateOrderSerializer(serializers.Serializer):
    shipping_address_id = serializers.IntegerField()


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Serializer for payment transaction audit records"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'order_number', 'user_email', 'subtotal', 'shipping', 'tax', 'total',
            'payment_method', 'razorpay_order_id', 'razorpay_payment_id', 
            'razorpay_signature', 'status', 'transaction_date', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'razorpay_signature', 'transaction_date', 'created_at', 'updated_at'
        ]