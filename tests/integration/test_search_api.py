#!/usr/bin/env python3
import requests
import json

def test_search_api():
    """Test the search API functionality"""
    print("Testing Ask Dr. Chaffee Search API...")
    
    test_queries = [
        "carnivore",
        "diet", 
        "health",
        "cholesterol",
        "vegetables"
    ]
    
    for query in test_queries:
        try:
            print(f"\nSearching for: '{query}'")
            response = requests.get(f'http://localhost:3000/api/search?q={query}')
            print(f"Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                print(f"Results found: {len(results)}")
                
                for i, result in enumerate(results[:2]):  # Show top 2
                    text = result.get('text', '')[:80]
                    source = result.get('source_title', 'Unknown')
                    timestamp = result.get('timestamp_url', '')
                    print(f"  {i+1}. {text}...")
                    print(f"     Source: {source}")
                    if timestamp:
                        print(f"     Link: {timestamp}")
            else:
                print(f"Error: {response.text}")
                
        except Exception as e:
            print(f"Request failed: {e}")

if __name__ == "__main__":
    test_search_api()
