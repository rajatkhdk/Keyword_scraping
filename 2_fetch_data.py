from bs4 import BeautifulSoup
import pandas as pd

with open("page1.html", "r", encoding="utf-8") as f:
    soup = BeautifulSoup(f.read(), "html.parser")

brands = []

# find all brand items
carousel = soup.find("div", class_="owl-carousel", attrs={
    "data-loop":"false",
    "data-nav-dots":"true",
    "data-nav-arrow":"false",
    "data-items":"6",
    "data-sm-items":"4",
    "data-lg-items":"3",
    "data-md-items":"3",
    "data-xs-items":"2",
    "data-autoplay":"true",
})
items = carousel.find_all("div", class_="item")

brands = []

for item in items:
    a_tag = item.find("a")
    img_tag = item.find("img")

    if a_tag and img_tag:
        link = a_tag["href"]
        image = img_tag["src"]
        name = img_tag.get("alt")

        brands.append({
            "name": name,
            "link": link,
            "image": image
        })

# for b in brands[-5::1]:
#     print(b)

df = pd.DataFrame(brands)
df.to_csv("brands.csv", index=False)

print(df.head())