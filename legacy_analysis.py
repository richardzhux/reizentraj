"""
Legacy exploratory script retained for reference.

The logic inside this file reflects earlier ad-hoc analyses and is no longer
maintained. Prefer `trajectory.py` for the supported command-line workflow.
"""

import json
import geopandas as gpd
from shapely.geometry import Point, LineString
import folium

# Load Google Takeout location history JSON file
file_path = '/Users/rx/Downloads/location-history 2.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
coords = []
timestamps = []

def extract_coordinates_from_point(point_str):
    lat, lon = map(float, point_str.replace('geo:', '').split(','))
    return lat, lon

for entry in data:
    if 'locations' in entry:  # Old format
        locations = entry['locations']
        for location in locations:
            if 'latitudeE7' in location and 'longitudeE7' in location:
                latitude = location['latitudeE7'] / 1e7
                longitude = location['longitudeE7'] / 1e7
                timestamp = location['timestamp']
                coords.append((latitude, longitude))
                timestamps.append(timestamp)
    elif 'timelinePath' in entry:  # New format
        for point in entry['timelinePath']:
            lat, lon = extract_coordinates_from_point(point['point'])
            timestamp = entry['startTime']  # Use the start time for simplicity
            coords.append((lat, lon))
            timestamps.append(timestamp)

# NORMAL MAP SECTOR

# Create GeoDataFrame
gdf = gpd.GeoDataFrame({
    'timestamp': timestamps,
    'geometry': [Point(lon, lat) for lat, lon in coords]
}, crs="EPSG:4326")

# Create LineString from points
line = LineString(gdf['geometry'].values)

# Create a GeoDataFrame for the trajectory
trajectory_gdf = gpd.GeoDataFrame({'geometry': [line]}, crs="EPSG:4326")

# Re-project to a projected CRS (e.g., UTM)
trajectory_gdf_projected = trajectory_gdf.to_crs(epsg=32633)  # UTM zone 33N, adjust as needed

# Calculate the centroid in the projected CRS
centroid_projected = trajectory_gdf_projected.geometry.centroid.iloc[0]

# Convert the centroid back to the geographic CRS
centroid = gpd.GeoSeries([centroid_projected], crs="EPSG:32633").to_crs(epsg=4326).iloc[0]

# Plot the trajectory on a map using folium
def plot_trajectory(trajectory_gdf, centroid):
    # Create a folium map centered at the centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=6)

    # Add the trajectory to the map
    folium.GeoJson(trajectory_gdf).add_to(m)

    # Save the map to an HTML file and display it
    m.save('trajectory.html')
    return m

# Plot and display the map
map_ = plot_trajectory(trajectory_gdf, centroid)
map_




# HEATMAP SECTOR

from folium.plugins import HeatMap

# Create a folium map centered at the first coordinate
heatmap_map = folium.Map(location=[coords[0][0], coords[0][1]], zoom_start=6)

# Add heatmap layer
HeatMap(coords).add_to(heatmap_map)

# Save to HTML and display
heatmap_map.save('heatmap.html')
heatmap_map



