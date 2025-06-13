
import requests
import math

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(d_lambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def find_nearby_places(lat, lon, tag_type="amenity", tag_value="shower", radius=5000):
    query = f"""
    [out:json][timeout:25];
    (
      node["{tag_type}"="{tag_value}"](around:{radius},{lat},{lon});
      way["{tag_type}"="{tag_value}"](around:{radius},{lat},{lon});
      relation["{tag_type}"="{tag_value}"](around:{radius},{lat},{lon});
    );
    out center;
    """
    url = "https://overpass.kumi.systems/api/interpreter"
    try:
        response = requests.post(url, data={"data": query})
        data = response.json()
        results = []
        for el in data["elements"]:
            lat2 = el.get("lat") or el.get("center", {}).get("lat")
            lon2 = el.get("lon") or el.get("center", {}).get("lon")
            if lat2 and lon2:
                el["dist"] = haversine(lat, lon, lat2, lon2)
                results.append(el)
        results.sort(key=lambda x: x["dist"])
        return results
    except Exception as e:
        print(f"Ошибка Overpass: {e}")
        return []
