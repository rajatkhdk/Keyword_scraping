from django.db import models

class CarBrand(models.Model):

    # slug = models.SlugField(unique=True)

    # keywords = models.JSONField(null=True, default=list, blank=True)

    # brand = models.CharField(max_length=50, unique=True)

    keyword = models.CharField(max_length=500)

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
        return self.keyword
