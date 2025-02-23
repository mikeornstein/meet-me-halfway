import streamlit as st

st.title("🎈🎈🎈 My new app")
st.write(
    "Let's start building! For help and inspiration, head over to [docs.streamlit.io](https://docs.streamlit.io/)."
)


import streamlit as st
import requests
from shapely.geometry import shape, Point
import folium
from streamlit_folium import st_folium
import geopy.distance

# API keys (use Streamlit secrets)
ORS_API_KEY = st.secrets["ORS_API_KEY"]
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]

# Place type mapping for user-friendly categories to Google Maps place types
PLACE_TYPE_MAPPING = {
    "Eat": ["restaurant", "cafe", "bakery"],
    "Drink": ["bar", "pub", "night_club"],
    "Coffee": ["cafe"],
    "Walk Outside": ["park"],
    "Shop": ["shopping_mall", "department_store", "supermarket"],
}

# Helper functions

def geocode(address):
    """
    Convert an address to coordinates [longitude, latitude] using OpenRouteService.
    """
    url = f"https://api.openrouteservice.org/geocode/search?api_key={ORS_API_KEY}&text={address}"
    response = requests.get(url)
    data = response.json()
    if data["features"]:
        return data["features"][0]["geometry"]["coordinates"]  # [lng, lat]
    else:
        return None

def get_isochrone(location, mode, time):
    """
    Get the isochrone (reachable area within time) for a location using OpenRouteService.
    - location: [longitude, latitude]
    - mode: "Driving" or "Walking"
    - time: Maximum travel time in minutes
    """
    profile = "driving-car" if mode == "Driving" else "foot-walking"
    url = f"https://api.openrouteservice.org/v2/isochrones/{profile}/json"
    body = {
        "locations": [location],
        "range": [time * 60],  # time in seconds
    }
    headers = {"Authorization": ORS_API_KEY}
    response = requests.post(url, json=body, headers=headers)
    return response.json()

def get_intersection(geojson1, geojson2):
    """
    Find the intersection of two isochrones using Shapely.
    Returns GeoJSON of the intersection or None if no overlap.
    """
    poly1 = shape(geojson1["features"][0]["geometry"])
    poly2 = shape(geojson2["features"][0]["geometry"])
    intersection = poly1.intersection(poly2)
    if intersection.is_empty:
        return None
    else:
        return intersection.__geo_interface__  # GeoJSON

def get_bbox(geojson):
    """
    Get the bounding box [south, west, north, east] of a GeoJSON polygon.
    """
    poly = shape(geojson)
    minx, miny, maxx, maxy = poly.bounds
    return [miny, minx, maxy, maxx]  # [south, west, north, east]

def get_center_and_radius(bbox):
    """
    Calculate the center and radius (in meters) covering the bounding box.
    - bbox: [south, west, north, east]
    """
    sw = (bbox[0], bbox[1])
    ne = (bbox[2], bbox[3])
    center_lat = (sw[0] + ne[0]) / 2
    center_lng = (sw[1] + ne[1]) / 2
    center = (center_lat, center_lng)
    radius = geopy.distance.geodesic(center, sw).meters
    return center, radius

def search_places(center, radius, types):
    """
    Search for places of specified types within a radius using Google Maps Places API.
    - center: [latitude, longitude]
    - radius: Radius in meters
    - types: List of place types
    """
    url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location={center[0]},{center[1]}&radius={radius}&type={types[0]}&key={GOOGLE_API_KEY}"
    response = requests.get(url)
    return response.json()

def get_travel_times(sources, destinations, mode):
    """
    Calculate travel times from sources to destinations using OpenRouteService Matrix API.
    - sources: List of [longitude, latitude] for source locations
    - destinations: List of [longitude, latitude] for destination locations
    - mode: "Driving" or "Walking"
    """
    profile = "driving-car" if mode == "Driving" else "foot-walking"
    url = f"https://api.openrouteservice.org/v2/matrix/{profile}/json"
    body = {
        "locations": sources + destinations,
        "sources": [0, 1],
        "destinations": list(range(2, 2 + len(destinations))),
        "metrics": ["duration"],
    }
    headers = {"Authorization": ORS_API_KEY}
    response = requests.post(url, json=body, headers=headers)
    data = response.json()
    return data["durations"]

# Streamlit UI
st.title("Meet Me Halfway")

