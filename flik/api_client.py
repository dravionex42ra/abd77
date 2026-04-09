import requests
import json
import time

class FliflikAPI:
    def __init__(self):
        self.url = "https://online.fliflik.com/get-video-link"
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://online.fliflik.com",
            "Referer": "https://online.fliflik.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }

    def get_video_link(self, sora_url):
        """
        Fetches the direct MP4 link for a given Sora URL.
        """
        payload = {"url": sora_url}
        try:
            response = requests.post(self.url, json=payload, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") == 200 and data.get("data"):
                return data["data"]
            else:
                print(f"  [!] API Error: {data.get('msg', 'Unknown error')}")
                return None
        except Exception as e:
            print(f"  [!] Connection failed for {sora_url}: {e}")
            return None

# Simple Test
if __name__ == "__main__":
    client = FliflikAPI()
    test_link = "https://sora.chatgpt.com/p/s_691284466e908191a23cc542f66a5c90"
    print(f"Testing with: {test_link}")
    result = client.get_video_link(test_link)
    print(f"Result: {result}")
