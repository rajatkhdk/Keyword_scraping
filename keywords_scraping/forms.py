from django import forms
from .models import CarBrand

class SearchForm(forms.Form):
    brand = forms.ModelChoiceField(
        queryset=CarBrand.objects.all().order_by("name"),
        empty_label="Select Brand"
    )

class URLForm(forms.Form):
    brand = forms.ModelChoiceField(
        queryset=CarBrand.objects.all().order_by("name"),
        empty_label="Select Brand"
    )
    url = forms.URLField()
    mode = forms.ChoiceField(
        choices=[
            ("single", "Single Page"),
            ("deep", "All Pages"),
        ]
    )