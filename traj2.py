import json
import geopandas as gpd
from shapely.geometry import Point, LineString
import folium
import numpy as np

# Load Google Takeout location history JSON file
file_path = '/Users/rx/Downloads/location-history.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
coords = []
timestamps = []

import datetime

def format_date(input_date):
    return datetime.datetime.strptime(input_date, "%y%m%d")

# Ask user whether to filter by date
filter_choice = input("Do you want to filter by date? (y/n): ").lower()

if filter_choice == 'y':
    start_input = input("Enter start date (yymmdd): ")
    end_input = input("Enter end date (yymmdd), or 'n' for indefinite: ")

    start_dt = format_date(start_input)
    end_dt = format_date(end_input) if end_input.lower() != 'n' else None

    def date_within_range(ts):
        ts_dt = datetime.datetime.fromisoformat(ts.rstrip('Z'))
        if end_dt:
            return start_dt <= ts_dt <= end_dt
        else:
            return ts_dt >= start_dt
else:
    def date_within_range(ts):
        return True  # No filtering


def extract_coordinates_from_point(point_str):
    lat, lon = map(float, point_str.replace('geo:', '').split(','))
    return lat, lon

for entry in data:
    if 'locations' in entry:
        locations = entry['locations']
        for location in locations:
            if 'latitudeE7' in location and 'longitudeE7' in location:
                latitude = location['latitudeE7'] / 1e7
                longitude = location['longitudeE7'] / 1e7
                timestamp = location['timestamp']
                if date_within_range(timestamp):
                    coords.append((latitude, longitude))
                    timestamps.append(timestamp)
    elif 'timelinePath' in entry:
        entry_time = entry['startTime']
        if date_within_range(entry_time):
            for point in entry['timelinePath']:
                lat, lon = extract_coordinates_from_point(point['point'])
                coords.append((lat, lon))
                timestamps.append(entry_time)


# Convert coordinates to NumPy array
coords_array = np.array(coords)

# Vectorized Haversine formula
def haversine_vectorized(lat1, lon1, lat2, lon2):
    R = 6371.0  # Earth's radius in km
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat / 2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

    return R * c

# Calculate distances
lat1, lon1 = coords_array[:-1, 0], coords_array[:-1, 1]
lat2, lon2 = coords_array[1:, 0], coords_array[1:, 1]

distances = haversine_vectorized(lat1, lon1, lat2, lon2)

# Apply distance threshold filtering
threshold = 50  # km
mask = distances <= threshold
mask = np.insert(mask, 0, True)

filtered_coords = np.where(mask[:, None], coords_array, [np.nan, np.nan])
filtered_timestamps = np.where(mask, timestamps, None)

# Create LineStrings from filtered segments
segments = []
current_segment = []

for coord in filtered_coords:
    if np.isnan(coord).any():
        if len(current_segment) > 1:
            segments.append(LineString(current_segment))
        current_segment = []
    else:
        current_segment.append(Point(coord[1], coord[0]))

if len(current_segment) > 1:
    segments.append(LineString(current_segment))

trajectory_gdf_filtered = gpd.GeoDataFrame({'geometry': segments}, crs="EPSG:4326")

# Calculate centroid for visualization
trajectory_union = trajectory_gdf_filtered.unary_union
centroid = trajectory_union.centroid

# Create folium map
m = folium.Map(location=[centroid.y, centroid.x], zoom_start=6)

# Add trajectory segments to the map
for segment in segments:
    folium.GeoJson(segment).add_to(m)

# Save and display map
m.save('filtered_trajector_unfilteredMAR31.html')
m
