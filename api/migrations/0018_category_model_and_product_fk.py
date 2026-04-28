from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    Category = apps.get_model('api', 'Category')
    Product = apps.get_model('api', 'Product')

    # Create categories from existing Product.category (string) values.
    # Note: At this point in the migration graph, Product still has the legacy
    # CharField "category", and a nullable FK field "category_tmp".
    from django.utils.text import slugify

    def get_or_create_category(name: str):
        base_name = (name or '').strip() or 'Uncategorized'
        base_slug = slugify(base_name) or 'uncategorized'

        slug = base_slug
        i = 2
        while Category.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{i}"
            i += 1

        obj, _created = Category.objects.get_or_create(
            slug=slug,
            defaults={'name': base_name},
        )
        # If it existed with same slug but different name, keep existing name.
        return obj

    # Create categories deterministically based on distinct names
    distinct_names = (
        Product.objects.order_by()
        .values_list('category', flat=True)
        .distinct()
    )
    name_to_category_id = {}
    for name in distinct_names:
        cat = get_or_create_category(name)
        name_to_category_id[(name or '').strip() or 'Uncategorized'] = cat.id

    # Populate FK
    for product in Product.objects.all().only('id', 'category'):
        name = (product.category or '').strip() or 'Uncategorized'
        category_id = name_to_category_id.get(name)
        if category_id is None:
            category_id = get_or_create_category(name).id
            name_to_category_id[name] = category_id
        Product.objects.filter(id=product.id).update(category_tmp_id=category_id)


def backwards(apps, schema_editor):
    # Best-effort reverse: restore legacy string field from FK.
    # In reverse migration state at this point, the FK is named `category_tmp`
    # and the legacy CharField is named `category`.
    Product = apps.get_model('api', 'Product')
    for product in Product.objects.select_related('category_tmp').all():
        cat = getattr(product, 'category_tmp', None)
        if cat is not None:
            Product.objects.filter(id=product.id).update(category=cat.name)


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0017_product_new_in'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('slug', models.SlugField(db_index=True, max_length=100, unique=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='categories/')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'Categories',
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='product',
            name='category_tmp',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='api.category',
            ),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='product',
            name='category',
        ),
        migrations.RenameField(
            model_name='product',
            old_name='category_tmp',
            new_name='category',
        ),
        migrations.AlterField(
            model_name='product',
            name='category',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='products',
                to='api.category',
            ),
        ),
    ]

