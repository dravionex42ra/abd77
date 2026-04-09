import requests
import os
import shutil
from tqdm import tqdm

class VideoDownloader:
    def __init__(self, output_dir):
        """
        output_dir can be the main folder or a session folder like fail1/
        """
        self.output_dir = output_dir
        self.temp_dir = os.path.join(output_dir, "temp")
        
        # Ensure directories exist
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(self.temp_dir, exist_ok=True)

    def download(self, url, filename):
        """
        Downloads a video with a progress bar.
        Saves to temp/ first, then moves up.
        """
        temp_path = os.path.join(self.temp_dir, filename)
        final_path = os.path.join(self.output_dir, filename)
        
        # Avoid redundant downloads in the SAME level
        if os.path.exists(final_path):
            print(f"  [i] Already exists: {filename}")
            return True

        header = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        }

        try:
            response = requests.get(url, stream=True, timeout=60, headers=header)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            block_size = 1024
            
            pbar = tqdm(total=total_size, unit='iB', unit_scale=True, desc=f"  Downloading {filename}")
            
            with open(temp_path, 'wb') as f:
                for data in response.iter_content(block_size):
                    pbar.update(len(data))
                    f.write(data)
            pbar.close()
            
            if total_size != 0 and os.path.getsize(temp_path) < total_size:
                print("  [!] Truncated download.")
                return False
                
            shutil.move(temp_path, final_path)
            print(f"  [+] Saved: {final_path}")
            return True

        except Exception as e:
            print(f"  [!] Download error: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False
