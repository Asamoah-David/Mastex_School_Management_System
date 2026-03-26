# Duplicate Models - Consolidation Notes

## Overview
The following models are duplicated across apps and should be consolidated in a future refactor.

---

## 1. Discipline Models

### Location A: `students/models.py`
```python
class StudentDiscipline(models.Model):
    """Track behavior and discipline records"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    incident_date = models.DateField()
    action_taken = models.TextField(blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
```

### Location B: `operations/models.py`
```python
class DisciplineIncident(models.Model):
    """Track student disciplinary incidents"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    incident_date = models.DateTimeField()
    incident_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    description = models.TextField()
    action_taken = models.TextField(blank=True)
    reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
```

### Recommendation
**Keep:** `DisciplineIncident` (operations/models.py)
- More complete fields (severity, status)
- Better organization in operations app
- **Action:** Deprecate `StudentDiscipline` in students app

---

## 2. Timetable Models

### Location A: `academics/models.py`
```python
class Timetable(models.Model):
    """Class timetable"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    day = models.CharField(max_length=20)
    period = models.PositiveIntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)
```

### Location B: `operations/models.py`
```python
class TimetableSlot(models.Model):
    """Timetable slots for classes"""
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    class_name = models.CharField(max_length=50)
    day = models.CharField(max_length=20, choices=DAYS)
    period_number = models.PositiveIntegerField()
    subject = models.ForeignKey('academics.Subject', on_delete=models.CASCADE)
    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
```

### Recommendation
**Keep:** `TimetableSlot` (operations/models.py)
- Has `is_active` field for managing timetable versions
- Uses `period_number` instead of `period` (clearer naming)
- Better structured for complex timetable management
- **Action:** Deprecate `Timetable` in academics app

---

## Consolidation Steps (When Ready)

1. **Backup database** before any migration
2. **Choose which model to keep** (recommendations above)
3. **Migrate data** from old model to new model
4. **Update all references** in views, templates, admin, URLs
5. **Remove old model** and create removal migration
6. **Test thoroughly** before deployment

---

## Impact Assessment

| Model Pair | Complexity | Risk | Effort |
|------------|------------|------|--------|
| Discipline | Medium | Medium | 2-4 hours |
| Timetable | High | High | 4-8 hours |

**Recommendation:** Only consolidate if you have existing data that needs to be preserved. Otherwise, just use one consistently going forward.
