import hashlib
import os
from datetime import datetime, timedelta
from functools import lru_cache

import pytz
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request

load_dotenv()

app = Flask(__name__, template_folder="templates")
WIKI_API = "https://en.wikipedia.org/w/api.php"
REST_COUNTRIES_API = "https://restcountries.com/v3.1/alpha"
OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"
REQUEST_HEADERS = {
    "User-Agent": "itsfivepmsomewhere/1.0 (https://localhost; contact: local-dev)"
}
NO_DRINK_TEXT = "No national drink was found"

CHEERS_BY_LANGUAGE = {
    "en": {"phrase": "Cheers!", "pronunciation": "cheerz"},
    "es": {"phrase": "Salud!", "pronunciation": "sah-LOOD"},
    "fr": {"phrase": "Sante!", "pronunciation": "sahn-TAY"},
    "de": {"phrase": "Prost!", "pronunciation": "prohst"},
    "it": {"phrase": "Cin cin!", "pronunciation": "cheen-cheen"},
    "pt": {"phrase": "Saude!", "pronunciation": "sah-OO-jee"},
    "nl": {"phrase": "Proost!", "pronunciation": "prohst"},
    "sv": {"phrase": "Skal!", "pronunciation": "skohl"},
    "no": {"phrase": "Skal!", "pronunciation": "skohl"},
    "da": {"phrase": "Skal!", "pronunciation": "skehl"},
    "fi": {"phrase": "Kippis!", "pronunciation": "KEEP-pees"},
    "pl": {"phrase": "Na zdrowie!", "pronunciation": "nah zdroh-VYEH"},
    "cs": {"phrase": "Na zdravi!", "pronunciation": "nah ZDRAH-vee"},
    "sk": {"phrase": "Na zdravie!", "pronunciation": "nah ZDRAH-vee-eh"},
    "hu": {"phrase": "Egeszsegedre!", "pronunciation": "eh-gaysh-SHAY-ghed-reh"},
    "ro": {"phrase": "Noroc!", "pronunciation": "noh-ROK"},
    "tr": {"phrase": "Serefe!", "pronunciation": "sheh-reh-FEH"},
    "el": {"phrase": "Yamas!", "pronunciation": "yah-MAHS"},
    "ru": {"phrase": "Za zdorovye!", "pronunciation": "zah zda-ROV-ye"},
    "uk": {"phrase": "Budmo!", "pronunciation": "BOOD-moh"},
    "ar": {"phrase": "Fi sehatak!", "pronunciation": "fee seh-HA-tak"},
    "he": {"phrase": "Lechaim!", "pronunciation": "leh-KHAI-im"},
    "hi": {"phrase": "Cheers!", "pronunciation": "cheerz"},
    "bn": {"phrase": "Cheers!", "pronunciation": "cheerz"},
    "ja": {"phrase": "Kanpai!", "pronunciation": "kahn-PIE"},
    "ko": {"phrase": "Geonbae!", "pronunciation": "guhn-bay"},
    "zh": {"phrase": "Ganbei!", "pronunciation": "gahn-bay"},
    "vi": {"phrase": "Mot, hai, ba, yo!", "pronunciation": "moht hi bah yo"},
    "th": {"phrase": "Chon kaew!", "pronunciation": "chon gao"},
    "id": {"phrase": "Bersulang!", "pronunciation": "ber-soo-LAHNG"},
    "ms": {"phrase": "Sorak!", "pronunciation": "soh-RAK"},
    "sw": {"phrase": "Afya!", "pronunciation": "AHF-yah"},
}

WEATHER_CODE_LABELS = {
    0: "Clear sky",
    1: "Mostly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Foggy",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Heavy freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Severe thunderstorm",
}


def pick_by_seed(options, seed):
    hashed_value = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return options[int(hashed_value, 16) % len(options)]


