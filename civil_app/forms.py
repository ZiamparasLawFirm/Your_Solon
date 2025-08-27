"""
Forms for Civil search.

We render a simple form with four inputs:
- Client name (text)
- Court (select populated from Court model)
- ΓΑΚ Αριθμός (text)
- Έτος (integer)
"""

from django import forms
from .models import Court

class CivilSearchForm(forms.Form):
    client_name = forms.CharField(label="Όνομα Πελάτη", max_length=255)
    court = forms.ModelChoiceField(
        label="Κατάστημα",
        queryset=Court.objects.filter(is_active=True).order_by("name"),
        empty_label=None,
    )
    gak_number = forms.CharField(label="ΓΑΚ Αριθμός", max_length=20)
    gak_year = forms.IntegerField(label="Έτος", min_value=1980, max_value=2100)
