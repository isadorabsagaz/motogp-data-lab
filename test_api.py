from src.motogp_data_lab.api_client import get_json

seasons = get_json('results/seasons')

print("quant seasons: ", len(seasons))
print("first season: ", seasons[len(seasons)-1])