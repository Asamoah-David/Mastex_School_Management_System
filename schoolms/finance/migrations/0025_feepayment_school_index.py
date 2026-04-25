"""
Create index on finance_feepayment.school_id after field migration is complete.
This separates index creation from field addition to avoid pending trigger events.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0024_feestructure_term_fk"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE INDEX finance_feepayment_school_id_idx ON finance_feepayment(school_id);",
            reverse_sql="DROP INDEX finance_feepayment_school_id_idx;",
        ),
    ]
