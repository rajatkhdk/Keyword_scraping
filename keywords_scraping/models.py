from django.db import models
from django.utils.text import slugify

class CarBrand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)

    logo = models.URLField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1

            # ensure uniqueness
            while CarBrand.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            self.slug = slug

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class BrandDetails(models.Model):

    # slug = models.SlugField(unique=True)

    # keywords = models.JSONField(null=True, default=list, blank=True)

    # brand = models.CharField(max_length=50, unique=True)

    brand = models.ForeignKey(CarBrand, on_delete=models.CASCADE)

    website = models.URLField(null=True, blank=True)
    logo = models.URLField(null=True, blank=True)

    phones = models.JSONField(default=list, blank=True)
    emails = models.JSONField(default=list, blank=True)
    
    facebook = models.JSONField(null=True, default=list, blank=True)
    instagram = models.JSONField(null=True, default=list, blank=True)
    twitter = models.JSONField(null=True, default=list, blank=True)
    linkedin = models.JSONField(null=True, default=list, blank=True)
    youtube = models.JSONField(null=True, default=list, blank=True)
    tiktok = models.JSONField(null=True, default=list, blank=True)

    dealers = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.brand.name
