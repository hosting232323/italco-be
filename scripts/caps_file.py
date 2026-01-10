import json
import time
import requests

# =========================
# CONFIGURAZIONE
# =========================
GOOGLE_API_KEY = "XXX"
INPUT_FILE = "assets/caps.json"
OUTPUT_FILE = "output.json"
COUNTRY = "Italy"

# =========================
# FUNZIONE GEOCODING
# =========================
def geocode_cap(cap):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "components": f"postal_code:{cap}|country:IT",
        "language": "it",
        "key": GOOGLE_API_KEY
    }

    response = requests.get(url, params=params)
    data = response.json()

    if data["status"] != "OK":
        return None

    result = data["results"][0]

    city_name = None
    for component in result["address_components"]:
        types = component["types"]

        if (
            "locality" in types or
            "postal_town" in types or
            "administrative_area_level_3" in types or
            "administrative_area_level_2" in types
        ):
            city_name = component["long_name"]
            break

    location = result["geometry"]["location"]

    return {
        "name": city_name,
        "lat": location["lat"],
        "lon": location["lng"]
    }


# =========================
# MAIN
# =========================
def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        cap_data = json.load(f)

    output = {}

    for province, caps in cap_data.items():
        output[province] = {}

        for cap in caps:
            print(f"Geocoding {cap} ({province})...")
            geo = geocode_cap(cap)
            print(geo)

            if geo:
                output[province][cap] = geo
            else:
                print(f"⚠️ Errore per CAP {cap}")

            # per evitare limiti API
            time.sleep(0.2)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("✅ File JSON generato con successo")

if __name__ == "__main__":
    main()
