from django import forms

class SearchForm(forms.Form):
    keyword = forms.CharField(
        label="Enter Keyword",
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "e.g. BMW"
        })
    )