import aiohttp
import urllib.parse
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SoraAPI:
    """
    Wrapper for the reverse-engineered SnapSora API to fetch watermark-free video links.
    """
    BASE_URL = "https://api.soracdn.workers.dev/api-proxy/"
    
    @staticmethod
    async def get_clean_link(session, sora_url):
        """
        Calls the proxy API and returns the direct clean MP4 link.
        """
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
                    # The cleaner link is usually stored in 'mp4_source' or 'mp4'
                    clean_link = data.get('mp4_source') or data.get('mp4')
                    return clean_link, data
                else:
                    logger.error(f"API Error: Status {response.status} for URL {sora_url}")
                    return None, None
        except Exception as e:
            logger.error(f"Network Exception for {sora_url}: {str(e)}")
            return None, None