"""
# STATES VISITED SECTOR may not work now?

from datetime import datetime

# Load the shapefiles for countries and states
# Adjust these paths to where your shapefiles are stored
states_gdf = gpd.read_file("/Users/rpigzhux/Downloads/States/ne_110m_admin_1_states_provinces.shp")
countries_gdf = gpd.read_file("/Users/rpigzhux/Downloads/Countries/ne_110m_admin_0_countries.shp")

# Function to parse the timestamp from Google Takeout format
def parse_timestamp(ts):
    try:
        return datetime.utcfromtimestamp(int(ts) / 1000)
    except:
        return datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S.%fZ')

# Function to reverse geocode using local shapefiles
def get_local_geocode(lat, lon, countries_gdf, states_gdf):
    point = Point(lon, lat)  # Create a Shapely point

    # Find the country containing the point
    country = countries_gdf[countries_gdf.contains(point)]
    country_name = country['NAME'].values[0] if not country.empty else 'Unknown'

    # Find the state containing the point
    state = states_gdf[states_gdf.contains(point)]
    state_name = state['NAME'].values[0] if not state.empty else 'Unknown'

    print(f"Geocoded: Lat {lat}, Lon {lon} -> State: {state_name}, Country: {country_name}")
    return state_name, country_name

# Load Google Takeout location history JSON file
file_path = '/Users/rpigzhux/Downloads/location-history 3.json'  # Adjust this path to your JSON file
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
coords = []
timestamps = []

for entry in data:
    if 'locations' in entry:  # Old format
        locations = entry['locations']
        for location in locations:
            if 'latitudeE7' in location and 'longitudeE7' in location:
                latitude = location['latitudeE7'] / 1e7
                longitude = location['longitudeE7'] / 1e7
                timestamp = parse_timestamp(location['timestampMs'])
                coords.append((latitude, longitude))
                timestamps.append(timestamp)

# Dictionaries to store first visits to states and countries
visited_states = {}
visited_countries = {}

# Analyze locations to track first state and country visits
for i, (lat, lon) in enumerate(coords):
    timestamp = timestamps[i]
    state, country = get_local_geocode(lat, lon, countries_gdf, states_gdf)
    
    # Track first visit to states
    if state != 'Unknown' and state not in visited_states:
        visited_states[state] = timestamp.strftime('%Y-%m-%d')

    # Track first visit to countries
    if country != 'Unknown' and country not in visited_countries:
        visited_countries[country] = timestamp.strftime('%Y-%m-%d')

# Sort visited states and countries by timestamp
sorted_states = sorted(visited_states.items(), key=lambda x: x[1])
sorted_countries = sorted(visited_countries.items(), key=lambda x: x[1])

# Constants for the percentage calculation
TOTAL_STATES = 50  # Total number of US states
TOTAL_COUNTRIES = 195  # Approximate number of countries in the world

# Calculate percentages
states_visited_count = len(sorted_states)
countries_visited_count = len(sorted_countries)
states_percentage = (states_visited_count / TOTAL_STATES) * 100
countries_percentage = (countries_visited_count / TOTAL_COUNTRIES) * 100

# Display results
print("States visited:")
for state, date in sorted_states:
    print(f"{date} {state}")

print(f"\n{states_visited_count}/{TOTAL_STATES}, {states_percentage:.2f}% states visited.\n")

print("Countries visited:")
for country, date in sorted_countries:
    print(f"{date} {country}")

print(f"\n{countries_visited_count}/{TOTAL_COUNTRIES}, {countries_percentage:.2f}% countries visited.")






# DISTANCE TRAVELED SECTOR

import json
from geopy.distance import geodesic

def haversine(coord1, coord2):
    return geodesic(coord1, coord2).kilometers

def calculate_total_distance(locations):
    total_distance = 0.0
    previous_location = None

    for location in locations:
        if previous_location:
            distance = haversine(previous_location, location)
            total_distance += distance
        previous_location = location

    return total_distance

# Load Google Takeout location history JSON file
file_path = '/Users/rpigzhux/Desktop/Takeout/Location History (Timeline)/Records.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
locations = data['locations']

# Prepare a list of tuples with (latitude, longitude)
coords = []
for loc in locations:
    try:
        latitude = loc['latitudeE7'] / 1e7
        longitude = loc['longitudeE7'] / 1e7
        coords.append((latitude, longitude))
    except KeyError:
        # Skip entries that do not have latitude or longitude
        continue

# Calculate total distance traveled
total_distance = calculate_total_distance(coords)

print(f"Total distance traveled: {total_distance:.2f} kilometers")




# MONTHLY TRAVEL DISTANCE SECTOR
import json
from geopy.distance import geodesic
from datetime import datetime

def haversine(coord1, coord2):
    return geodesic(coord1, coord2).kilometers

def calculate_distances_by_month(locations):
    distances_by_month = {}
    previous_location = None
    previous_timestamp = None

    for location in locations:
        if 'latitudeE7' in location and 'longitudeE7' in location:
            latitude = location['latitudeE7'] / 1e7
            longitude = location['longitudeE7'] / 1e7
            current_location = (latitude, longitude)
            timestamp = datetime.fromisoformat(location['timestamp'][:-1])  # Remove 'Z' and parse

            if previous_location and previous_timestamp:
                distance = haversine(previous_location, current_location)
                month = timestamp.strftime('%Y-%m')

                if month not in distances_by_month:
                    distances_by_month[month] = 0.0

                distances_by_month[month] += distance

            previous_location = current_location
            previous_timestamp = timestamp

    return distances_by_month

def categorize_distance_by_speed(locations):
    categorized_distances = {'walking': 0.0, 'driving': 0.0, 'flying': 0.0}
    previous_location = None
    previous_timestamp = None

    for location in locations:
        if 'latitudeE7' in location and 'longitudeE7' in location:
            latitude = location['latitudeE7'] / 1e7
            longitude = location['longitudeE7'] / 1e7
            current_location = (latitude, longitude)
            timestamp = datetime.fromisoformat(location['timestamp'][:-1])  # Remove 'Z' and parse

            if previous_location and previous_timestamp:
                distance = haversine(previous_location, current_location)
                time_diff = (timestamp - previous_timestamp).total_seconds() / 3600.0  # in hours
                if time_diff > 0:
                    speed = distance / time_diff  # km/h

                    if speed < 6:
                        categorized_distances['walking'] += distance
                    elif speed < 140:
                        categorized_distances['driving'] += distance
                    else:
                        categorized_distances['flying'] += distance

            previous_location = current_location
            previous_timestamp = timestamp

    return categorized_distances

# Load Google Takeout location history JSON file
file_path = '/Users/rpigzhux/Desktop/Takeout/Location History (Timeline)/Records.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
locations = data['locations']

# Calculate monthly distances
distances_by_month = calculate_distances_by_month(locations)
print("Distances traveled each month:")
for month, distance in distances_by_month.items():
    print(f"{month}: {distance:.2f} kilometers")

# Categorize distances by speed
categorized_distances = categorize_distance_by_speed(locations)
print("\nDistances categorized by activity type:")
for category, distance in categorized_distances.items():
    print(f"{category.capitalize()}: {distance:.2f} kilometers")

from collections import defaultdict

def calculate_distances_by_month_and_category(locations):
    distances_by_month_and_category = defaultdict(lambda: {'walking': 0.0, 'driving': 0.0, 'flying': 0.0})
    previous_location = None
    previous_timestamp = None

    for location in locations:
        if 'latitudeE7' in location and 'longitudeE7' in location:
            latitude = location['latitudeE7'] / 1e7
            longitude = location['longitudeE7'] / 1e7
            current_location = (latitude, longitude)
            timestamp = datetime.fromisoformat(location['timestamp'][:-1])  # Remove 'Z' and parse

            if previous_location and previous_timestamp:
                distance = haversine(previous_location, current_location)
                time_diff = (timestamp - previous_timestamp).total_seconds() / 3600.0  # in hours
                if time_diff > 0:
                    speed = distance / time_diff  # km/h

                    month = timestamp.strftime('%Y-%m')
                    if speed < 5:
                        distances_by_month_and_category[month]['walking'] += distance
                    elif speed < 140:
                        distances_by_month_and_category[month]['driving'] += distance
                    else:
                        distances_by_month_and_category[month]['flying'] += distance

            previous_location = current_location
            previous_timestamp = timestamp

    return distances_by_month_and_category

# Categorize distances by speed for each month
distances_by_month_and_category = calculate_distances_by_month_and_category(locations)
print("\nDistances categorized by activity type and month:")
for month, categories in distances_by_month_and_category.items():
    print(f"{month}:")
    for category, distance in categories.items():
        print(f"  {category.capitalize()}: {distance:.2f} kilometers")




# VISITED STATES BY CHRONOLOGICAL ORDER SECTOR

import json
import geopandas as gpd
from shapely.geometry import Point
from datetime import datetime, timedelta

# Load the shapefile for states and provinces
states_gdf = gpd.read_file('/Users/rpigzhux/Desktop/ne_110m_admin_1_states_provinces/ne_110m_admin_1_states_provinces.shp')

def get_state(lat, lon, states_gdf):
    point = Point(lon, lat)
    state = 'Unknown'
    
    # Find the state
    for idx, row in states_gdf.iterrows():
        if row['geometry'].contains(point):
            state = row['name']  # Adjust based on the attribute name in your shapefile
            break
    
    return state

def calculate_speed(lat1, lon1, time1, lat2, lon2, time2):
    point1 = Point(lon1, lat1)
    point2 = Point(lon2, lat2)
    distance = point1.distance(point2) * 111  # Convert degrees to kilometers (approximation)
    time_diff = (time2 - time1).total_seconds() / 3600  # Convert time difference to hours
    if time_diff == 0:
        return 0
    speed = distance / time_diff  # Speed in km/h
    return speed

# Load Google Takeout location history JSON file
file_path = '/Users/rpigzhux/Desktop/Takeout/Location History (Timeline)/Records.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
locations = data['locations']

# Sort locations by timestamp
locations.sort(key=lambda x: x['timestamp'])

# Find states
visited_states = {}
previous_location = None
previous_time = None
for location in locations:
    if 'latitudeE7' in location and 'longitudeE7' in location:
        latitude = location['latitudeE7'] / 1e7
        longitude = location['longitudeE7'] / 1e7
        timestamp = datetime.fromisoformat(location['timestamp'][:-1])  # Remove 'Z' and parse
        
        if previous_location is not None and previous_time is not None:
            speed = calculate_speed(previous_location[0], previous_location[1], previous_time, latitude, longitude, timestamp)
            if speed < 300:  # Consider non-flight if speed is less than 300 km/h
                state = get_state(latitude, longitude, states_gdf)
                if state != 'Unknown' and state not in visited_states:
                    visited_states[state] = timestamp.strftime('%Y-%m-%d %H:%M')
        
        previous_location = (latitude, longitude)
        previous_time = timestamp

# Sort visited states by timestamp
sorted_states = sorted(visited_states.items(), key=lambda x: x[1])

# Print visited states
print("\nVisited states in order of first non-flight visit:")
for state, timestamp in sorted_states:
    print(f"{timestamp}: {state}")
print("\nNote: All timestamps are in UTC.")



# COARSE TRAJ SECTOR (NEW TIMELINE FORMAT since 2024 Summer?)

import json
import geopandas as gpd
from shapely.geometry import Point, LineString
import folium

# Load the shapefile for states and provinces (adjust the path as needed)
states_gdf = gpd.read_file('/Users/rpigzhux/Desktop/Imperial Archive/ne_110m_admin_1_states_provinces/ne_110m_admin_1_states_provinces.shp')

def get_state(lat, lon, states_gdf):
    point = Point(lon, lat)
    state = 'Unknown'
    
    # Find the state
    for idx, row in states_gdf.iterrows():
        if row['geometry'].contains(point):
            state = row['name']  # Adjust based on the attribute name in your shapefile
            break
    
    return state

# Load Google Takeout location history JSON file
file_path = '/Users/rpigzhux/Downloads/location-history.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
locations = data  # Assuming the JSON root is a list of entries

# Extract coordinates and timestamps
coords = []
timestamps = []
for entry in locations:
    if 'visit' in entry and 'topCandidate' in entry['visit']:
        location_str = entry['visit']['topCandidate']['placeLocation']
        lat, lon = map(float, location_str.replace('geo:', '').split(','))
        timestamp = entry['startTime']  # Store the start time
        coords.append((lat, lon))
        timestamps.append(timestamp)

# Create GeoDataFrame
gdf = gpd.GeoDataFrame({
    'timestamp': timestamps,
    'geometry': [Point(lon, lat) for lat, lon in coords]
}, crs="EPSG:4326")

# Create LineString from points
line = LineString(gdf['geometry'].values)

# Create a GeoDataFrame for the trajectory
trajectory_gdf = gpd.GeoDataFrame({'geometry': [line]}, crs="EPSG:4326")

# Re-project to a projected CRS (e.g., UTM)
trajectory_gdf_projected = trajectory_gdf.to_crs(epsg=32633)  # UTM zone 33N, adjust as needed

# Calculate the centroid in the projected CRS
centroid_projected = trajectory_gdf_projected.geometry.centroid.iloc[0]

# Convert the centroid back to the geographic CRS
centroid = gpd.GeoSeries([centroid_projected], crs="EPSG:32633").to_crs(epsg=4326).iloc[0]

# Plot the trajectory on a map using folium
def plot_trajectory(trajectory_gdf, centroid):
    # Create a folium map centered at the centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=6)

    # Add the trajectory to the map
    folium.GeoJson(trajectory_gdf).add_to(m)

    # Save the map to an HTML file and display it
    m.save('trajectory.html')
    return m

# Plot and display the map
map_ = plot_trajectory(trajectory_gdf, centroid)
map_





# HIGH ACCURACY SECTOR (NEW FORMAT 2024 SOMER)

import json
import geopandas as gpd
from shapely.geometry import Point, LineString
import folium

# Load the shapefile for states and provinces (adjust the path as needed)
states_gdf = gpd.read_file('/Users/rpigzhux/Desktop/Imperial Archive/ne_110m_admin_1_states_provinces/ne_110m_admin_1_states_provinces.shp')

def get_state(lat, lon, states_gdf):
    point = Point(lon, lat)
    state = 'Unknown'
    
    # Find the state
    for idx, row in states_gdf.iterrows():
        if row['geometry'].contains(point):
            state = row['name']  # Adjust based on the attribute name in your shapefile
            break
    
    return state

# Load Google Takeout location history JSON file
file_path = '/Users/rpigzhux/Downloads/location-history.json'
with open(file_path, 'r') as file:
    data = json.load(file)

# Extract location data
coords = []
timestamps = []

def extract_coordinates_from_point(point_str):
    lat, lon = map(float, point_str.replace('geo:', '').split(','))
    return lat, lon

for entry in data:
    if 'locations' in entry:  # Old format
        locations = entry['locations']
        for location in locations:
            if 'latitudeE7' in location and 'longitudeE7' in location:
                latitude = location['latitudeE7'] / 1e7
                longitude = location['longitudeE7'] / 1e7
                timestamp = location['timestamp']
                coords.append((latitude, longitude))
                timestamps.append(timestamp)
    elif 'timelinePath' in entry:  # New format
        for point in entry['timelinePath']:
            lat, lon = extract_coordinates_from_point(point['point'])
            timestamp = entry['startTime']  # Use the start time for simplicity
            coords.append((lat, lon))
            timestamps.append(timestamp)

# Create GeoDataFrame
gdf = gpd.GeoDataFrame({
    'timestamp': timestamps,
    'geometry': [Point(lon, lat) for lat, lon in coords]
}, crs="EPSG:4326")

# Create LineString from points
line = LineString(gdf['geometry'].values)

# Create a GeoDataFrame for the trajectory
trajectory_gdf = gpd.GeoDataFrame({'geometry': [line]}, crs="EPSG:4326")

# Re-project to a projected CRS (e.g., UTM)
trajectory_gdf_projected = trajectory_gdf.to_crs(epsg=32633)  # UTM zone 33N, adjust as needed

# Calculate the centroid in the projected CRS
centroid_projected = trajectory_gdf_projected.geometry.centroid.iloc[0]

# Convert the centroid back to the geographic CRS
centroid = gpd.GeoSeries([centroid_projected], crs="EPSG:32633").to_crs(epsg=4326).iloc[0]

# Plot the trajectory on a map using folium
def plot_trajectory(trajectory_gdf, centroid):
    # Create a folium map centered at the centroid
    m = folium.Map(location=[centroid.y, centroid.x], zoom_start=6)

    # Add the trajectory to the map
    folium.GeoJson(trajectory_gdf).add_to(m)

    # Save the map to an HTML file and display it
    m.save('trajectory.html')
    return m

# Plot and display the map
map_ = plot_trajectory(trajectory_gdf, centroid)
map_
"""
