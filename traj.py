import json
import geopandas as gpd
from shapely.geometry import Point, LineString
import folium

# Load Google Takeout location history JSON file
file_path = '/Users/rx/Downloads/location-history.json'
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