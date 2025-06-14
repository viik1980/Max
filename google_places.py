import os
import aiohttp
from dotenv import load_dotenv

load_dotenv()
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

async def find_nearby_places(lat, lon, place_type="park", radius=5000):
    url = (
        f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?"
        f"location={lat},{lon}&radius={radius}&type={place_type}&key={GOOGLE_MAPS_API_KEY}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            results = data.get("results", [])
            return [
                {
                    "name": r.get("name"),
                    "address": r.get("vicinity"),
                    "rating": r.get("rating", "–"),
                    "lat": r["geometry"]["location"]["lat"],
                    "lon": r["geometry"]["location"]["lng"]
                }
                for r in results[:5]
            ]
