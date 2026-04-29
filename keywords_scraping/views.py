from django.shortcuts import render
from .forms import SearchForm, URLForm
from .models import CarBrand, BrandDetails
from keywords_scraping.ddgs_search import get_urls
from keywords_scraping.extract_data_1 import extract_basic_info, fetch_soup, get_pages_to_scrape
from dealer_scraper_1 import scrape_dealers
import asyncio
import re
from dal import autocomplete

class BrandAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        qs = CarBrand.objects.all().order_by("name")

        if self.q:
            qs = qs.filter(name__icontains=self.q)

        return qs

def scrape_dealers_sync(url):
    try:
        return asyncio.run(scrape_dealers(url))
    except RuntimeError:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(scrape_dealers(url))

def is_dealer_page(url, html):
    url = url.lower()

    if (any(k in url for k in ["dealer", "showroom", "location", "branch", "network"])
    and "become" not in url):
        print("dealer")
        return True

    if html:
        text = html.lower()
        if "dealer" in text or "showroom" in text:
            return True

    return False

def scrape_from_url(base_url, deep=True):
    """
    Takes a url, crawl through different pages and extract info.
    1. fetch soup
    2. if deep -> get pages (multiple)
        else single page (url)
    3. Loop through pages
        i. data -> extract_basic_info(page)
    """
    try:
        homepage_soup = fetch_soup(base_url)

        if not homepage_soup:
            return None

        # -----------------------------
        # STEP 1: Decide pages to crawl
        # -----------------------------
        if deep:
            pages = get_pages_to_scrape(homepage_soup, base_url)
            pages = [base_url] + pages
        else:
            pages = [base_url]

        # remove duplicate pages
        pages = list(dict.fromkeys(pages))

        # -----------------------------
        # STEP 2: Global accumulators
        # -----------------------------
        all_phones = []
        all_emails = []
        # logo = None

        all_facebook = set()
        all_instagram = set()
        all_twitter = set()
        all_linkedin = set()
        all_youtube = set()
        all_tiktok = set()

        all_dealers = []

        # -----------------------------
        # STEP 3: Crawl normal pages
        # -----------------------------
        for page in pages:
            print(f"Scraping: {page}")

            try:

                # -----------------------------
                # STEP 4: Dealer extraction
                # -----------------------------
                if is_dealer_page(page, None):
                    print(f"Running dealer scraper on: {page}")

                    try:
                        dealers = scrape_dealers_sync(page)

                        if dealers:
                            all_dealers.extend(dealers)

                    except Exception as dealer_error:
                        print(f"Dealer scrape error: {dealer_error}")

                else:
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

                    # if not logo and data.get("logo"):
                    #     logo = data["logo"]

                

            except Exception as e:
                print(f"Page error: {e}")

        # -----------------------------
        # STEP 5: Final dealer dedupe
        # -----------------------------
        unique_dealers = []
        seen = set()

        for dealer in all_dealers:
            phone_key = tuple(sorted(
                re.sub(r"\D", "", p)
                for p in dealer.get("phone", [])
            ))

            name_key = dealer.get("name", "").strip().lower()

            key = phone_key if phone_key else (name_key,)

            if key in seen:
                continue

            seen.add(key)
            unique_dealers.append(dealer)

        print(f"All phones : {all_phones} \n Dealers : {unique_dealers}")

        return {
            "website": base_url,
            "phones": list(set(all_phones)),
            "emails": list(set(all_emails)),
            # "logo": logo,
            "facebook": list(all_facebook),
            "instagram": list(all_instagram),
            "twitter": list(all_twitter),
            "linkedin": list(all_linkedin),
            "youtube": list(all_youtube),
            "tiktok": list(all_tiktok),
            "dealers": unique_dealers,
        }

    except Exception as e:
        print(f"Site error: {e}")
        return None


def search_view(request):
    """
    View for keyword search page
    """
    form = SearchForm()
    data = None
    result = None

    if request.method == "POST":
        form = SearchForm(request.POST)

        if form.is_valid():
            brand_obj = form.cleaned_data["brand"]
            brand_name = brand_obj.name

            # =========================
            # STEP 1: SHOW EXISTING DATA
            # =========================
            
            existing = BrandDetails.objects.filter(brand=brand_obj).first()

            if (existing and "scrape_new" not in request.POST and "confirm_save" not in request.POST):

                return render(request, "admin/search.html", {
                    "form": form,
                    "data": existing,
                    "show_scrape_button": True,
                    "existing": True
                })            

            # =========================
            # STEP 2: CONFIRM SAVE
            # =========================
            if "confirm_save" in request.POST:

                result = request.session.get("scraped_data")

                if not result:
                    return render(request, "admin/search.html", {
                        "form": form,
                        "data": None,
                        "error": "No scraped data found. Please scrape again."
                    })

                obj, created = BrandDetails.objects.update_or_create(
                    brand=brand_obj,
                    defaults={
                        "website": result.get("website"),
                        "phones": result.get("phones"),
                        "emails": result.get("emails"),
                        "facebook": result.get("facebook"),
                        "instagram": result.get("instagram"),
                        "twitter": result.get("twitter"),
                        "linkedin": result.get("linkedin"),
                        "tiktok": result.get("tiktok"),
                        "youtube": result.get("youtube"),
                        "dealers": result.get("dealers"),
                    }
                )

                # clear session after save
                request.session.pop("scraped_data", None)
                request.session.pop("brand_id", None)

                return render(request, "admin/search.html", {
                    "form": form,
                    "data": obj,
                    "existing": False,
                    "pending_save": False,
                    "show_scrape_button": False
                })
            
            # -----------------------------
            # STEP 3: Scrape Data
            # -----------------------------
            if "scrape_new" in request.POST or not existing:

                # -----------------------------
                # SEARCH URLS USING BRAND NAME
                # -----------------------------
                results = get_urls(brand_name) 
                # print("Result: ", results)

                MAX_TRIES = 5
                final_data = None

                for r in results[:MAX_TRIES]:

                    base_url = r[1]

                    candidate_data = scrape_from_url(base_url, deep=True)

                    if not candidate_data:
                        continue

                    #  STOP CONDITION
                    if candidate_data["phones"] or candidate_data["dealers"]:
                        # print("Good result found, stopping early")
                        final_data = candidate_data
                        break

                    # fallback: keep best partial result
                    if not final_data:
                        final_data = candidate_data

                if not final_data:
                    return render(request, "admin/search.html", {
                        "form": form,
                        "data": None,
                        "error": "No data could be scraped."
                    })

                # store temporarily in session
                request.session["scraped_data"] = final_data
                request.session["brand_id"] = brand_obj.id

                return render(request, "admin/search.html", {
                    "form": form,
                    "data": final_data,
                    "existing": False,
                    "pending_save": True,
                    "show_scrape_button": False
                })
            
    return render(request, "admin/search.html", {
        "form": form,
        "data": data,
        "show_scrape_button": False,
        "existing": False,
        "pending_save": False
    })
