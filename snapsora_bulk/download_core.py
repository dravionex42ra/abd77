import aiohttp
import aiofiles
import os
import asyncio
from tqdm.asyncio import tqdm

class VideoArchive:
    """
    Advanced streaming downloader with Auto-Resume and Retry support.
    """
    
    @staticmethod
    def _get_unique_path(path):
        """
        Handles duplicates by appending #1, #2, etc. (Not used for resume).
        """
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        counter = 1
        while True:
            new_path = f"{base}#{counter}{ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    @staticmethod
    async def stream_download(session, mp4_url, output_path, retries=3):
        """
        Downloads a video with 'Range' resume support and automatic retries.
        Saves to a 'temp' subfolder first, then moves to final path.
        """
        base_dir = os.path.dirname(output_path)
        temp_dir = os.path.join(base_dir, "temp")
        os.makedirs(temp_dir, exist_ok=True)
        
        filename = os.path.basename(output_path)
        temp_path = os.path.join(temp_dir, filename)
        
        # Check if already exists in final destination
        if os.path.exists(output_path):
            return True, os.path.getsize(output_path)
            
        current_size = 0
        if os.path.exists(temp_path):
            current_size = os.path.getsize(temp_path)
            
        for attempt in range(retries):
            try:
                headers = {'Range': f'bytes={current_size}-'} if current_size > 0 else {}
                
                async with session.get(mp4_url, headers=headers, timeout=60) as response:
                    # 206=Partial, 200=Full
                    if response.status in (200, 206):
                        total_size = int(response.headers.get('content-length', 0)) + current_size
                        
                        mode = 'ab' if response.status == 206 else 'wb'
                        if response.status == 200: current_size = 0
                        
                        pbar = tqdm(
                            total=total_size,
                            initial=current_size,
                            unit='B',
                            unit_scale=True,
                            desc=f"  {filename[:25]}",
                            leave=False,
                            ncols=80 # Termux friendly width
                        )
                        
                        async with aiofiles.open(temp_path, mode=mode) as f:
                            async for chunk in response.content.iter_chunked(1024 * 1024):
                                await f.write(chunk)
                                current_size += len(chunk)
                                pbar.update(len(chunk))
                        
                        pbar.close()
                        
                        # Move to final destination
                        shutil.move(temp_path, output_path)
                        return True, current_size
                        
                    elif response.status == 416: 
                        if os.path.exists(temp_path):
                            shutil.move(temp_path, output_path)
                        return True, current_size
                    else:
                        print(f"  [!] Attempt {attempt+1} fail: HTTP {response.status}")
                
            except Exception as e:
                print(f"  [!] Attempt {attempt+1} error: {str(e)[:50]}")
            
            if attempt < retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
        
        return False, current_size
