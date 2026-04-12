"""Detect teacher / room overlaps when saving timetable slots."""
from __future__ import annotations

from datetime import datetime, timedelta

def _combine(day: str, t) -> datetime | None:
    if not t:
        return None
    # Use a fixed epoch weekday map for ordering comparisons only
    base = datetime(2000, 1, 3)  # Monday
    day_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
    }
    off = day_map.get(day)
    if off is None:
        return None
    d = base + timedelta(days=off)
    return datetime.combine(d.date(), t)


def collect_timetable_slot_conflicts(
    school,
    *,
    day: str,
    start_time,
    end_time,
    teacher_id=None,
    room: str = "",
    exclude_slot_id=None,
) -> list[str]:
    """
    Return human-readable conflict messages for the proposed slot.
    """
    from operations.models import TimetableSlot

    errors: list[str] = []
    if not school or not day or not start_time or not end_time:
        return errors
    if end_time <= start_time:
        errors.append("End time must be after start time.")
        return errors

    new_start = _combine(day, start_time)
    new_end = _combine(day, end_time)
    if not new_start or not new_end:
        return errors

    qs = TimetableSlot.objects.filter(school=school, day=day, is_active=True)
    if exclude_slot_id:
        qs = qs.exclude(pk=exclude_slot_id)

    # Time overlap on same day: (start1 < end2) and (start2 < end1)
    def overlaps(o1, o2, o3, o4):
        return o1 < o4 and o3 < o2

    if teacher_id:
        for slot in qs.filter(teacher_id=teacher_id).select_related("teacher"):
            o1 = _combine(slot.day, slot.start_time)
            o2 = _combine(slot.day, slot.end_time)
            if o1 and o2 and overlaps(new_start, new_end, o1, o2):
                errors.append(
                    f"This teacher is already scheduled ({slot.class_name} · "
                    f"{slot.subject.name} · {slot.start_time}–{slot.end_time})."
                )
                break

    room = (room or "").strip()
    if room:
        for slot in qs.filter(room=room).select_related("subject"):
            o1 = _combine(slot.day, slot.start_time)
            o2 = _combine(slot.day, slot.end_time)
            if o1 and o2 and overlaps(new_start, new_end, o1, o2):
                errors.append(
                    f"Room {room} is already used ({slot.class_name} · "
                    f"{slot.subject.name} · {slot.start_time}–{slot.end_time})."
                )
                break

    return errors
