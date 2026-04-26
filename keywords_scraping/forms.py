from django import forms
from .models import CarBrand
from dal import autocomplete

class SearchForm(forms.Form):
    brand = forms.ModelChoiceField(
        queryset=CarBrand.objects.all().order_by("name"),
        widget=autocomplete.ModelSelect2(
            url='brand-autocomplete',
            attrs={
                'data-placeholder': 'Search brand...',
                # 'data-minimum-input-length': 1,
                'style': 'width: 100%;'
            }
        )
    )

class URLForm(forms.Form):
    brand = forms.ModelChoiceField(
        queryset=CarBrand.objects.all().order_by("name"),
        widget=autocomplete.ModelSelect2(
            url='brand-autocomplete',
            attrs={
                'data-placeholder': 'Search brand...',
                # 'data-minimum-input-length': 1,
                'style': 'width: 100%;'
            }
        )
    )
    url = forms.URLField()
    mode = forms.ChoiceField(
        choices=[
            ("single", "Single Page"),
            ("deep", "All Pages"),
        ]
    )