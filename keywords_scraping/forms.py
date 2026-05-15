from django import forms
from .models import CarBrand
from dal import autocomplete

class CarBrandForm(forms.ModelForm):

    class Meta:
        model = CarBrand
        fields = ["name", "slug", "logo"]

        widgets = {

            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Enter brand name"
            }),

            "slug": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Optional (auto-generated if empty)"
            }),

            "logo": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "Paste logo image URL"
            }),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if name:
            return name.strip()
        return name

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