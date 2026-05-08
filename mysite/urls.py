"""
URL configuration for mysite project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from keywords_scraping import views
from keywords_scraping.views import BrandAutocomplete

urlpatterns = [
    path('admin/', admin.site.urls),
    path('keywordsearch/', views.search_view, name='search'),
    path('scrape-url/', views.scrape_url_view, name='scrape_url'),
    path('index/', views.index, name='index'),
    path('index/data', views.data, name='data'),
    path('table/', views.table, name='table'),

    path('carbrands/', views.carbrands, name='car_brand'),
    path('carbrands/add/', views.add_carbrand, name='add_car_brand'),
    path('carbrands/<int:id>/edit/', views.edit_carbrand, name='edit_car_brand'),
    path('carbrands/<int:id>/delete/', views.delete_carbrand, name='delete_car_brand'),

    path('brand-autocomplete/', BrandAutocomplete.as_view(), name='brand-autocomplete')
]