# results = get_urls(keyword)


def scrape_url_view(request):
    """
    View for url search page
    """
    form = URLForm()
    data = None
    result = None

    if request.method == "POST":
        form = URLForm(request.POST)

        if form.is_valid():

            brand_obj = form.cleaned_data["brand"]
            # brand_name = brand_obj.name
            
            url = form.cleaned_data["url"]
            mode = form.cleaned_data["mode"]

            deep = (mode == "deep")

            # =========================
            # STEP 1: SHOW EXISTING DATA
            # =========================

            existing = BrandDetails.objects.filter(brand=brand_obj).first()

            if existing and "scrape_new" not in request.POST and "confirm_save" not in request.POST:
                print("inside existing")
                return render(request, "admin/url_scrape.html", {
                    "form": form,
                    "data": existing,
                    "existing": True,
                    "show_scrape_button": True
                    
                })
            
            # =========================
            # STEP 2: CONFIRM SAVE
            # =========================
            if "confirm_save" in request.POST:

                result = request.session.get("scraped_data")

                if not result:
                    return render(request, "admin/url_scrape.html", {
                        "form": form,
                        "data": None,
                        "error": "No scraped data found. Please scrape again."
                    })

                obj, created = BrandDetails.objects.update_or_create(
                    brand=brand_obj,
                    defaults={
                        "website": result.get("website"),
                        "phones": result.get("phones"),
                        "emails": result.get("emails"),
                        "facebook": result.get("facebook"),
                        "instagram": result.get("instagram"),
                        "twitter": result.get("twitter"),
                        "linkedin": result.get("linkedin"),
                        "tiktok": result.get("tiktok"),
                        "youtube": result.get("youtube"),
                        "dealers": result.get("dealers"),
                    }
                )

                # clear session after save
                request.session.pop("scraped_data", None)
                request.session.pop("brand_id", None)
                request.session.pop("url", None)

                return render(request, "admin/url_scrape.html", {
                    "form": form,
                    "data": obj,
                    "existing": False,
                    "show_scrape_button": False
                })
            
            # =========================
            # STEP 3: SCRAPE NEW DATA (ONLY ONCE)
            # =========================
            if "scrape_new" in request.POST or not existing:

                result = scrape_from_url(url, deep=deep)

                if not result:
                    result = {
                        "website": url,
                        "phones": [],
                        "emails": [],
                        "dealers": [],
                    }

                 # store in session (temporary state)
                request.session["scraped_data"] = result
                request.session["brand_id"] = brand_obj.id
                request.session["url"] = url

                return render(request, "admin/url_scrape.html", {
                    "form": form,
                    "data": result,
                    "existing": False,
                    "pending_save": True,"show_scrape_button": False
                })
           

            # result = scrape_from_url(url, deep=deep)

            # if not result:
            #     result = {
            #         "website": url,
            #         "phones": [],
            #         "emails": [],
            #         # "logo": None,
            #         "dealers": [],
            #     }

            # # IMPORTANT: DO NOT SAVE
            # request.session["scraped_data"] = result
            # request.session["brand_id"] = brand_obj.id
            # request.session["url"] = url
            
            # obj = BrandDetails.objects.create(
            #     brand=brand_obj,
            #     website=result.get("website"),
            #     phones=result.get("phones"),
            #     emails=result.get("emails"),
            #     # logo=result.get("logo"),
            #     facebook=result.get("facebook"),
            #     instagram=result.get("instagram"),
            #     twitter=result.get("twitter"),
            #     linkedin=result.get("linkedin"),
            #     tiktok=result.get("tiktok"),
            #     youtube=result.get("youtube"),
            #     dealers=result.get("dealers")
            # )

            # data = obj

    return render(request, "admin/url_scrape.html", {
        "form": form,
        "data": data,
        "existing": False,
        "pending_save": False,
        "show_save_button": False
    })

def index(request):
    return render(request, "admin/index.html")

def data(request):
    return render(request, "admin/data.html")

def table(request):
    data = BrandDetails.objects.select_related("brand").all()

    return render(request, "admin/table.html", {"data": data})