# Input fields
location1 = st.text_input("Your location", placeholder="Enter your address")
location2 = st.text_input("Other party's location", placeholder="Enter the other party's address")
mode = st.selectbox("Transportation mode", ["Driving", "Walking"])
place_categories = st.multiselect("Type of place", ["Eat", "Drink", "Coffee", "Walk Outside", "Shop"], default=["Eat"])
max_time = st.slider("Maximum travel time (minutes)", 5, 60, 15)

if st.button("Find Meeting Places"):
    with st.spinner("Calculating..."):
        # Geocode locations
        loc1 = geocode(location1)
        loc2 = geocode(location2)
        if not loc1 or not loc2:
            st.error("Could not find one or both locations. Please check the addresses and try again.")
            st.stop()
        
        # Get isochrones
        iso1 = get_isochrone(loc1, mode, max_time)
        iso2 = get_isochrone(loc2, mode, max_time)
        
        # Get intersection of isochrones
        intersection = get_intersection(iso1, iso2)
        if not intersection:
            st.error("No overlapping area within the time limit. Try increasing the time or choosing different locations.")
            st.stop()
        
        # Get bounding box for place search
        bbox = get_bbox(intersection)
        center, radius = get_center_and_radius(bbox)
        
        # Get unique place types from selected categories
        place_types = set()
        for category in place_categories:
            place_types.update(PLACE_TYPE_MAPPING[category])
        place_types = list(place_types)
        
        # Search for places of each type
        places = []
        for type in place_types:
            response = search_places(center, radius, [type])
            places.extend(response.get("results", []))
        
        # Remove duplicates based on place_id
        places = {place["place_id"]: place for place in places}.values()
        
        # Filter places that lie within the intersection polygon
        intersection_poly = shape(intersection)
        filtered_places = [
            place for place in places
            if intersection_poly.contains(
                Point(place["geometry"]["location"]["lng"], place["geometry"]["location"]["lat"])
            )
        ]
        
        if not filtered_places:
            st.error("No places found within the overlapping area. Try selecting different place types or increasing the time.")
            st.stop()
        
        # Calculate travel times from both locations to each place
        sources = [loc1, loc2]
        destinations = [
            [place["geometry"]["location"]["lng"], place["geometry"]["location"]["lat"]]
            for place in filtered_places
        ]
        durations = get_travel_times(sources, destinations, mode)
        
        # Create a Folium map centered at the midpoint of the two locations
        m = folium.Map(location=[(loc1[1] + loc2[1])/2, (loc1[0] + loc2[0])/2], zoom_start=12)
        
        # Add isochrones to the map
        folium.GeoJson(iso1, name="Your Isochrone", style_function=lambda x: {"fillColor": "blue", "color": "blue", "fillOpacity": 0.3}).add_to(m)
        folium.GeoJson(iso2, name="Other's Isochrone", style_function=lambda x: {"fillColor": "red", "color": "red", "fillOpacity": 0.3}).add_to(m)
        folium.GeoJson(intersection, name="Intersection", style_function=lambda x: {"fillColor": "green", "color": "green", "fillOpacity": 0.5}).add_to(m)
        
        # Add markers for each place
        for place, dur1, dur2 in zip(filtered_places, durations[0], durations[1]):
            folium.Marker(
                location=[place["geometry"]["location"]["lat"], place["geometry"]["location"]["lng"]],
                popup=f"{place['name']}<br>Travel time: {dur1/60:.1f} min / {dur2/60:.1f} min",
                icon=folium.Icon(color="green")
            ).add_to(m)
        
        # Enable layer control for toggling isochrones and markers
        folium.LayerControl().add_to(m)
        
        # Display the map in Streamlit
        st_folium(m, width=700, height=500)
        
        # Display the list of places with details
        st.header("Meeting Place Options")
        for place, dur1, dur2 in zip(filtered_places, durations[0], durations[1]):
            st.subheader(place["name"])
            st.write(f"**Address:** {place['vicinity']}")
            st.write(f"**Travel time for you:** {dur1/60:.1f} minutes")
            st.write(f"**Travel time for other party:** {dur2/60:.1f} minutes")
            st.write(f"**Rating:** {place.get('rating', 'N/A')} ({place.get('user_ratings_total', 0)} reviews)")
            message = (
                f"Let's meet at {place['name']}, {place['vicinity']}. "
                f"It will take me {dur1/60:.1f} minutes and you {dur2/60:.1f} minutes to get there. "
                f"Check it out: https://www.google.com/maps/place/?q=place_id:{place['place_id']}"
            )
            st.write("**Shareable Message:**")
            st.write(message)