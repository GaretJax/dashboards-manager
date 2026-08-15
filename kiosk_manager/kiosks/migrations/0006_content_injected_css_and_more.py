import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kiosks', '0005_content_screencontent_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='content',
            name='injected_css',
            field=models.TextField(blank=True, default='', help_text='Optional CSS applied on every document load.', max_length=65536, validators=[django.core.validators.MaxLengthValidator(65536)], verbose_name='injected CSS'),
        ),
        migrations.AddField(
            model_name='content',
            name='injected_javascript_after',
            field=models.TextField(blank=True, default='', help_text='Optional JavaScript executed after document load.', max_length=65536, validators=[django.core.validators.MaxLengthValidator(65536)], verbose_name='JavaScript after document load'),
        ),
        migrations.AddField(
            model_name='content',
            name='injected_javascript_before',
            field=models.TextField(blank=True, default='', help_text='Optional JavaScript executed before page scripts.', max_length=65536, validators=[django.core.validators.MaxLengthValidator(65536)], verbose_name='JavaScript before page scripts'),
        ),
    ]
