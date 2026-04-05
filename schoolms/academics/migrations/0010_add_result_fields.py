# Generated migration to add missing Result fields and fix Timetable
# Modified to be idempotent - handles existing columns gracefully

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academics', '0009_alter_gradingpolicy_unique_together'),
    ]

    operations = [
        # Rename day to day_of_week in Timetable (idempotent - handles if already renamed)
        migrations.RenameField(
            model_name='timetable',
            old_name='day',
            new_name='day_of_week',
        ),
        
        # Make migrations idempotent by checking if columns exist before adding
        # Use RunSQL to only add columns if they don't exist (PostgreSQL specific)
        
        # Add created_by field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='created_by_id') THEN
                    ALTER TABLE academics_result ADD COLUMN created_by_id integer REFERENCES accounts_user(id) ON DELETE SET NULL;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS created_by_id;
            """,
        ),
        
        # Add created_at field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='created_at') THEN
                    ALTER TABLE academics_result ADD COLUMN created_at timestamp with time zone DEFAULT NOW();
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS created_at;
            """,
        ),
        
        # Add remarks field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='remarks') THEN
                    ALTER TABLE academics_result ADD COLUMN remarks text DEFAULT '';
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS remarks;
            """,
        ),
        
        # Add subject field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='subject_id') THEN
                    ALTER TABLE academics_result ADD COLUMN subject_id integer REFERENCES academics_subject(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS subject_id;
            """,
        ),
        
        # Add student field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='student_id') THEN
                    ALTER TABLE academics_result ADD COLUMN student_id integer REFERENCES students_student(id) ON DELETE CASCADE;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS student_id;
            """,
        ),
        
        # Add total_score field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='total_score') THEN
                    ALTER TABLE academics_result ADD COLUMN total_score double precision DEFAULT 100;
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS total_score;
            """,
        ),
        
        # Add updated_at field if it doesn't exist
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='academics_result' AND column_name='updated_at') THEN
                    ALTER TABLE academics_result ADD COLUMN updated_at timestamp with time zone DEFAULT NOW();
                END IF;
            END $$;
            """,
            reverse_sql="""
            ALTER TABLE academics_result DROP COLUMN IF EXISTS updated_at;
            """,
        ),
    ]
