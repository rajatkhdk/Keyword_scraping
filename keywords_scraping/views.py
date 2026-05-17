from django.shortcuts import render, redirect, get_object_or_404
from .forms import SearchForm, URLForm, CarBrandForm
from .models import CarBrand, BrandDetails, Dealers
from keywords_scraping.ddgs_search import get_urls
from keywords_scraping.extract_data_1 import extract_basic_info, fetch_soup, get_pages_to_scrape
from dealer_scraper_1 import scrape_dealers
import asyncio
import re
from dal import autocomplete
from keywords_scraping.utility import deduplicate_contacts, standardize_dealers, normalize_phone, normalize_email
from django.db import transaction
import json
from openpyxl import Workbook
from django.http import HttpResponse

from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak)
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter


def build_context(form, **kwargs):
    context = {
        "form": form,
        "data": None,
        "existing": False,
        "pending_save": False,
        "show_scrape_button": False,
    }

    context.update(kwargs)

    return context

def save_brand_details(brand_obj, result):

    obj, created = BrandDetails.objects.update_or_create(
        brand=brand_obj,
        defaults={
            "website": result.get("website"),
            "phones": result.get("phones", []),
            "emails": result.get("emails", []),
            "facebook": result.get("facebook", []),
            "instagram": result.get("instagram", []),
            "twitter": result.get("twitter", []),
            "linkedin": result.get("linkedin", []),
            "tiktok": result.get("tiktok", []),
            "youtube": result.get("youtube", []),
        }
    )

    return obj

def save_dealers(brand_detail, dealers):

    # ---------------------------------------------------------
    # NORMALIZE SCRAPED DEALERS
    # ---------------------------------------------------------

    normalized_scraped = []

    seen = set()

    for d in dealers:

        name = (d.get("name") or "").strip()
        address = (d.get("address") or "").strip()

        phones = d.get("phones") or d.get("phone") or []
        emails = d.get("emails") or d.get("email") or []

        if not name and not address:
            continue

        key = (
            name.lower(),
            address.lower(),
        )

        if key in seen:
            continue

        seen.add(key)

        normalized_scraped.append({
            "name": name,
            "address": address,
            "phones": phones,
            "emails": emails,
            "key": key,
        })

    # ---------------------------------------------------------
    # EXISTING DEALERS
    # ---------------------------------------------------------

    existing_dealers = list(
        brand_detail.dealers.all().order_by("id")
    )

    existing_map = {
        (
            (d.name or "").strip().lower(),
            (d.address or "").strip().lower(),
        ): d
        for d in existing_dealers
    }

    matched_keys = set()

    update_objects = []
    create_objects = []

    # unmatched old rows available for reuse
    reusable_old = []

    # ---------------------------------------------------------
    # STEP 1: KEEP MATCHED ROWS
    # ---------------------------------------------------------

    for scraped in normalized_scraped:

        key = scraped["key"]

        if key in existing_map:

            matched_keys.add(key)

            # optionally refresh phones/emails
            obj = existing_map[key]

            obj.phones = scraped["phones"]
            obj.emails = scraped["emails"]

            update_objects.append(obj)

    # ---------------------------------------------------------
    # STEP 2: FIND OLD UNMATCHED ROWS
    # ---------------------------------------------------------

    for key, obj in existing_map.items():

        if key not in matched_keys:
            reusable_old.append(obj)

    # ---------------------------------------------------------
    # STEP 3: HANDLE NEW UNMATCHED DEALERS
    # ---------------------------------------------------------

    unmatched_new = []

    for scraped in normalized_scraped:

        if scraped["key"] not in matched_keys:
            unmatched_new.append(scraped)

    # ---------------------------------------------------------
    # STEP 4: REUSE OLD ROW IDS
    # ---------------------------------------------------------

    reusable_count = min(
        len(reusable_old),
        len(unmatched_new)
    )

    for i in range(reusable_count):

        old_obj = reusable_old[i]
        new_data = unmatched_new[i]

        old_obj.name = new_data["name"]
        old_obj.address = new_data["address"]
        old_obj.phones = new_data["phones"]
        old_obj.emails = new_data["emails"]

        update_objects.append(old_obj)

    # ---------------------------------------------------------
    # STEP 5: CREATE EXTRA NEW ROWS
    # ---------------------------------------------------------

    for new_data in unmatched_new[reusable_count:]:

        create_objects.append(
            Dealers(
                brand_detail=brand_detail,
                name=new_data["name"],
                address=new_data["address"],
                phones=new_data["phones"],
                emails=new_data["emails"],
            )
        )

    # ---------------------------------------------------------
    # STEP 6: DELETE EXTRA OLD ROWS
    # ---------------------------------------------------------

    for old_obj in reusable_old[reusable_count:]:

        old_obj.delete()

    # ---------------------------------------------------------
    # STEP 7: BULK OPERATIONS
    # ---------------------------------------------------------

    if update_objects:

        Dealers.objects.bulk_update(
            update_objects,
            ["name", "address", "phones", "emails", "updated_at"]
        )

    if create_objects:

        Dealers.objects.bulk_create(create_objects)
        
