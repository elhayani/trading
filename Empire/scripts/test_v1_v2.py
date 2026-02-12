import requests

def main():
    print("Testing v1 vs v2 for account endpoint...")
    
    endpoints = [
        "https://demo-fapi.binance.com/fapi/v1/account",
        "https://demo-fapi.binance.com/fapi/v2/account",
    ]
    
    for url in endpoints:
        print(f"Testing {url}...", end=" ")
        try:
            # Note: 401/400 is fine as long as it's not 404/Invalid Path
            resp = requests.get(url, timeout=5)
            print(f"RES: {resp.status_code} - {resp.text[:100]}")
        except Exception as e:
            print(f"💥 ERROR: {e}")

if __name__ == "__main__":
    main()
