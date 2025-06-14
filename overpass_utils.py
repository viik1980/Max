import aiohttp
import logging

async def query_overpass(lat, lon, radius=10000):
    query = f"""
    [out:json][timeout:25];
    (
      node["shop"](around:{radius},{lat},{lon});
      node["amenity"="pharmacy"](around:{radius},{lat},{lon});
      node["amenity"="toilets"](around:{radius},{lat},{lon});
      node["amenity"="shower"](around:{radius},{lat},{lon});
      node["amenity"="fuel"](around:{radius},{lat},{lon});
      node["amenity"="parking"](around:{radius},{lat},{lon});
    );
    out body;
    >;
    out skel qt;
    """
    url = "https://overpass-api.de/api/interpreter"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data={"data": query}) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logging.error(f"Overpass статус {resp.status}")
                    return None
    except Exception as e:
        logging.error(f"Ошибка Overpass: {e}")
        return None

def parse_places(data):
    places = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name", "Без названия")
        type_ = tags.get("shop") or tags.get("amenity")
        lat = element.get("lat")
        lon = element.get("lon")
        if type_ and lat and lon:
            places.append(f"📍 {type_.capitalize()}: {name}\n➡️ Координаты: {lat:.4f}, {lon:.4f}")
    return places[:10]
