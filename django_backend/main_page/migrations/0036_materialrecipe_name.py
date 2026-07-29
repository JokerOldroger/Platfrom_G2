from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main_page', '0035_experimentdatapoint'),
    ]

    operations = [
        migrations.AddField(
            model_name='materialrecipe',
            name='name',
            field=models.CharField(default='Default Recipe', max_length=100),
        ),
    ]
