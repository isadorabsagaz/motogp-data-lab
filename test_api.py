from src.motogp_data_lab.api_client import get_seasons, get_events, get_categories, get_sessions, get_classification, get_grid, get_standings

SEASON_ID = "ae6c6f0d-c652-44f8-94aa-420fc5b3dab4"
CATEGORY_ID = "e8c110ad-64aa-4e8e-8a86-f2f152f6a942"

seasons = get_seasons()
print("SEASON: ", seasons[1])
print("-----------------------------------------")

events = get_events(SEASON_ID, True)
print("EVENT", events[1])
print("-----------------------------------------")

categories = get_categories(SEASON_ID)
print("CATEGORY", categories[1])
print("-----------------------------------------")

sessions = get_sessions(events[1].get("id"), categories[1].get("id"))
print("SESSION", sessions[1])
print("-----------------------------------------")

classification = get_classification(sessions[1].get("id"))
print("CLASSIFICATION: ", classification)
print("-----------------------------------------")

grid = get_grid(events[1].get("id"), categories[1].get("id"))
print("GRID: ", grid[1])
print("-----------------------------------------")

standings = get_standings(SEASON_ID, categories[1].get("id"))
print("STANDINGS: ", standings)
print("-----------------------------------------")