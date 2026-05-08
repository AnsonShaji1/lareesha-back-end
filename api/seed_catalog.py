import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse, urljoin
from urllib.request import urlopen

import boto3
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.text import slugify

from api.models import Category, Order, Product, ProductImage, PaymentTransaction


@dataclass(frozen=True)
class SeedResult:
    created_products: int
    created_categories: int
    created_images: int


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_remote_image_name(source_image_path: str) -> str:
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


def _get_r2_client():
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


def _build_remote_image_url(source_image_path: str) -> str:
    image_path = (source_image_path or "").strip()
    if image_path.startswith("http://") or image_path.startswith("https://"):
        return image_path

    bucket_name = (os.environ.get("AWS_STORAGE_BUCKET_NAME") or "").strip().strip("/")
    normalized_path = image_path.lstrip("/")
    if bucket_name and normalized_path.startswith(f"{bucket_name}/"):
        normalized_path = normalized_path[len(bucket_name) + 1:]

    public_base = (os.environ.get("R2_PUBLIC_URL") or getattr(settings, "MEDIA_URL", "") or "").strip()
    if not public_base.startswith("http://") and not public_base.startswith("https://"):
        return ""

    return urljoin(public_base.rstrip("/") + "/", normalized_path)


def load_remote_image(source_image_path: str, image_name: str) -> ContentFile | None:
    object_key = _normalize_remote_image_name(source_image_path)
    bucket_name = (os.environ.get("AWS_STORAGE_BUCKET_NAME") or "").strip()
    r2_client = _get_r2_client()

    if r2_client and bucket_name and object_key:
        try:
            obj = r2_client.get_object(Bucket=bucket_name, Key=object_key)
            return ContentFile(obj["Body"].read(), name=image_name)
        except Exception:
            pass

    remote_url = _build_remote_image_url(source_image_path)
    if not remote_url:
        return None

    try:
        with urlopen(remote_url) as response:
            return ContentFile(response.read(), name=image_name)
    except Exception:
        return None


def load_local_image(full_image_path: Path, image_name: str) -> ContentFile | None:
    try:
        with full_image_path.open("rb") as f:
            return ContentFile(f.read(), name=image_name)
    except Exception:
        return None


def _get_or_create_category(name: str) -> Category:
    base_name = (name or "").strip() or "Uncategorized"
    base_slug = slugify(base_name) or "uncategorized"

    existing = Category.objects.filter(name=base_name).first()
    if existing:
        return existing

    slug = base_slug
    i = 2
    while Category.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{i}"
        i += 1

    return Category.objects.create(name=base_name, slug=slug)


def _coerce_products_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "products" in payload:
        payload = payload["products"]
    if not isinstance(payload, list):
        raise ValueError("JSON must be a list of products (or an object with a 'products' list).")
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Product at index {idx} must be an object.")
        out.append(item)
    return out


@transaction.atomic
def seed_from_products_json(
    *,
    json_bytes: bytes,
    reset_catalog: bool,
    reset_orders: bool,
    is_local_images: bool,
    local_image_root: str | Path | None = None,
) -> SeedResult:
    payload = json.loads(json_bytes.decode("utf-8"))
    products = _coerce_products_payload(payload)

    if reset_orders:
        Order.objects.all().delete()
        PaymentTransaction.objects.all().delete()

    if reset_catalog:
        for image in list(ProductImage.objects.all()):
            image.delete()
        Product.objects.all().delete()
        Category.objects.all().delete()

    local_root = Path(local_image_root) if local_image_root else None

    created_products = 0
    created_images = 0
    category_names_before = set(Category.objects.values_list("name", flat=True))

    for product_data in products:
        name = (product_data.get("name") or "").strip()
        if not name:
            continue

        category_name = product_data.get("category") or product_data.get("category_name") or "Uncategorized"
        category = _get_or_create_category(str(category_name))

        product = Product.objects.create(
            name=name,
            description=str(product_data.get("description") or ""),
            original_price=product_data.get("original_price") or 0,
            sale_price=product_data.get("sale_price") or 0,
            tax_percentage=product_data.get("tax_percentage") or 0,
            category=category,
            new_in=bool(product_data.get("new_in", False)),
            no_of_stock=int(product_data.get("no_of_stock") or 0),
        )
        created_products += 1

        images: Iterable[str] = product_data.get("images") or []
        for order, source_image_path in enumerate(images):
            if not source_image_path:
                continue
            source_image_path = str(source_image_path)
            # Keep the same naming scheme as the legacy seed management command:
            # "<product_id>_<idx><extension>"
            extension = os.path.splitext(source_image_path)[1] or ".jpg"
            image_name = f"{product.id}_{order}{extension}"

            if is_local_images:
                if not local_root:
                    continue
                full_path = local_root / source_image_path.lstrip("/")
                content = load_local_image(full_path, image_name)
            else:
                content = load_remote_image(source_image_path, image_name)

            if not content:
                continue

            pi = ProductImage(product=product, order=order)
            pi.image.save(image_name, content, save=True)
            created_images += 1

    category_names_after = set(Category.objects.values_list("name", flat=True))
    created_categories = len(category_names_after - category_names_before)
    return SeedResult(
        created_products=created_products,
        created_categories=created_categories,
        created_images=created_images,
    )

