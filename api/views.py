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
from .models import Category, Product, CartItem, WishlistItem, Order, OrderItem, StockReservation, Address, PaymentTransaction
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
import hmac
import hashlib
import random
from datetime import timedelta
from rest_framework_simplejwt.tokens import RefreshToken
from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import User
from google.auth.transport import requests
from google.oauth2 import id_token
import razorpay


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
        reset_link = f"http://localhost:4200/reset-password/{uid}/{token}"
        
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
            queryset = queryset.order_by('sale_price')
        elif price_sort == 'high-to-low':
            queryset = queryset.order_by('-sale_price')
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
        
        # Create a temporary order to calculate totals
        from decimal import Decimal
        subtotal = Decimal('0.00')
        shipping = Decimal('0.00')
        tax = Decimal('0.00')
        
        cart_items_data = []
        
        for cart_item in cart_items:
            item_subtotal = (cart_item.product.sale_price) * cart_item.quantity
            subtotal += item_subtotal
            
            # Add product-specific tax
            item_tax = (item_subtotal * cart_item.product.tax_percentage) / 100
            tax += item_tax
            
            # Add product-specific shipping (only if product doesn't have free shipping)
            if not cart_item.product.is_free_shipping_eligible:
                shipping += cart_item.product.shipping_cost * cart_item.quantity
            
            cart_items_data.append({
                'product_id': cart_item.product.id,
                'product_name': cart_item.product.name,
                'quantity': cart_item.quantity,
                'price': float(cart_item.product.sale_price),
                'tax_percentage': float(cart_item.product.tax_percentage),
                'shipping_cost': float(cart_item.product.shipping_cost) if not cart_item.product.is_free_shipping_eligible else 0,
                'is_free_shipping_eligible': cart_item.product.is_free_shipping_eligible,
            })
        
        total = subtotal + shipping + tax
        
        return Response({
            'subtotal': float(round(subtotal, 2)),
            'shipping': float(round(shipping, 2)),
            'tax': float(round(tax, 2)),
            'total': float(round(total, 2)),
            'items': cart_items_data,
        }, status=status.HTTP_200_OK)

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
        
        # Calculate totals based on product-specific tax and shipping
        totals = order.calculate_totals()
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