def process_scraped_data(result):

    if not result:
        return {
            "website": "",
            "phones": [],
            "emails": [],
            "facebook": [],
            "instagram": [],
            "twitter": [],
            "linkedin": [],
            "youtube": [],
            "tiktok": [],
            "dealers": [],
        }

    result["dealers"] = standardize_dealers(
        result.get("dealers", [])
    )

    result = deduplicate_contacts(result)

    return result

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

    if (any(k in url for k in ["dealer", "showroom", "location", "branch", "network", "locate", 'store'])
    and "become" not in url):
        print("dealer")
        return True

    if html:
        text = html.lower()
        if "dealer" in text or "showroom" in text:
            return True

    return False

def split_fields(value):

    if not value:
        return []
    
    if isinstance(value, list):

        final = []

        for item in value:
            final.extend(split_fields(item))

        return final
    
    # split string
    parts = re.split(r"[,/|;\n]+", str(value))

    return [ p.strip() for p in parts if p.strip()]

def scrape_from_url(base_url, deep=True):

    """
    Crawl a website and extract:
    - phones
    - emails
    - socials
    - dealers

    Flow:
    1. Fetch homepage soup
    2. Discover pages (if deep=True)
    3. Crawl pages
    4. Extract basic info or dealer data
    5. Deduplicate final result
    """

    try:

        homepage_soup = fetch_soup(base_url)

        if not homepage_soup:
            return None

        # =====================================================
        # STEP 1: BUILD PAGE LIST
        # =====================================================

        if deep:
            pages = [base_url] + get_pages_to_scrape(
                homepage_soup,
                base_url
            )
        else:
            pages = [base_url]

        # dedupe preserve order
        pages = list(dict.fromkeys(pages))

        print(f"\n[INFO] Total pages to scrape: {len(pages)}")

        # =====================================================
        # STEP 2: GLOBAL ACCUMULATORS
        # =====================================================

        all_phones = set()
        all_emails = set()

        all_facebook = set()
        all_instagram = set()
        all_twitter = set()
        all_linkedin = set()
        all_youtube = set()
        all_tiktok = set()

        all_dealers = []

        # =====================================================
        # STEP 3: SCRAPE PAGES
        # =====================================================

        for page in pages:

            print(f"\n[SCRAPING] {page}")

            try:

                # =============================================
                # DEALER PAGE
                # =============================================

                if is_dealer_page(page, None):

                    print(f"[DEALER PAGE] {page}")

                    try:

                        dealers = scrape_dealers_sync(page)
                        # print("\n 1. dealers : ", dealers)

                        if dealers:

                            for dealer in dealers:

                                standardized_dealer = {
                                    "name": (
                                        dealer.get("name", "")
                                        .strip()
                                    ),

                                    "address": (
                                        dealer.get("address", "")
                                        .strip()
                                    ),

                                    # STANDARDIZED
                                    "phones": [
                                        normalize_phone(p)
                                        for p in split_fields(
                                            dealer.get("phones", dealer.get("phone", []))
                                        )
                                        if normalize_phone(p)
                                    ],

                                    "emails": [
                                        normalize_email(e)
                                        for e in split_fields(
                                                dealer.get("emails", dealer.get("email", []))
                                            )
                                        if normalize_email(e)
                                    ],
                                }

                                # skip completely empty dealers
                                if not any([
                                    standardized_dealer["name"],
                                    standardized_dealer["address"],
                                    standardized_dealer["phones"],
                                    standardized_dealer["emails"],
                                ]):
                                    continue

                                all_dealers.append(
                                    standardized_dealer
                                )

                                # print("2. All dealers : ", all_dealers)

                    except Exception as dealer_error:

                        print(
                            f"[DEALER ERROR] "
                            f"{page} -> {dealer_error}"
                        )

                # =============================================
                # NORMAL PAGE
                # =============================================

                else:

                    data = extract_basic_info(page)

                    if not data:
                        continue

                    # -----------------------------
                    # Phones
                    # -----------------------------

                    for p in data.get("phones", []):

                        normalized = normalize_phone(p)

                        if normalized:
                            all_phones.add(normalized)

                    # -----------------------------
                    # Emails
                    # -----------------------------

                    for e in data.get("emails", []):

                        normalized = normalize_email(e)

                        if normalized:
                            all_emails.add(normalized)

                    # -----------------------------
                    # Socials
                    # -----------------------------

                    all_facebook.update(
                        data.get("facebook", [])
                    )

                    all_instagram.update(
                        data.get("instagram", [])
                    )

                    all_twitter.update(
                        data.get("twitter", [])
                    )

                    all_linkedin.update(
                        data.get("linkedin", [])
                    )

                    all_youtube.update(
                        data.get("youtube", [])
                    )

                    all_tiktok.update(
                        data.get("tiktok", [])
                    )

            except Exception as page_error:

                print(
                    f"[PAGE ERROR] "
                    f"{page} -> {page_error}"
                )

        # =====================================================
        # STEP 4: DEALER DEDUPLICATION
        # =====================================================

        unique_dealers = []

        seen = set()

        for dealer in all_dealers:

            # print(" 3. Dealer : ", dealer)

            phones = tuple(sorted(
                re.sub(r"\D", "", p)
                for p in dealer.get("phones", [])
                if p
            ))

            emails = tuple(sorted(
                e.lower().strip()
                for e in dealer.get("emails", [])
                if e
            ))

            name = dealer.get("name", "").strip().lower()

            address = dealer.get("address", "").strip().lower()

            # priority matching
            if phones:
                key = ("phone", phones)

            elif emails:
                key = ("email", emails)

            elif name and address:
                key = ("name_address", name, address)

            elif name:
                key = ("name", name)

            else:
                continue

            if key in seen:
                continue

            seen.add(key)

            unique_dealers.append(dealer)

            # print("Dealer : ", dealer)
            # print("Unique Dealer : ", dealer)

        # =====================================================
        # STEP 5: FINAL OUTPUT
        # =====================================================

        final_result = {

            "website": base_url,

            "phones": sorted(all_phones),

            "emails": sorted(all_emails),

            "facebook": sorted(all_facebook),

            "instagram": sorted(all_instagram),

            "twitter": sorted(all_twitter),

            "linkedin": sorted(all_linkedin),

            "youtube": sorted(all_youtube),

            "tiktok": sorted(all_tiktok),

            "dealers": unique_dealers,
        }

        print(
            f"\n[FINAL RESULT]"
            f"\nPhones: {len(final_result['phones'])}"
            f"\nEmails: {len(final_result['emails'])}"
            f"\nDealers: {len(final_result['dealers'])}"
        )

        # print("Final result : ", final_result)

        return final_result

    except Exception as e:

        print(f"[SITE ERROR] {base_url} -> {e}")

        return None
    
