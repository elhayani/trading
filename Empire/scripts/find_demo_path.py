import ccxt
import boto3
import json
import os
import sys
import requests

def main():
    print("Hunting for the correct Demo URL path...")
    
    # Try different combinations
    bases = [
        "https://demo-fapi.binance.com/fapi/v1",
        "https://demo-fapi.binance.com/v1",
        "https://demo-fapi.binance.com/fapi",
        "https://demo-fapi.binance.com",
    ]
    
    for base in bases:
        url = f"{base}/ping"
        print(f"Testing {url}...", end=" ")
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                print("✅ 200 OK")
            else:
                print(f"❌ {resp.status_code} - {resp.text[:50]}")
        except Exception as e:
            print(f"💥 ERROR: {e}")

if __name__ == "__main__":
    main()