def get_five_pm_candidates(limit=40):
    current_time_utc = datetime.now(pytz.utc)
    excluded_country_codes = {"AQ"}
    candidates = []

    for country_code, country_name in pytz.country_names.items():
        if country_code in excluded_country_codes:
            continue
        timezones = pytz.country_timezones.get(country_code, [])
        for timezone_name in timezones:
            local_time = current_time_utc.astimezone(pytz.timezone(timezone_name))
            today_five = local_time.replace(hour=17, minute=0, second=0, microsecond=0)
            diff = abs(local_time - today_five)
            next_five = today_five if local_time <= today_five else today_five + timedelta(days=1)

            candidates.append(
                {
                    "country": country_name,
                    "country_code": country_code,
                    "timezone_name": timezone_name,
                    "local_time": local_time,
                    "minutes_from_five": int(diff.total_seconds() // 60),
                    "seconds_to_next_five": int((next_five - local_time).total_seconds()),
                    "is_exactly_five": local_time.hour == 17 and local_time.minute == 0,
                }
            )

    candidates.sort(key=lambda item: (item["minutes_from_five"], item["country"], item["timezone_name"]))
    return candidates[:limit]


def pick_candidate(spin_index):
    candidates = get_five_pm_candidates(limit=60)
    safe_spin = max(spin_index, 0)
    if not candidates:
        return None, [], 0
    picked_index = safe_spin % len(candidates)
    return candidates[picked_index], candidates, picked_index


@lru_cache(maxsize=256)
def get_national_liquor(country_name):
    try:
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "titles": "List of national liquors",
            "explaintext": 1,
            "exsectionformat": "wiki",
        }
        response = requests.get(WIKI_API, params=params, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", {})
        page_content = next(
            (page_data.get("extract", "") for page_data in pages.values() if "extract" in page_data),
            "",
        )

        for line in page_content.split("\n"):
            if country_name.lower() not in line.lower():
                continue
            for separator in [":", "–", "-"]:
                if separator in line:
                    liquor = line.split(separator, 1)[1].split(".")[0].split("(")[0].strip()
                    return liquor if liquor else NO_DRINK_TEXT
        return NO_DRINK_TEXT
    except Exception as error:
        print(f"National liquor lookup error: {error}")
        return NO_DRINK_TEXT


def trim_text_by_sentences(text, max_chars=480):
    message = []
    for sentence in text.split("."):
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{'. '.join(message)}. {sentence}".strip(". ")
        if len(candidate) > max_chars:
            break
        message.append(sentence)
    return ". ".join(message) + ("." if message else "")


@lru_cache(maxsize=256)
def get_wikipedia_info(query_term):
    try:
        search_params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query_term,
            "utf8": 1,
            "formatversion": 2,
        }
        response = requests.get(WIKI_API, params=search_params, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        search_results = response.json().get("query", {}).get("search", [])

        if not search_results:
            return {"images": [], "text": "No description available"}

        page_id = search_results[0]["pageid"]
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
        response = requests.get(WIKI_API, params=page_params, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", [])
        if not pages:
            return {"images": [], "text": "No description available"}

        page = pages[0]
        text = trim_text_by_sentences(page.get("extract", "No description available"))

        image_urls = []
        image_titles = [img["title"] for img in page.get("images", [])[:14] if "title" in img]
        if image_titles:
            image_params = {
                "action": "query",
                "prop": "imageinfo",
                "format": "json",
                "iiprop": "url",
                "titles": "|".join(image_titles),
                "utf8": 1,
                "formatversion": 2,
            }
            response = requests.get(WIKI_API, params=image_params, headers=REQUEST_HEADERS, timeout=10)
            response.raise_for_status()
            img_pages = response.json().get("query", {}).get("pages", [])
            for img_page in img_pages:
                image_info = img_page.get("imageinfo", [])
                if not image_info:
                    continue
                img_url = image_info[0].get("url", "")
                if img_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    image_urls.append(img_url)

        return {"images": image_urls[:8], "text": text or "No description available"}
    except Exception as error:
        print(f"Wikipedia info error: {error}")
        return {"images": [], "text": "No description available"}


def build_osm_embed_url(latitude, longitude):
    delta = 2.5
    left = longitude - delta
    right = longitude + delta
    top = latitude + delta
    bottom = latitude - delta
    marker = f"{latitude},{longitude}"
    return (
        f"https://www.openstreetmap.org/export/embed.html?bbox={left}%2C{bottom}%2C{right}%2C{top}"
        f"&layer=mapnik&marker={marker}"
    )


@lru_cache(maxsize=256)
def get_country_profile(country_code):
    fallback = {
        "flag": "",
        "capital": "Unknown",
        "region": "Unknown",
        "population": "Unknown",
        "currencies": "Unknown",
        "languages": "Unknown",
        "languages_detail": [],
        "map_url": "",
        "map_embed_url": "",
        "latitude": None,
        "longitude": None,
    }
    try:
        fields = "name,capital,region,subregion,population,currencies,languages,flags,maps,capitalInfo,latlng"
        response = requests.get(
            f"{REST_COUNTRIES_API}/{country_code}",
            params={"fields": fields},
            headers=REQUEST_HEADERS,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        country_data = data[0] if isinstance(data, list) and data else data
        if not country_data:
            return fallback

        currencies = ", ".join(
            f"{entry.get('name', code)} ({entry.get('symbol', code) or code})"
            for code, entry in country_data.get("currencies", {}).items()
        )
        language_map = country_data.get("languages", {})
        languages_detail = [{"code": code, "name": name} for code, name in language_map.items()]
        languages = ", ".join(language_map.values())
        capital = ", ".join(country_data.get("capital", [])) or "Unknown"

        coords = country_data.get("capitalInfo", {}).get("latlng", []) or country_data.get("latlng", [])
        latitude = coords[0] if len(coords) >= 2 else None
        longitude = coords[1] if len(coords) >= 2 else None
        map_embed_url = build_osm_embed_url(latitude, longitude) if latitude is not None else ""

        return {
            "flag": country_data.get("flags", {}).get("svg") or country_data.get("flags", {}).get("png", ""),
            "capital": capital,
            "region": " / ".join(
                [part for part in [country_data.get("region"), country_data.get("subregion")] if part]
            )
            or "Unknown",
            "population": f"{country_data.get('population', 0):,}" if country_data.get("population") else "Unknown",
            "currencies": currencies or "Unknown",
            "languages": languages or "Unknown",
            "languages_detail": languages_detail,
            "map_url": country_data.get("maps", {}).get("googleMaps", ""),
            "map_embed_url": map_embed_url,
            "latitude": latitude,
            "longitude": longitude,
        }
    except Exception as error:
        print(f"Country profile lookup error: {error}")
        return fallback


@lru_cache(maxsize=256)
def get_weather_snapshot(latitude, longitude):
    fallback = {
        "temperature_c": "Unknown",
        "feels_like_c": "Unknown",
        "wind_kph": "Unknown",
        "precip_mm": "Unknown",
        "condition": "Unknown",
        "patio_score": 50,
        "patio_label": "Data unavailable",
    }
    if latitude is None or longitude is None:
        return fallback

    try:
        params = {
            "latitude": f"{latitude:.4f}",
            "longitude": f"{longitude:.4f}",
            "current": "temperature_2m,apparent_temperature,wind_speed_10m,precipitation,weather_code",
            "timezone": "auto",
        }
        response = requests.get(OPEN_METEO_API, params=params, headers=REQUEST_HEADERS, timeout=10)
        response.raise_for_status()
        current = response.json().get("current", {})
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        wind = current.get("wind_speed_10m")
        precip = current.get("precipitation")
        weather_code = current.get("weather_code", -1)

        if temp is None or wind is None or precip is None:
            return fallback

        score = 65
        score -= min(abs(temp - 22) * 2.5, 35)
        if wind <= 15:
            score += 10
        elif wind >= 28:
            score -= 15

        if precip == 0:
            score += 10
        elif precip >= 1.5:
            score -= 20

        if weather_code in {45, 48, 67, 75, 82, 86, 95, 96, 99}:
            score -= 18
        score = max(0, min(int(round(score)), 100))

        if score >= 80:
            patio_label = "Patio paradise"
        elif score >= 60:
            patio_label = "Patio possible"
        elif score >= 40:
            patio_label = "Indoor with windows"
        else:
            patio_label = "Take it inside"

        return {
            "temperature_c": f"{temp:.1f}",
            "feels_like_c": f"{feels:.1f}" if feels is not None else "Unknown",
            "wind_kph": f"{wind:.1f}",
            "precip_mm": f"{precip:.1f}",
            "condition": WEATHER_CODE_LABELS.get(weather_code, "Variable weather"),
            "patio_score": score,
            "patio_label": patio_label,
        }
    except Exception as error:
        print(f"Weather lookup error: {error}")
        return fallback


def get_local_cheers(language_details):
    for language in language_details:
        cheers_data = CHEERS_BY_LANGUAGE.get(language["code"])
        if cheers_data:
            return {
                "phrase": cheers_data["phrase"],
                "pronunciation": cheers_data["pronunciation"],
                "language_name": language["name"],
            }
    return {"phrase": "Cheers!", "pronunciation": "cheerz", "language_name": "local language"}


def build_fun_bits(country_name, local_time):
    seed = f"{country_name}-{local_time.strftime('%Y-%m-%d')}"
    toasts = [
        "Raise your glass to international time zones and poor life choices.",
        "Hydration reminder: water counts, but so does confidence.",
        "Today we honor diplomacy, daylight savings, and questionable playlists.",
        "A toast to being culturally informed while mildly buzzed.",
    ]
    missions = [
        "Happy-hour mission: learn how to say 'cheers' in a new language.",
        "Tourist mission: locate the country's weirdest festival and put it on your bucket list.",
        "Snack mission: pair your drink with something that is not chips for once.",
        "Trivia mission: text one friend the country of today's 5 PM spotlight.",
    ]
    playful_facts = [
        "Time is fake, but this countdown is very real.",
        "No need to book a flight. Your browser already traveled.",
        "Day drinking is just global awareness with better branding.",
        "Somewhere, a bartender just yelled, 'last call.'",
    ]
    return {
        "toast": pick_by_seed(toasts, f"{seed}-toast"),
        "mission": pick_by_seed(missions, f"{seed}-mission"),
        "playful_fact": pick_by_seed(playful_facts, f"{seed}-fact"),
    }


def build_nearby_spots(candidates, picked_index, count=4):
    spots = []
    if not candidates:
        return spots
    for jump in range(1, count + 1):
        idx = (picked_index + jump) % len(candidates)
        item = candidates[idx]
        spots.append(
            {
                "country": item["country"],
                "country_code": item["country_code"],
                "local_time": item["local_time"].strftime("%I:%M %p"),
                "minutes_from_five": item["minutes_from_five"],
                "spin": idx,
            }
        )
    return spots


def build_page_context(spin_index=0):
    chosen, candidates, picked_index = pick_candidate(spin_index)
    if not chosen:
        return {}

    country = chosen["country"]
    country_code = chosen["country_code"]
    profile = get_country_profile(country_code)
    national_drink = get_national_liquor(country)

    wiki_query = f"{country} landmarks culture"
    wiki_info = get_wikipedia_info(wiki_query)
    if not wiki_info["images"] and national_drink != NO_DRINK_TEXT:
        wiki_info = get_wikipedia_info(national_drink)

    weather = get_weather_snapshot(profile["latitude"], profile["longitude"])
    cheers = get_local_cheers(profile["languages_detail"])
    fun_bits = build_fun_bits(country, chosen["local_time"])
    is_weekend = chosen["local_time"].weekday() >= 5
    nearby_spots = build_nearby_spots(candidates, picked_index)

    return {
        "country": country,
        "country_code": country_code,
        "local_time": chosen["local_time"].strftime("%I:%M:%S %p"),
        "local_day": chosen["local_time"].strftime("%A, %B %d"),
        "timezone_name": chosen["timezone_name"],
        "minutes_from_five": chosen["minutes_from_five"],
        "seconds_to_next_five": chosen["seconds_to_next_five"],
        "is_exactly_five": chosen["is_exactly_five"],
        "is_weekend": is_weekend,
        "national_drink": national_drink,
        "country_profile": profile,
        "weather": weather,
        "cheers": cheers,
        "links": wiki_info["images"],
        "message": wiki_info["text"],
        "toast": fun_bits["toast"],
        "mission": fun_bits["mission"],
        "playful_fact": fun_bits["playful_fact"],
        "spin_index": picked_index,
        "next_spin_index": picked_index + 1,
        "nearby_spots": nearby_spots,
    }


@app.route("/")
@app.route("/5")
def five_pm():
    spin_param = request.args.get("spin", "0")
    try:
        spin_index = int(spin_param)
    except ValueError:
        spin_index = 0
    return render_template("5.html", **build_page_context(spin_index))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
