from django.shortcuts import render
from .forms import SearchForm
from .models import CarBrand
from keywords_scraping.ddgs_search import get_urls
from keywords_scraping.extract_data_1 import extract_basic_info, fetch_soup, get_pages_to_scrape
# from key_scrape.extract_data
# # import your scraper functions
# from key_scrape.ddgs_search import get_urls
# from key_scrape.extract_data import extract_basic_info, fetch_soup

def search_view(request):
    form = SearchForm()
    data = None

    if request.method == "POST":
        form = SearchForm(request.POST)

        if form.is_valid():
            keyword = form.cleaned_data["keyword"]

            results = get_urls(keyword)  
            r = results[0]
            # print("Result 1: ",r)
            # info = extract_basic_info(r[1])
            # print(info)

            base_url = r[1]

            homepage_soup = fetch_soup(base_url)

            pages = get_pages_to_scrape(homepage_soup, base_url)

            # include homepage itself
            pages = [base_url] + pages

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

                    all_phones.extend(data["phones"])
                    all_emails.extend(data["emails"])

                    # merge socials
                    all_facebook.update(data["facebook"])
                    all_instagram.update(data["instagram"])
                    all_twitter.update(data["twitter"])
                    all_linkedin.update(data["linkedin"])
                    all_youtube.update(data["youtube"])
                    all_tiktok.update(data["tiktok"])

                    # keep first valid logo
                    if not logo and data["logo"]:
                        logo = data["logo"]

                except Exception as e:
                    print(f"Error: {e}")

            final_data = {
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

            print(final_data)
            print("website202: ", final_data.get("website"))

            # Step 1: get best URL
            
            # if results:
            #     url = results[0][1]

            #     # Step 2: extract data
            #     extracted = extract_basic_info(url)

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