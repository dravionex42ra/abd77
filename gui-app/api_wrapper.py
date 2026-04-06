import aiohttp
import urllib.parse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SoraAPI:
    BASE_URL = "https://api.soracdn.workers.dev/api-proxy/"
    
    @staticmethod
    async def get_clean_link(session, sora_url):
        encoded_url = urllib.parse.quote(sora_url, safe='')
        target_url = f"{SoraAPI.BASE_URL}{encoded_url}"
        
        headers = {
            "Origin": "https://snapsora.net",
            "Referer": "https://snapsora.net/",
            "Accept": "*/*",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        }
        
        try:
            async with session.get(target_url, headers=headers, timeout=15) as response:
                if response.status == 200:
                    data = await response.json()
                    clean_link = data.get('mp4_source') or data.get('mp4')
                    return clean_link, data
                return None, None
        except Exception as e:
            logger.error(f"API Fetch Error: {e}")
            return None, None