@transaction.atomic
def search_view(request):

    form = SearchForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        brand_obj = form.cleaned_data["brand"]
        brand_name = brand_obj.name

        existing = BrandDetails.objects.filter(
            brand=brand_obj
        ).first()

        # ==================================================
        # SHOW EXISTING
        # ==================================================

        if (
            existing
            and "scrape_new" not in request.POST
            and "confirm_save" not in request.POST
        ):

            return render(
                request,
                "admin/search.html",
                build_context(
                    form,
                    data=existing,
                    existing=True,
                    show_scrape_button=True,
                    dealers=existing.dealers.all()
                )
            )

        # ==================================================
        # CONFIRM SAVE
        # ==================================================

        if "confirm_save" in request.POST:

            result = request.session.get("scraped_data")

            if not result:

                return render(
                    request,
                    "admin/search.html",
                    build_context(
                        form,
                        error="No scraped data found."
                    )
                )

            obj = save_brand_details(
                brand_obj,
                result
            )

            save_dealers(
                obj,
                result.get("dealers", [])
            )

            request.session.pop("scraped_data", None)
            request.session.pop("brand_id", None)

            return render(
                request,
                "admin/search.html",
                build_context(
                    form,
                    data=obj,
                    dealers=obj.dealers.all()
                )
            )

        # ==================================================
        # SCRAPE NEW
        # ==================================================

        if "scrape_new" in request.POST or not existing:

            results = get_urls(brand_name)

            final_data = None

            for r in results[:5]:

                base_url = r[1]

                candidate_data = scrape_from_url(
                    base_url,
                    deep=True
                )

                candidate_data = process_scraped_data(
                    candidate_data
                )

                if (
                    candidate_data.get("phones")
                    or candidate_data.get("dealers")
                ):
                    final_data = candidate_data
                    break

                if not final_data:
                    final_data = candidate_data

            if not final_data:

                return render(
                    request,
                    "admin/search.html",
                    build_context(
                        form,
                        error="No data scraped."
                    )
                )

            request.session["scraped_data"] = final_data
            request.session["brand_id"] = brand_obj.id

            return render(
                request,
                "admin/search.html",
                build_context(
                    form,
                    data=final_data,
                    pending_save=True,
                    dealers=final_data.get("dealers", [])
                )
            )

    return render(
        request,
        "admin/search.html",
        build_context(form)
    )


