from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_user_firebase_uid")]

    operations = [
        migrations.DeleteModel(name="AdminMfaChallenge"),
        migrations.DeleteModel(name="LoginOtpChallenge"),
    ]
