import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('kiosks', '0007_screencontentscreenshot_screenruntimestatus'),
    ]

    operations = [
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=64, validators=[django.core.validators.RegexValidator(message='Use lowercase letters, numbers, and underscores.', regex='^[a-z][a-z0-9_]{1,63}$')], verbose_name='event code')),
                ('level', models.CharField(choices=[('DEBUG', 'debug'), ('INFO', 'info'), ('WARNING', 'warning'), ('ERROR', 'error'), ('CRITICAL', 'critical')], max_length=16, verbose_name='level')),
                ('message', models.CharField(max_length=500, verbose_name='message')),
                ('url', models.URLField(blank=True, max_length=2048, verbose_name='URL')),
                ('occurred_at', models.DateTimeField(verbose_name='occurred at')),
                ('received_at', models.DateTimeField(auto_now_add=True, verbose_name='received at')),
                ('fingerprint', models.CharField(blank=True, max_length=128, verbose_name='fingerprint')),
                ('details', models.JSONField(blank=True, default=dict, verbose_name='details')),
                ('content', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='kiosks.content', verbose_name='content')),
                ('screen', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='kiosks.screen', verbose_name='screen')),
            ],
            options={
                'verbose_name': 'event',
                'verbose_name_plural': 'events',
                'ordering': ['-received_at', '-pk'],
                'indexes': [models.Index(fields=['screen', '-received_at'], name='kiosks_event_screen_received'), models.Index(fields=['screen', 'code', '-received_at'], name='kiosks_event_code_received'), models.Index(fields=['received_at'], name='kiosks_event_received')],
            },
        ),
    ]