def scrape_url_view(request):
    """
    View for URL scraping page
    """

    form = URLForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        brand_obj = form.cleaned_data["brand"]
        url = form.cleaned_data["url"]
        mode = form.cleaned_data["mode"]

        deep = (mode == "deep")

        # =========================================================
        # STEP 1: GET EXISTING DATA
        # =========================================================

        existing = (
            BrandDetails.objects
            .select_related("brand")
            .prefetch_related("dealers")
            .filter(brand=brand_obj)
            .first()
        )

        # =========================================================
        # STEP 2: SHOW EXISTING DATA
        # =========================================================

        if (
            existing
            and "scrape_new" not in request.POST
            and "confirm_save" not in request.POST
        ):

            return render(
                request,
                "admin/url_scrape.html",
                build_context(
                    form,
                    data=existing,
                    dealers=existing.dealers.all(),
                    existing=True,
                    show_scrape_button=True,
                )
            )

        # =========================================================
        # STEP 3: SAVE SCRAPED DATA
        # =========================================================

        if "confirm_save" in request.POST:

            result = request.session.get("scraped_data")

            if not result:
                return render(
                    request,
                    "admin/url_scrape.html",
                    build_context(
                        form,
                        error="No scraped data found. Please scrape again."
                    )
                )

            result = process_scraped_data(result)

            try:

                with transaction.atomic():

                    # -----------------------------------------
                    # SAVE BRAND DETAILS
                    # -----------------------------------------

                    obj = save_brand_details(
                        brand_obj,
                        result
                    )

                    # -----------------------------------------
                    # SAVE DEALERS
                    # -----------------------------------------

                    save_dealers(
                        obj,
                        result.get("dealers", [])
                    )

            except Exception as e:

                return render(
                    request,
                    "admin/url_scrape.html",
                    build_context(
                        form,
                        error=str(e)
                    )
                )

            # -----------------------------------------
            # CLEAR SESSION
            # -----------------------------------------

            request.session.pop("scraped_data", None)
            request.session.pop("brand_id", None)
            request.session.pop("url", None)

            # reload updated object
            obj = (
                BrandDetails.objects
                .select_related("brand")
                .prefetch_related("dealers")
                .get(id=obj.id)
            )

            return render(
                request,
                "admin/url_scrape.html",
                build_context(
                    form,
                    data=obj,
                    dealers=obj.dealers.all(),
                    existing=False,
                    pending_save=False,
                )
            )

        # =========================================================
        # STEP 4: SCRAPE NEW DATA
        # =========================================================

        if "scrape_new" in request.POST or not existing:

            result = scrape_from_url(
                url,
                deep=deep
            )

            # print("Result -> scrape from url : ", result)
            result = process_scraped_data(result)
            # print("Result -> process scraped data : ", result)

            # temporary session storage
            request.session["scraped_data"] = result
            request.session["brand_id"] = brand_obj.id
            request.session["url"] = url

            return render(
                request,
                "admin/url_scrape.html",
                build_context(
                    form,
                    data=result,
                    dealers=result.get("dealers", []),
                    pending_save=True,
                )
            )

    return render(
        request,
        "admin/url_scrape.html",
        build_context(form)
    )
 
