from __future__ import annotations

from decimal import Decimal

from django import forms

from .models import FeeStructure


class FeeStructureForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "name": "e.g. Tuition, Development Levy",
            "class_name": "e.g. Form 1A (leave empty for all)",
            "term": "e.g. Term 1 2026",
        }
        for field_name, field in self.fields.items():
            existing_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"form-control {existing_class}".strip()
            if field_name in placeholders:
                field.widget.attrs.setdefault("placeholder", placeholders[field_name])
            if isinstance(field, forms.DecimalField):
                field.widget.attrs.setdefault("step", "0.01")
                field.widget.attrs.setdefault("min", "0")
        if not getattr(self.instance, "pk", None):
            self.fields.get("is_active").initial = True

    class Meta:
        model = FeeStructure
        fields = ["name", "amount", "class_name", "term", "is_active"]

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            raise forms.ValidationError("Amount is required.")
        if amount < Decimal("0"):
            raise forms.ValidationError("Amount must be zero or greater.")
        return amount.quantize(Decimal("0.01"))
