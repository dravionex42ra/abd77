import aiohttp
import aiofiles
import os
from tqdm.asyncio import tqdm

class VideoArchive:
    """
    Streaming downloader with smart duplicate handling.
    """
    
    @staticmethod
    def _get_unique_path(path):
        """
        If file exists, appends #1, #2, etc. to the filename before the extension.
        Example: video.mp4 -> video#1.mp4
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
    async def stream_download(session, mp4_url, output_path):
        """
        Saves the video chunks directly to the specified path with a progress bar.
        Handles duplicates by renaming.
        """
        try:
            # Ensure folder exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Smart Renaming for duplicates
            final_path = VideoArchive._get_unique_path(output_path)
            
            async with session.get(mp4_url, timeout=45) as response:
                if response.status == 200:
                    file_size = int(response.headers.get('content-length', 0))
                    
                    filename = os.path.basename(final_path)
                    progress_bar = tqdm(
                        total=file_size,
                        unit='B',
                        unit_scale=True,
                        desc=f"Downloading {filename[:25]}...",
                        leave=False
                    )
                    
                    async with aiofiles.open(final_path, mode='wb') as f:
                        async for chunk in response.content.iter_chunked(1024 * 1024):
                            await f.write(chunk)
                            progress_bar.update(len(chunk))
                    
                    progress_bar.close()
                    return True
                else:
                    print(f"Download Error: Status {response.status} for {mp4_url}")
                    return False
        except Exception as e:
            print(f"Exception during download: {str(e)}")
            return False