def index(request):
    return render(request, "admin/index.html")

def data(request):
    return render(request, "admin/data.html")

def table(request):
    search = request.GET.get('search', '')
    data = BrandDetails.objects.select_related("brand").prefetch_related("dealers").all()

    if search:
        data = data.filter(brand__name__icontains=search)

    table_data = []

    for item in data:
        dealers = item.dealers.all()

        dealer_list = [
            {
                "id":      dealer.id,
                "name":    dealer.name or '',
                "address": dealer.address or '',
                "phones":  dealer.phones or [],
                "emails":  dealer.emails or [],
            }
            for dealer in dealers
        ]

        social_links = {
            "facebook":  item.facebook,
            "instagram": item.instagram,
            "twitter":   item.twitter,
            "linkedin":  item.linkedin,
            "youtube":   item.youtube,
            "tiktok":    item.tiktok,
        }
        active_socials = {k: v for k, v in social_links.items() if v}

        table_data.append({
            "id":            item.id,
            "dealer_key":    f"d_{item.id}",   # ← clean string ID for template
            "social_key":    f"s_{item.id}",   # ← clean string ID for template
            "brand_name":    item.brand.name if item.brand else '',
            "website":       item.website or '',
            "phones":        item.phones or [],
            "emails":        item.emails or [],
            "dealers_count": dealers.count(),
            "dealers":       dealer_list,
            "socials":       active_socials,
            "has_social":    bool(active_socials),
        })

    return render(request, "admin/table.html", {
        "table_data": table_data,
        "search":     search,
    })

def carbrands(request):

    search = request.GET.get("search", "").strip()

    data = CarBrand.objects.all().order_by("name")

    if search:
        data = data.filter(name__icontains=search)

    context = {
        "data": data,
        "search": search,
    }

    return render(request, "admin/car_brand.html", context)


# placeholder views for now

def add_carbrand(request):
    
    if request.method == "POST":

        form = CarBrandForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("car_brand")

    else:
        form = CarBrandForm()

    return render(
        request,
        "admin/add_car_brand.html",
        {"form": form}
    )


