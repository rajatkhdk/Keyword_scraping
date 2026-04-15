from django.db import models

class CarBrand(models.Model):
    keyword = models.CharField(max_length=200)

    website = models.URLField(null=True, blank=True)
    logo = models.URLField(null=True, blank=True)

    phones = models.JSONField(default=list, blank=True)
    emails = models.JSONField(default=list, blank=True)
    
    facebook = models.JSONField(default=list, blank=True)
    instagram = models.JSONField(default=list, blank=True)
    twitter = models.JSONField(default=list, blank=True)
    linkedin = models.JSONField(default=list, blank=True)
    youtube = models.JSONField(default=list, blank=True)
    tiktok = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.keyword
