import os
from datetime import datetime, timedelta

import pytz
import requests
from dotenv import load_dotenv
from flask import Flask, render_template

load_dotenv()

app = Flask(__name__, template_folder="templates")


def get_timezone_by_country(country_code):
    timezones = pytz.country_timezones.get(country_code)
    if timezones:
        return timezones[0]
    return None


def find_closest_time_to_5pm():
    current_time = datetime.now(pytz.utc)
    closest_time_diff = timedelta.max
    closest_country = None
    closest_time = None

    for country_code in pytz.country_names:
        country = pytz.country_names[country_code]
        timezone = get_timezone_by_country(country_code)
        if timezone is None:
            continue

        local_time = current_time.astimezone(pytz.timezone(timezone))
        time_diff = abs(
            datetime(
                local_time.year,
                local_time.month,
                local_time.day,
                17,
                0,
                tzinfo=pytz.timezone(timezone),
            )
            - datetime(
                local_time.year,
                local_time.month,
                local_time.day,
                local_time.hour,
                local_time.minute,
                local_time.second,
                local_time.microsecond,
                tzinfo=pytz.timezone(timezone),
            )
        )

        if time_diff.total_seconds() < closest_time_diff.total_seconds():
            closest_time_diff = time_diff
            closest_country = country
            closest_time = local_time

    return closest_country, closest_time


def get_national_liquor(country_name):
    try:
        api_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "titles": "List of national liquors",
            "explaintext": 1,
            "exsectionformat": "wiki",
        }

        response = requests.get(api_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        pages = data.get("query", {}).get("pages", {})

        if not pages:
            return "No national alcohol was found"

        page_content = ""
        for _, page_data in pages.items():
            if "extract" in page_data:
                page_content = page_data["extract"]
                break

        if not page_content:
            return "No national alcohol was found"

        lines = page_content.split("\n")
        for line in lines:
            if country_name.lower() in line.lower():
                if ":" in line:
                    liquor = line.split(":", 1)[1].strip()
                elif "–" in line:
                    liquor = line.split("–", 1)[1].strip()
                elif "-" in line:
                    liquor = line.split("-", 1)[1].strip()
                else:
                    continue

                liquor = liquor.split(".")[0].strip()
                liquor = liquor.split("(")[0].strip()
                return liquor if liquor else "No national alcohol was found"

        return "No national alcohol was found"
    except Exception as e:
        print(f"Wikipedia API request error: {e}")
        return "No national alcohol was found"


def get_wikipedia_info(query_term):
    try:
        url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query_term,
            "srprop": "size",
            "utf8": 1,
            "formatversion": 2,
        }

        response = requests.get(url, params=search_params, timeout=10)
        response.raise_for_status()
        json_data = response.json()

        if (
            "query" not in json_data
            or "search" not in json_data["query"]
            or not json_data["query"]["search"]
        ):
            return {"images": [], "text": "No description available", "error": "No search results found"}

        page_id = json_data["query"]["search"][0]["pageid"]

        page_params = {
            "action": "query",
            "format": "json",
            "prop": "extracts|images",
            "pageids": page_id,
            "exintro": True,
            "explaintext": True,
            "utf8": 1,
            "formatversion": 2,
        }

        response = requests.get(url, params=page_params, timeout=10)
        response.raise_for_status()
        data = response.json()
        pages = data.get("query", {}).get("pages", [])

        if not pages:
            return {"images": [], "text": "No description available", "error": "No page data found"}

        page = pages[0]
        text = page.get("extract", "No description available")
        images = page.get("images", [])

        image_urls = []
        if images:
            try:
                image_titles = [img["title"] for img in images[:10]]
                image_params = {
                    "action": "query",
                    "prop": "imageinfo",
                    "format": "json",
                    "iiprop": "url",
                    "titles": "|".join(image_titles),
                    "utf8": 1,
                    "formatversion": 2,
                }
                response = requests.get(url, params=image_params, timeout=10)
                response.raise_for_status()
                img_data = response.json()
                img_pages = img_data.get("query", {}).get("pages", [])

                for img_page in img_pages:
                    if "imageinfo" in img_page and img_page["imageinfo"]:
                        img_url = img_page["imageinfo"][0].get("url", "")
                        if img_url.lower().endswith((".png", ".jpg", ".jpeg")):
                            image_urls.append(img_url)
            except Exception as e:
                print(f"Error getting image URLs: {e}")

        sentences = text.split(".")
        if sentences:
            message = ""
            for sentence in sentences:
                if len(message + sentence) < 500:
                    message += sentence + "."
                else:
                    break
            text = message.strip()

        return {"images": image_urls[:5], "text": text, "error": None}
    except Exception as e:
        print(f"Wikipedia info error: {e}")
        return {"images": [], "text": "No description available", "error": str(e)}


def build_page_context():
    country, closest_time = find_closest_time_to_5pm()
    alcohols = get_national_liquor(country)
    query = country if alcohols == "No national alcohol was found" else alcohols
    wiki_info = get_wikipedia_info(query)

    string1 = f"The closest country to 5:00 PM is {country}. "
    string2 = f"The local time is: {closest_time.strftime('%I:%M %p')}. "
    string3 = " " if alcohols == "No national alcohol was found" else f"In {country} they drink: {alcohols}. "

    return {
        "string1": string1,
        "string2": string2,
        "string3": string3,
        "links": wiki_info["images"],
        "message": wiki_info["text"],
    }


@app.route("/")
@app.route("/5")
def five_pm():
    return render_template("5.html", **build_page_context())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