def edit_carbrand(request, id):
    brand = get_object_or_404(
        CarBrand,
        id=id
    )

    if request.method == "POST":

        form = CarBrandForm(
            request.POST,
            instance=brand
        )

        if form.is_valid():

            form.save()

            return redirect("car_brand")

    else:

        form = CarBrandForm(
            instance=brand
        )

    return render(
        request,
        "admin/edit_car_brand.html",
        {
            "form": form,
            "brand": brand,
        }
    )


def delete_carbrand(request, id):
    brand = get_object_or_404(CarBrand, id=id)

    brand.delete()

    return redirect("car_brand")

def export_excel(request):

    wb = Workbook()
    ws = wb.active
    ws.title = "Brand Details"

    headers = [
        "Brand",
        "Website",
        "Phones",
        "Emails",
        "Dealer Name",
        "Dealer Address",
        "Dealer Phones",
        "Dealer Emails",
        "Facebook",
        "Instagram",
        "Youtube",
        "Twitter",
        "Linkedin",
        "Tiktok"
    ]

    ws.append(headers)

    brands = BrandDetails. objects.select_related(
        "brand"
    ).prefetch_related("dealers")

    for brand in brands:

        socials = {
            "facebook": brand.facebook or [],
            "instagram": brand.instagram or [],
            "youtube": brand.youtube or [],
            "twitter": brand.twitter or [],
            "linkedin": brand.linkedin or [],
            "tiktok": brand.tiktok or [],
        }

        dealers = brand.dealers.all()

        if dealers.exists():

            for dealer in dealers:

                ws.append([
                    brand.brand.name,
                    brand.website,

                    ", ".join(brand.phones or []),
                    ", ".join(brand.emails or []),

                    dealer.name,
                    dealer.address,

                    ", ".join(dealer.phones or []),
                    ", ".join(dealer.emails or []),

                    ", ".join(socials["facebook"]),
                    ", ".join(socials["instagram"]),
                    ", ".join(socials["youtube"]),
                    ", ".join(socials["twitter"]),
                    ", ".join(socials["linkedin"]),
                    ", ".join(socials["tiktok"]),
                ])

        else:

             ws.append([
                brand.brand.name,
                brand.website,

                ", ".join(brand.phones or []),
                ", ".join(brand.emails or []),

                "",
                "",
                "",
                "",

                ", ".join(socials["facebook"]),
                ", ".join(socials["instagram"]),
                ", ".join(socials["youtube"]),
            ])

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    response["Content-Disposition"] = (
        'attachment; filename="brand_details.xlsx"'
    )

    wb.save(response)

    return response

