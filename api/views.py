import logging
import hmac
import hashlib

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from .models import Category, Product, ProductImage, CartItem, WishlistItem, Order, OrderItem, StockReservation, Address, PaymentTransaction
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    CartItemSerializer,
    WishlistItemSerializer,
    OrderSerializer,
    CreateOrderSerializer,
    RegisterSerializer,
    UserSerializer,
    AddressSerializer
)
from .shipping import calculate_shipping_for_address, resolve_shipping_zone_by_pincode, calculate_shipping_for_zone

logger = logging.getLogger(__name__)

import random
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from google.auth.transport import requests
from google.oauth2 import id_token
import razorpay
import json
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
import os


def get_user_or_session(request):
    if request.user.is_authenticated:
        return {'user': request.user}
    else:
        if not request.session.session_key:
            request.session.create()
        return {'session_id': request.session.session_key}


class GoogleAuthView(APIView):
    """Handle Google OAuth authentication"""
    permission_classes = [AllowAny]

    def post(self, request):
        access_token = request.data.get('access_token')
        
        if not access_token:
            return Response(
                {'error': 'access_token is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Get the client ID from settings or environment
            client_id = settings.SOCIALACCOUNT_PROVIDERS.get('google', {}).get('APP', {}).get('client_id')
            
            if not client_id:
                return Response(
                    {'error': 'Google Client ID not configured on server. Please set GOOGLE_OAUTH_CLIENT_ID environment variable.'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            # Verify the Google ID token
            idinfo = id_token.verify_oauth2_token(
                access_token, 
                requests.Request(), 
                client_id
            )
            
            # Get user info from token
            email = idinfo.get('email')
            first_name = idinfo.get('given_name', '')
            last_name = idinfo.get('family_name', '')
            google_id = idinfo.get('sub')
            
            if not email:
                return Response(
                    {'error': 'Email not provided by Google'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get or create user
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    'username': email,
                    'first_name': first_name,
                    'last_name': last_name,
                }
            )
            
            # Update user info if created
            if created:
                user.first_name = first_name
                user.last_name = last_name
                user.save()
            
            # Get or create social account
            social_account, _ = SocialAccount.objects.get_or_create(
                user=user,
                provider='google',
                defaults={
                    'uid': google_id,
                    'extra_data': {
                        'email': email,
                        'name': f"{first_name} {last_name}",
                    }
                }
            )
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'date_joined': user.date_joined.isoformat(),
                },
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_200_OK)
            
        except ValueError as e:
            # Invalid token
            error_msg = str(e)
            return Response(
                {'error': f'Invalid token: {error_msg}. Please make sure GOOGLE_OAUTH_CLIENT_ID is set correctly.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Authentication failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class RegistrationView(APIView):
    """Handle user registration with email and generate JWT tokens"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        
        if serializer.is_valid():
            user = serializer.save()
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'date_joined': user.date_joined.isoformat(),
                },
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """Handle user login with email/password and return JWT tokens"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email or not password:
            return Response(
                {'error': 'Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {'error': 'Invalid email or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Check password
        if not user.check_password(password):
            return Response(
                {'error': 'Invalid email or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        return Response({
            'user': {
                'id': user.id,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'date_joined': user.date_joined.isoformat(),
            },
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_200_OK)


class ForgotPasswordView(APIView):
    """Generate and send password reset email"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        
        if not email:
            return Response(
                {'error': 'Email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Don't reveal if user exists for security
            return Response(
                {'message': 'If an account exists with this email, password reset instructions have been sent.'},
                status=status.HTTP_200_OK
            )
        
        # Generate reset token
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Create reset link (frontend URL)
        env = (os.getenv("ENV") or "local").strip().lower()
        if env == "local":
            reset_link = f"http://localhost:4200/reset-password/{uid}/{token}"
        else:
            reset_link = f"https://lareeshaluxe.com/reset-password/{uid}/{token}"
        print("reset_link", reset_link)
        # Send email
        try:
            subject = "Password Reset Request - Lareesha Luxe"
            message = f"""
                Hello {user.first_name or user.email},

                We received a request to reset your password. Click the link below to reset your password:

                {reset_link}

                This link will expire in 1 hour.

                If you didn't request this, you can ignore this email.

                Best regards,
                Lareesha Luxe Team
            """
            
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            
            return Response(
                {'message': 'If an account exists with this email, password reset instructions have been sent.'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {'error': f'Failed to send email: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ResetPasswordConfirmView(APIView):
    """Confirm password reset with token"""
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not all([uid, token, new_password]):
            return Response(
                {'error': 'Missing required fields: uid, token, new_password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Decode uid
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {'error': 'Invalid reset link'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if token is valid
        if not default_token_generator.check_token(user, token):
            return Response(
                {'error': 'Reset link has expired or is invalid'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate password
        from django.contrib.auth.password_validation import validate_password
        try:
            validate_password(new_password, user=user)
        except Exception as e:
            return Response(
                {'error': f'Password validation failed: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Set new password
        user.set_password(new_password)
        user.save()
        
        return Response(
            {'message': 'Password has been reset successfully'},
            status=status.HTTP_200_OK
        )


class AddressViewSet(viewsets.ModelViewSet):
    """ViewSet for managing user addresses"""
    serializer_class = AddressSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=False, methods=['get'])
    def validate_pincode(self, request):
        """Validate an Indian pincode and return supported post office metadata."""
        pincode = (request.query_params.get('pincode') or '').strip()

        if not pincode:
            return Response(
                {'error': 'pincode is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not pincode.isdigit() or len(pincode) != 6:
            return Response(
                {'error': 'pincode must be a 6-digit number'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with urlopen(f'https://api.postalpincode.in/pincode/{pincode}', timeout=8) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except (URLError, HTTPError, TimeoutError, json.JSONDecodeError):
            return Response(
                {'error': 'Unable to validate pincode right now. Please try again.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if not payload or payload[0].get('Status') != 'Success':
            return Response(
                {'valid': False, 'error': 'Invalid pincode'},
                status=status.HTTP_200_OK
            )

        post_offices = payload[0].get('PostOffice') or []
        normalized = []
        seen_cities = set()
        seen_states = set()

        for office in post_offices:
            city = (office.get('District') or '').strip()
            state = (office.get('State') or '').strip()
            branch = (office.get('Name') or '').strip()
            if city:
                seen_cities.add(city.lower())
            if state:
                seen_states.add(state.lower())
            normalized.append({
                'name': branch,
                'city': city,
                'state': state,
            })

        return Response(
            {
                'valid': True,
                'pincode': pincode,
                'cities': sorted({office['city'] for office in normalized if office['city']}),
                'states': sorted({office['state'] for office in normalized if office['state']}),
                'post_offices': normalized,
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'])
    def set_default(self, request):
        """Set an address as the default address"""
        address_id = request.data.get('address_id')
        try:
            address = Address.objects.get(id=address_id, user=request.user)
            # Clear other defaults
            Address.objects.filter(user=request.user, is_default=True).update(is_default=False)
            # Set this as default
            address.is_default = True
            address.save()
            return Response(AddressSerializer(address).data, status=status.HTTP_200_OK)
        except Address.DoesNotExist:
            return Response(
                {'error': 'Address not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def default(self, request):
        """Get the default address"""
        default_address = Address.objects.filter(user=request.user, is_default=True).first()
        if default_address:
            return Response(AddressSerializer(default_address).data, status=status.HTTP_200_OK)
        return Response({'error': 'No default address set'}, status=status.HTTP_404_NOT_FOUND)


def _absolute_media_url(request, file_field):
    if not file_field:
        return None
    url = file_field.url
    if url.startswith(('http://', 'https://')):
        return url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


def _category_display_image_url(category, request):
    if category.image:
        return _absolute_media_url(request, category.image)
    first_image = (
        ProductImage.objects.filter(product__category=category)
        .exclude(image='')
        .order_by('-product__created_at', 'order')
        .first()
    )
    if first_image and first_image.image:
        return _absolute_media_url(request, first_image.image)
    return None


def _product_has_image(product):
    return any(img.image for img in product.images.all())


def _recent_products_queryset(**filters):
    """Newest products first (homepage strips, category pages, new-in)."""
    return (
        Product.objects.filter(**filters)
        .select_related('category')
        .prefetch_related('images')
        .order_by('-created_at', '-id')
    )


def _serialize_homepage_products(queryset, limit, request):
    """Return (serialized products, total with images in queryset)."""
    serializer_context = {'request': request}
    selected = []
    total_with_images = 0
    for product in queryset:
        if not _product_has_image(product):
            continue
        total_with_images += 1
        if len(selected) < limit:
            selected.append(product)
    serialized = ProductSerializer(selected, many=True, context=serializer_context).data
    return serialized, total_with_images


class HomepageView(APIView):
    """Homepage payload: categories, new arrivals, and per-category product strips."""
    permission_classes = [AllowAny]
    SECTION_LIMIT = 6

    def get(self, request):
        include_new_arrivals = self._param_enabled(
            request, 'include_new_arrivals', default=True
        )
        include_category_sections = self._param_enabled(
            request, 'include_category_sections', default=True
        )
        section_limit = self._section_limit(request)

        categories = []
        for category in Category.objects.all().order_by('name'):
            categories.append({
                'id': category.id,
                'name': category.name,
                'slug': category.slug,
                'image_url': _category_display_image_url(category, request),
            })

        payload = {'categories': categories}

        if include_new_arrivals:
            new_arrivals_qs = _recent_products_queryset(new_in=True)
            new_arrivals, new_arrivals_count = _serialize_homepage_products(
                new_arrivals_qs, section_limit, request
            )
            payload['new_arrivals'] = new_arrivals
            payload['new_arrivals_count'] = new_arrivals_count

        if include_category_sections:
            category_sections = []
            for category in Category.objects.all().order_by('name'):
                category_qs = _recent_products_queryset(category=category)
                products, product_count = _serialize_homepage_products(
                    category_qs, section_limit, request
                )
                if not products:
                    continue
                category_sections.append({
                    'category': {
                        'id': category.id,
                        'name': category.name,
                        'slug': category.slug,
                        'image_url': _category_display_image_url(category, request),
                    },
                    'products': products,
                    'product_count': product_count,
                })
            payload['category_sections'] = category_sections

        return Response(payload)

    @staticmethod
    def _param_enabled(request, name, default=True):
        value = request.query_params.get(name)
        if value is None:
            return default
        return str(value).lower() in ['1', 'true', 'yes']

    def _section_limit(self, request):
        raw = request.query_params.get('section_limit')
        if raw is None:
            return self.SECTION_LIMIT
        try:
            limit = int(raw)
        except (TypeError, ValueError):
            return self.SECTION_LIMIT
        return max(1, min(limit, self.SECTION_LIMIT))


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    class ProductPagination(PageNumberPagination):
        page_size = 25
        page_size_query_param = 'page_size'
        max_page_size = 50

    pagination_class = ProductPagination

    def get_queryset(self):
        queryset = Product.objects.select_related('category').all()
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search.strip())
        new_in = self.request.query_params.get('new_in')
        if new_in is not None:
            queryset = queryset.filter(new_in=str(new_in).lower() in ['1', 'true', 'yes'])
        categories = self.request.query_params.getlist('category')
        if categories:
            queryset = queryset.filter(category__slug__in=categories)
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        if min_price:
            queryset = queryset.filter(sale_price__gte=min_price)
        if max_price:
            queryset = queryset.filter(sale_price__lte=max_price)
        price_sort = self.request.query_params.get('price_sort')
        if price_sort == 'low-to-high':
            queryset = queryset.order_by('sale_price', '-created_at', '-id')
        elif price_sort == 'high-to-low':
            queryset = queryset.order_by('-sale_price', '-created_at', '-id')
        else:
            queryset = queryset.order_by('-created_at', '-id')
        return queryset


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user_or_session = get_user_or_session(self.request)
        return CartItem.objects.filter(**user_or_session)

    def create(self, request, *args, **kwargs):
        user_or_session = get_user_or_session(request)
        product_id = request.data.get('product_id')
        quantity = request.data.get('quantity', 1)
        product = get_object_or_404(Product, id=product_id)
        # Check against AVAILABLE stock (not total), accounting for reservations
        available = product.get_available_stock()
        if available < quantity:
            return Response(
                {'error': 'Insufficient stock', 'available': available, 'requested': quantity},
                status=status.HTTP_400_BAD_REQUEST
            )
        cart_item, created = CartItem.objects.get_or_create(
            **user_or_session,
            product=product,
            defaults={'quantity': quantity}
        )
        if not created:
            # Recalculate available after getting cart item (other items might have been added)
            available = product.get_available_stock()
            new_quantity = min(cart_item.quantity + quantity, available)
            cart_item.quantity = new_quantity
            cart_item.save()
        serializer = self.get_serializer(cart_item)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        quantity = request.data.get('quantity', 1)
        # Check against AVAILABLE stock, not total
        available = instance.product.get_available_stock()
        if available < quantity:
            return Response(
                {'error': 'Insufficient stock', 'available': available, 'requested': quantity},
                status=status.HTTP_400_BAD_REQUEST
            )
        instance.quantity = quantity
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        user_or_session = get_user_or_session(request)
        CartItem.objects.filter(**user_or_session).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def total(self, request):
        user_or_session = get_user_or_session(request)
        cart_items = CartItem.objects.filter(**user_or_session)
        total = sum(
            (item.product.sale_price) * item.quantity
            for item in cart_items
        )
        return Response({'total': total})

    @action(detail=False, methods=['post'])
    def validate_stock(self, request):
        user_or_session = get_user_or_session(request)
        cart_items = CartItem.objects.filter(**user_or_session).select_related('product')
        if not cart_items.exists():
            return Response(
                {'valid': False, 'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        insufficient_stock = []
        for cart_item in cart_items:
            if cart_item.product.no_of_stock < cart_item.quantity:
                insufficient_stock.append({
                    'product_id': cart_item.product.id,
                    'product_name': cart_item.product.name,
                    'requested': cart_item.quantity,
                    'available': cart_item.product.no_of_stock
                })
        if insufficient_stock:
            return Response(
                {
                    'valid': False,
                    'error': 'Insufficient stock for some items',
                    'items': insufficient_stock
                },
                status=status.HTTP_200_OK
            )
        return Response({'valid': True}, status=status.HTTP_200_OK)


class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistItemSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user_or_session = get_user_or_session(self.request)
        return WishlistItem.objects.filter(**user_or_session)

    def create(self, request, *args, **kwargs):
        user_or_session = get_user_or_session(request)
        product_id = request.data.get('product_id')
        product = get_object_or_404(Product, id=product_id)
        wishlist_item, created = WishlistItem.objects.get_or_create(
            **user_or_session,
            product=product
        )
        serializer = self.get_serializer(wishlist_item)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(serializer.data, status=status_code)

    @action(detail=False, methods=['post'])
    def toggle(self, request):
        user_or_session = get_user_or_session(request)
        product_id = request.data.get('product_id')
        product = get_object_or_404(Product, id=product_id)
        wishlist_item = WishlistItem.objects.filter(
            **user_or_session,
            product=product
        ).first()
        if wishlist_item:
            wishlist_item.delete()
            return Response({'in_wishlist': False})
        else:
            WishlistItem.objects.create(**user_or_session, product=product)
            return Response({'in_wishlist': True}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'])
    def check(self, request):
        user_or_session = get_user_or_session(request)
        product_id = request.query_params.get('product_id')
        if not product_id:
            return Response(
                {'error': 'product_id required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        exists = WishlistItem.objects.filter(
            **user_or_session,
            product_id=product_id
        ).exists()
        return Response({'in_wishlist': exists})

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        user_or_session = get_user_or_session(request)
        WishlistItem.objects.filter(**user_or_session).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _format_order_owner_notification_body(order):
    lines = [
        'A customer completed payment — this order is now placed.',
        '',
        'Order',
        f'  Order number: {order.order_number}',
        f'  Order ID: {order.id}',
        f'  Placed at: {order.created_at}',
        f'  Order status: {order.status}',
        f'  Payment status: {order.payment_status}',
        f'  Razorpay order ID: {order.razorpay_order_id}',
        f'  Razorpay payment ID: {order.razorpay_payment_id or "-"}',
        '',
        'Customer account',
        f'  Email: {order.user.email}',
        f'  Name: {(order.user.get_full_name() or "-").strip() or "-"}',
        '',
        'Shipping address',
        f'  Name: {order.shipping_full_name}',
        f'  Phone: {order.shipping_phone}',
        f'  Email: {order.shipping_email}',
        f'  Address line 1: {order.shipping_address_line_1}',
        f'  Address line 2: {order.shipping_address_line_2 or "-"}',
        f'  City: {order.shipping_city}',
        f'  State: {order.shipping_state}',
        f'  PIN / ZIP: {order.shipping_zip_code}',
        f'  Country: {order.shipping_country}',
        '',
        'Line items',
    ]
    for item in order.items.order_by('id'):
        line_total = item.line_total
        lines.append(
            f'  - {item.product_name} × {item.quantity} @ ₹{item.product_price} = ₹{line_total}'
        )
    lines.extend([
        '',
        'Totals',
        f'  Subtotal: ₹{order.subtotal}',
        f'  Shipping: ₹{order.shipping}',
        f'  Tax: ₹{order.tax}',
        f'  Total (paid): ₹{order.total}',
    ])
    return '\n'.join(lines)


def _format_order_customer_confirmation_body(order):
    lines = [
        'Thank you for your order — your payment was successful.',
        '',
        f'Order number: {order.order_number}',
        f'Placed on: {order.created_at}',
        '',
        'Shipping to',
        f'  {order.shipping_full_name}',
        f'  {order.shipping_address_line_1}',
    ]
    if order.shipping_address_line_2:
        lines.append(f'  {order.shipping_address_line_2}')
    lines.extend([
        f'  {order.shipping_city}, {order.shipping_state} {order.shipping_zip_code}',
        f'  {order.shipping_country}',
        f'  Phone: {order.shipping_phone}',
        '',
        'Items',
    ])
    for item in order.items.order_by('id'):
        line_total = item.line_total
        lines.append(
            f'  {item.product_name} × {item.quantity} @ ₹{item.product_price} = ₹{line_total}'
        )
    lines.extend([
        '',
        'Summary',
        f'  Subtotal: ₹{order.subtotal}',
        f'  Shipping: ₹{order.shipping}',
        f'  Tax: ₹{order.tax}',
        f'  Total paid: ₹{order.total}',
        '',
        'We will send updates as your order progresses. For help, please use the contact options on our website.',
    ])
    return '\n'.join(lines)


def _order_email_context(order, **extra):
    ctx = {
        'order': order,
        'items': list(order.items.order_by('id')),
        'brand_name': settings.SITE_BRAND_NAME,
    }
    ctx.update(extra)
    return ctx


def _send_order_mail_multipart(subject, text_body, html_template_name, recipients, context):
    html_body = render_to_string(html_template_name, context)
    send_mail(
        subject,
        text_body,
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        fail_silently=False,
        html_message=html_body,
    )


def send_order_customer_confirmation(order):
    email = (order.shipping_email or '').strip()
    if not email:
        return
    subject = f'Order confirmed — {order.order_number}'
    body = _format_order_customer_confirmation_body(order)
    ctx = _order_email_context(order)
    try:
        _send_order_mail_multipart(
            subject,
            body,
            'emails/customer_order_confirmation.html',
            [email],
            ctx,
        )
    except Exception as exc:
        logger.exception(
            'Customer order confirmation email failed for %s (%s): %s',
            order.order_number,
            email,
            exc,
        )


def send_order_placed_owner_notification(order):
    recipients = settings.ORDER_OWNER_NOTIFICATION_EMAILS
    if not recipients:
        return
    subject = f'New paid order — {order.order_number}'
    body = _format_order_owner_notification_body(order)
    account_name = (order.user.get_full_name() or '').strip() or order.user.email
    ctx = _order_email_context(order, account_display_name=account_name)
    try:
        _send_order_mail_multipart(
            subject,
            body,
            'emails/owner_order_notification.html',
            recipients,
            ctx,
        )
    except Exception as exc:
        logger.exception(
            'Owner order notification email failed for %s: %s',
            order.order_number,
            exc,
        )


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Order.objects.filter(user=self.request.user).prefetch_related('items')
        
        # Filter by status
        status_param = self.request.query_params.get('status')
        if status_param:
            statuses = status_param.split(',')
            queryset = queryset.filter(status__in=statuses)
        
        # Filter by payment status
        payment_status_param = self.request.query_params.get('payment_status')
        if payment_status_param:
            payment_statuses = payment_status_param.split(',')
            queryset = queryset.filter(payment_status__in=payment_statuses)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            from datetime import datetime
            queryset = queryset.filter(created_at__gte=datetime.fromisoformat(start_date))
        if end_date:
            from datetime import datetime
            queryset = queryset.filter(created_at__lte=datetime.fromisoformat(end_date))
        
        # Search by order number or product name
        search_query = self.request.query_params.get('search')
        if search_query:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(order_number__icontains=search_query) |
                Q(items__product_name__icontains=search_query)
            ).distinct()
        
        return queryset.order_by('-created_at')

    @action(detail=False, methods=['post'])
    def calculate_checkout_totals(self, request):
        """Calculate totals for checkout preview without creating an order."""
        cart_items = CartItem.objects.filter(user=request.user).select_related('product')
        
        if not cart_items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        from decimal import Decimal
        subtotal = Decimal('0.00')
        tax = Decimal('0.00')
        shipping = Decimal('0.00')
        shipping_address = None
        shipping_address_id = request.data.get('shipping_address_id')

        if shipping_address_id is not None and shipping_address_id != '':
            try:
                aid = int(shipping_address_id)
                shipping_address = Address.objects.get(id=aid, user=request.user)
            except (ValueError, TypeError):
                return Response(
                    {'error': 'Invalid shipping_address_id'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Address.DoesNotExist:
                return Response(
                    {'error': 'Shipping address not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        cart_items_data = []
        
        for cart_item in cart_items:
            item_subtotal = (cart_item.product.sale_price) * cart_item.quantity
            subtotal += item_subtotal
            
            # Add product-specific tax
            item_tax = (item_subtotal * cart_item.product.tax_percentage) / 100
            tax += item_tax
            
            cart_items_data.append({
                'product_id': cart_item.product.id,
                'product_name': cart_item.product.name,
                'quantity': cart_item.quantity,
                'price': float(cart_item.product.sale_price),
                'tax_percentage': float(cart_item.product.tax_percentage),
            })

        shipping = calculate_shipping_for_address(shipping_address, subtotal)
        total = subtotal + shipping + tax

        shipping_zone_name = None
        if shipping_address:
            zone = resolve_shipping_zone_by_pincode(shipping_address.zip_code)
            shipping_zone_name = zone.name if zone else None

        return Response({
            'subtotal': float(round(subtotal, 2)),
            'shipping': float(round(shipping, 2)),
            'tax': float(round(tax, 2)),
            'total': float(round(total, 2)),
            'shipping_pending_address': shipping_address is None,
            'shipping_zone': shipping_zone_name,
            'items': cart_items_data,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def shipping_quote(self, request):
        """
        Debug helper to test zone resolution and fee from pincode + subtotal.
        Body: { "zip_code": "682020", "subtotal": 2400 }
        """
        zip_code = (request.data.get('zip_code') or '').strip()
        subtotal_input = request.data.get('subtotal', 0)
        from decimal import Decimal, InvalidOperation

        if not zip_code:
            return Response(
                {'error': 'zip_code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            subtotal = Decimal(str(subtotal_input))
            if subtotal < 0:
                return Response(
                    {'error': 'subtotal must be a non-negative number'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except (InvalidOperation, TypeError):
            return Response(
                {'error': 'subtotal must be a valid number'},
                status=status.HTTP_400_BAD_REQUEST
            )

        zone = resolve_shipping_zone_by_pincode(zip_code)
        shipping_fee = calculate_shipping_for_zone(zone, subtotal)

        return Response(
            {
                'zip_code': zip_code,
                'subtotal': float(round(subtotal, 2)),
                'shipping': float(round(shipping_fee, 2)),
                'zone': {
                    'name': zone.name if zone else None,
                    'code': zone.code if zone else None,
                    'base_fee': float(zone.base_fee) if zone else 0.0,
                    'free_shipping_min_order': (
                        float(zone.free_shipping_min_order)
                        if zone and zone.free_shipping_min_order is not None
                        else None
                    ),
                    'is_fallback': zone.is_fallback if zone else True,
                },
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def create_order(self, request):
        create_serializer = CreateOrderSerializer(data=request.data)
        if not create_serializer.is_valid():
            return Response(
                create_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        cart_items = CartItem.objects.filter(user=request.user).select_related('product')
        if not cart_items.exists():
            return Response(
                {'error': 'Cart is empty'},
                status=status.HTTP_400_BAD_REQUEST
            )
        insufficient_stock = []
        for cart_item in cart_items:
            available_stock = cart_item.product.get_available_stock()
            if available_stock < cart_item.quantity:
                insufficient_stock.append({
                    'product': cart_item.product.name,
                    'requested': cart_item.quantity,
                    'available': available_stock
                })
        if insufficient_stock:
            return Response(
                {
                    'error': 'Insufficient stock for some items',
                    'items': insufficient_stock
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the shipping address
        address_id = create_serializer.validated_data['shipping_address_id']
        try:
            shipping_address = Address.objects.get(id=address_id, user=request.user)
        except Address.DoesNotExist:
            return Response(
                {'error': 'Shipping address not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create order first
        import random
        order_number = f"LL{request.user.id}{random.randint(100000, 999999)}"
        reservation_expires_at = timezone.now() + timedelta(
            minutes=settings.STOCK_RESERVATION_MINUTES
        )
        
        # Create initial order with denormalized address fields (immutable after creation)
        order = Order.objects.create(
            user=request.user,
            order_number=order_number,
            # Denormalized address fields (captured at order time)
            shipping_full_name=shipping_address.full_name,
            shipping_phone=shipping_address.phone,
            shipping_email=shipping_address.email,
            shipping_address_line_1=shipping_address.address_line_1,
            shipping_address_line_2=shipping_address.address_line_2,
            shipping_city=shipping_address.city,
            shipping_state=shipping_address.state,
            shipping_zip_code=shipping_address.zip_code,
            shipping_country=shipping_address.country,
            subtotal=0,
            shipping=0,
            tax=0,
            total=0,
            status='pending',
            payment_status='pending',
            razorpay_order_id='',  # Will be set after Razorpay creates the order
            stock_reserved=True,
            reservation_expires_at=reservation_expires_at
        )
        
        # Add order items
        for cart_item in cart_items:
            product = cart_item.product
            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                product_price=product.sale_price,
                product_url=f'/products/{product.id}',
                quantity=cart_item.quantity
            )
        
        # Calculate totals using destination-aware shipping rules
        totals = order.calculate_totals(shipping_address=shipping_address)
        subtotal = totals['subtotal']
        shipping = totals['shipping']
        tax = totals['tax']
        total = totals['total']
        amount_in_paise = int(float(total) * 100)
        
        # Update order with calculated totals
        order.subtotal = subtotal
        order.shipping = shipping
        order.tax = tax
        order.total = total
        order.save()
        
        # Create Razorpay Order using Razorpay API
        try:
            client = razorpay.Client(
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
            )
            
            razorpay_order = client.order.create(
                data={
                    'amount': amount_in_paise,  # Amount in paise
                    'currency': 'INR',
                    'receipt': order_number,
                    'payment_capture': 1,  # Auto-capture payments
                }
            )
            
            # Update order with real Razorpay order ID
            order.razorpay_order_id = razorpay_order['id']
            order.save()
            
        except Exception as e:
            # Delete the order if Razorpay order creation fails
            order.delete()
            return Response(
                {'error': f'Failed to create payment order: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create stock reservations
        for cart_item in cart_items:
            product = cart_item.product
            StockReservation.objects.create(
                order=order,
                product=product,
                quantity=cart_item.quantity,
                expires_at=reservation_expires_at
            )
        
        # Clear cart
        cart_items.delete()
        serializer = OrderSerializer(order)
        response_data = serializer.data
        response_data['razorpay_key'] = settings.RAZORPAY_KEY_ID
        response_data['amount'] = amount_in_paise
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def verify_payment(self, request):
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')
        if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
            return Response(
                {'error': 'Missing payment verification details'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            order = Order.objects.get(
                razorpay_order_id=razorpay_order_id,
                user=request.user
            )
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # IDEMPOTENCY CHECK: If payment already captured, don't process again
        if order.payment_status == 'captured':
            serializer = OrderSerializer(order)
            return Response(
                {
                    'message': 'Payment already verified',
                    **serializer.data
                }, 
                status=status.HTTP_200_OK
            )
        
        # Verify signature
        generated_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode(),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
            hashlib.sha256
        ).hexdigest()
        if generated_signature != razorpay_signature:
            order.payment_status = 'failed'
            order.status = 'cancelled'
            order.save()
            self._release_stock_reservation(order)
            return Response(
                {'error': 'Payment verification failed'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Payment successful - update order and deduct stock
        order.razorpay_payment_id = razorpay_payment_id
        order.razorpay_signature = razorpay_signature
        order.payment_status = 'captured'
        order.status = 'on_the_way'
        order.save()
        
        # Create PaymentTransaction record for audit purposes
        PaymentTransaction.objects.create(
            order=order,
            user=order.user,
            subtotal=order.subtotal,
            shipping=order.shipping,
            tax=order.tax,
            total=order.total,
            payment_method='razorpay',
            razorpay_order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            razorpay_signature=razorpay_signature,
            status='completed'
        )
        
        # Deduct stock from products (only if stock_reserved is True)
        if order.stock_reserved:
            for reservation in order.stock_reservations.all():
                product = reservation.product
                product.no_of_stock -= reservation.quantity
                product.save()
            order.stock_reservations.all().delete()
            order.stock_reserved = False
            order.save()
        
        # Notify store owners (non-blocking — failures are logged only)
        send_order_placed_owner_notification(order)
        send_order_customer_confirmation(order)
        
        serializer = OrderSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def payment_failed(self, request):
        razorpay_order_id = request.data.get('razorpay_order_id')
        if not razorpay_order_id:
            return Response(
                {'error': 'Missing order ID'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            order = Order.objects.get(
                razorpay_order_id=razorpay_order_id,
                user=request.user
            )
        except Order.DoesNotExist:
            return Response(
                {'error': 'Order not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # IDEMPOTENCY: If already processed, return current status
        if order.payment_status in ['failed', 'captured']:
            return Response(
                {
                    'message': f'Payment already {order.payment_status}',
                    'status': order.status,
                    'payment_status': order.payment_status
                },
                status=status.HTTP_200_OK
            )
        
        # Mark as failed and release stock reservations
        order.payment_status = 'failed'
        order.status = 'cancelled'
        order.save()
        self._release_stock_reservation(order)
        
        return Response(
            {'message': 'Order cancelled, stock released'},
            status=status.HTTP_200_OK
        )

    def _release_stock_reservation(self, order):
        order.stock_reservations.all().delete()
        order.stock_reserved = False
        order.save()
