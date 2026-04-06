import aiohttp
import urllib.parse
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SnapsoraFetcher:
    """
    Revised API handler for Snapsora proxy worker (Bulk Page Compatible).
    """
    BASE_URL = "https://api.soracdn.workers.dev/api-proxy/"
    
    @staticmethod
    async def get_direct_link(session, sora_url):
        """
        Calls the proxy API and extracts the direct clean MP4 link from 'links' -> 'mp4'.
        """
        try:
            # Clean URL and Encode
            sora_url = sora_url.strip()
            encoded_url = urllib.parse.quote(sora_url, safe='')
            target_url = f"{SnapsoraFetcher.BASE_URL}{encoded_url}"
            
            headers = {
                "Origin": "https://snapsora.net",
                "Referer": "https://snapsora.net/",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            }
            
            async with session.get(target_url, headers=headers, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Real Website Structure Check
                    links = data.get('links', {})
                    post_info = data.get('post_info', {})
                    
                    # Extract Link and Title
                    direct_link = links.get('mp4')
                    title = post_info.get('title', 'Unknown Title')
                    
                    if not direct_link:
                        # Fallback for alternative structures
                        direct_link = data.get('mp4_source') or data.get('mp4')
                    
                    if direct_link:
                        return direct_link, {"title": title, "raw": data}
                    else:
                        logger.error(f"Link not found in response for {sora_url}")
                        return None, data
                else:
                    logger.error(f"API Request failed with status {response.status}")
                    return None, None
        except Exception as e:
            logger.error(f"Error fetching direct link for {sora_url}: {str(e)}")
            return None, None
