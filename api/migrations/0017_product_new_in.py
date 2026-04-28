from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_alter_order_status_alter_paymenttransaction_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='new_in',
            field=models.BooleanField(
                default=False,
                help_text='Mark product to be shown in New In listing',
            ),
        ),
    ]
