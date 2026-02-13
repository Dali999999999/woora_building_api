import requests
import json

def test_nominatim():
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': 'P',
        'countrycodes': 'BJ',
        'format': 'json',
        'addressdetails': 1,
        'limit': 10,
        'accept-language': 'fr'
    }
    headers = {'User-Agent': 'WooraDebug/1.0'}
    
    print(f"Testing URL: {url}")
    print(f"Params: {params}")
    
    try:
        r = requests.get(url, params=params, headers=headers)
        print(f"Status Code: {r.status_code}")
        data = r.json()
        print(f"Count: {len(data)}")
        for item in data:
            addr = item.get('address', {})
            city = (
                addr.get('city') or 
                addr.get('town') or 
                addr.get('village') or 
                addr.get('hamlet') or 
                addr.get('suburb') or 
                addr.get('municipality')
            )
            print(f" - Display: {item.get('display_name')}")
            print(f"   City detected: {city}")
            if city:
                print(f"   Starts with 'P'?: {city.lower().startswith('p')}")
            else:
                print("   No city detected")
            print("---")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_nominatim()