def export_pdf(request):

    # ─────────────────────────────
    # Response
    # ─────────────────────────────
    response = HttpResponse(
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        'attachment; filename="brand_details.pdf"'
    )

    # ─────────────────────────────
    # Document
    # ─────────────────────────────
    doc = SimpleDocTemplate(
        response,
        pagesize=letter,
        rightMargin=25,
        leftMargin=25,
        topMargin=25,
        bottomMargin=20,
    )

    # ─────────────────────────────
    # Styles
    # ─────────────────────────────
    styles = getSampleStyleSheet()

    cell_style = styles["BodyText"]

    cell_style.fontName = "Helvetica"
    cell_style.fontSize = 8
    cell_style.leading = 10

    heading_style = styles["Heading3"]

    elements = []

    # ─────────────────────────────
    # Helper Functions
    # ─────────────────────────────
    def p(text):

        """
        Safe paragraph wrapper
        """

        if isinstance(text, list):
            text = "<br/>".join(
                str(x) for x in text if x
            )

        text = text or "-"

        return Paragraph(
            str(text),
            cell_style
        )


    def create_table(data, col_widths, header_color):

        table = Table(
            data,
            colWidths=col_widths,
            repeatRows=1,
        )

        table.setStyle(TableStyle([

            # Header
            ("BACKGROUND", (0,0), (-1,0), header_color),

            ("TEXTCOLOR", (0,0), (-1,0), colors.black),

            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),

            # Body
            ("FONTNAME", (0,1), (-1,-1), "Helvetica"),

            ("FONTSIZE", (0,0), (-1,-1), 8),

            ("LEADING", (0,0), (-1,-1), 10),

            ("VALIGN", (0,0), (-1,-1), "TOP"),

            ("WORDWRAP", (0,0), (-1,-1), "CJK"),

            # Padding
            ("TOPPADDING", (0,0), (-1,-1), 6),

            ("BOTTOMPADDING", (0,0), (-1,-1), 6),

            ("LEFTPADDING", (0,0), (-1,-1), 5),

            ("RIGHTPADDING", (0,0), (-1,-1), 5),

            # Grid
            ("GRID", (0,0), (-1,-1), 1, colors.grey),

        ]))

        return table

    # ─────────────────────────────
    # Query
    # ─────────────────────────────
    brands = (
        BrandDetails.objects
        .select_related("brand")
        .prefetch_related("dealers")
    )

    # ─────────────────────────────
    # Generate PDF
    # ─────────────────────────────
    for brand in brands:

        # ==========================
        # BRAND TITLE
        # ==========================
        elements.append(
            Paragraph(
                f"<b>{brand.brand.name}</b>",
                styles["Heading1"]
            )
        )

        elements.append(Spacer(1, 10))

        # ==========================
        # BASIC INFO TABLE
        # ==========================
        basic_rows = [

            [p("Field"), p("Value")],

            [p("Website"), p(brand.website)],

            [p("Phones"), p(brand.phones)],

            [p("Emails"), p(brand.emails)],
        ]

        basic_table = create_table(
            data=basic_rows,
            col_widths=[120, 380],
            header_color=colors.lightgrey,
        )

        elements.append(basic_table)

        elements.append(Spacer(1, 15))

        # ==========================
        # SOCIAL TABLE
        # ==========================
        elements.append(
            Paragraph(
                "<b>Social Links</b>",
                heading_style
            )
        )

        social_rows = [
            [p("Platform"), p("Links")]
        ]

        socials = {
            "Facebook": brand.facebook,
            "Instagram": brand.instagram,
            "Twitter": brand.twitter,
            "LinkedIn": brand.linkedin,
            "Youtube": brand.youtube,
            "TikTok": brand.tiktok,
        }

        has_socials = False

        for platform, links in socials.items():

            if links:

                has_socials = True

                social_rows.append([
                    p(platform),
                    p(links),
                ])

        if not has_socials:

            social_rows.append([
                p("-"),
                p("No Social Links"),
            ])

        social_table = create_table(
            data=social_rows,
            col_widths=[120, 380],
            header_color=colors.lightblue,
        )

        elements.append(social_table)

        elements.append(Spacer(1, 15))

        # ==========================
        # DEALER TABLE
        # ==========================
        elements.append(
            Paragraph(
                "<b>Dealers</b>",
                heading_style
            )
        )

        dealer_rows = [[
            p("Name"),
            p("Address"),
            p("Phones"),
            p("Emails"),
        ]]

        dealers = brand.dealers.all()

        if dealers.exists():

            for dealer in dealers:

                dealer_rows.append([

                    p(dealer.name),

                    p(dealer.address),

                    p(dealer.phones),

                    p(dealer.emails),
                ])

        else:

            dealer_rows.append([
                p("No Dealers Found"),
                p(""),
                p(""),
                p(""),
            ])

        dealer_table = create_table(
            data=dealer_rows,
            col_widths=[100, 220, 110, 110],
            header_color=colors.lightgreen,
        )

        elements.append(dealer_table)

        elements.append(Spacer(1, 25))

        # Optional page break
        elements.append(PageBreak())

    # ─────────────────────────────
    # Build PDF
    # ─────────────────────────────
    doc.build(elements)

    return response

