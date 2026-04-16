from django.shortcuts import render
from .forms import SearchForm, URLForm
from .models import CarBrand
from keywords_scraping.ddgs_search import get_urls
from keywords_scraping.extract_data_1 import extract_basic_info, fetch_soup, get_pages_to_scrape

def scrape_from_url(base_url, deep=True):
    try:
        homepage_soup = fetch_soup(base_url)

        if not homepage_soup:
            return None

        if deep:
            pages = get_pages_to_scrape(homepage_soup, base_url)
            pages = [base_url] + pages
        else:
            pages = [base_url]

        all_phones = []
        all_emails = []
        logo = None

        all_facebook = set()
        all_instagram = set()
        all_twitter = set()
        all_linkedin = set()
        all_youtube = set()
        all_tiktok = set()

        for page in pages:
            print(f"Scraping: {page}")

            try:
                data = extract_basic_info(page)

                if not data:
                    continue

                all_phones.extend(data.get("phones", []))
                all_emails.extend(data.get("emails", []))

                all_facebook.update(data.get("facebook", []))
                all_instagram.update(data.get("instagram", []))
                all_twitter.update(data.get("twitter", []))
                all_linkedin.update(data.get("linkedin", []))
                all_youtube.update(data.get("youtube", []))
                all_tiktok.update(data.get("tiktok", []))

                if not logo and data.get("logo"):
                    logo = data["logo"]

            except Exception as e:
                print(f"Page error: {e}")

        return {
            "website": base_url,
            "phones": list(set(all_phones)),
            "emails": list(set(all_emails)),
            "logo": logo,
            "facebook": list(all_facebook),
            "instagram": list(all_instagram),
            "twitter": list(all_twitter),
            "linkedin": list(all_linkedin),
            "youtube": list(all_youtube),
            "tiktok": list(all_tiktok),
        }

    except Exception as e:
        print(f"Site error: {e}")
        return None


def search_view(request):
    form = SearchForm()
    data = None

    if request.method == "POST":
        form = SearchForm(request.POST)

        if form.is_valid():
            keyword = form.cleaned_data["keyword"]

            results = get_urls(keyword) 
            print("Result: ", results)

            MAX_TRIES = 5

            final_data = None

            for i, r in enumerate(results[:MAX_TRIES]):

                base_url = r[1]

                candidate_data = scrape_from_url(base_url, deep=True)

                if not candidate_data:
                    continue

                #  STOP CONDITION
                if candidate_data["logo"] and candidate_data["phones"]:
                    print("Good result found, stopping early")
                    final_data = candidate_data
                    break

                # fallback: keep best partial result
                if not final_data:
                    final_data = candidate_data

            # Step 3: save to DB
            obj = CarBrand.objects.create(
                keyword=keyword,
                website=final_data.get("website"),
                phones=final_data.get("phones"),
                emails=final_data.get("emails"),
                logo=final_data.get("logo"),
                facebook=final_data.get("facebook"),
                instagram=final_data.get("instagram"),
                twitter=final_data.get("twitter"),
                linkedin=final_data.get("linkedin"),
                tiktok=final_data.get("tiktok"),
                youtube=final_data.get("youtube"),
            )

            data = obj

    return render(request, "admin/search.html", {
        "form": form,
        "data": data
    })
# results = get_urls(keyword)


def scrape_url_view(request):
    form = URLForm()
    data = None

    if request.method == "POST":
        form = URLForm(request.POST)

        if form.is_valid():
            url = form.cleaned_data["url"]
            mode = form.cleaned_data["mode"]

            deep = True if mode == "deep" else False

            result = scrape_from_url(url, deep=deep)

            if not result:
                result = {
                    "website": url,
                    "phones": [],
                    "emails": [],
                    "logo": None,
                }

            obj = CarBrand.objects.create(
                keyword="manual",
                website=result.get("website"),
                phones=result.get("phones"),
                emails=result.get("emails"),
                logo=result.get("logo"),
                facebook=result.get("facebook"),
                instagram=result.get("instagram"),
                twitter=result.get("twitter"),
                linkedin=result.get("linkedin"),
                tiktok=result.get("tiktok"),
                youtube=result.get("youtube"),
            )

            data = obj

    return render(request, "admin/url_scrape.html", {
        "form": form,
        "data": data
    })