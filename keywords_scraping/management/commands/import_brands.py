import requests
from django.core.management.base import BaseCommand
from keywords_scraping.models import CarBrand


class Command(BaseCommand):
    help = "Import car brands from RoadSewa API"

    def handle(self, *args, **kwargs):
        url = "https://api.roadsewa.com/api/brand/all/public?statusIn=ACTIVE"

        try:
            res = requests.get(url, timeout=15)
            data = res.json().get("data", [])

            created = 0
            updated = 0

            for item in data:
                name = item.get("brandName", "").strip()

                if not name:
                    continue

                logo = None
                file_data = item.get("file")

                if file_data:
                    logo = file_data.get("path")

                obj, is_created = CarBrand.objects.update_or_create(
                    name=name,
                    defaults={
                        "logo": logo
                    }
                )

                if is_created:
                    created += 1
                else:
                    updated += 1

            self.stdout.write(self.style.SUCCESS(
                f"Done ✅ Created: {created}, Updated: {updated}"
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}"))