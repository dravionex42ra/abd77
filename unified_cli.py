import asyncio
import os
import argparse
import logging
from manager import SoraManager

# Simple CLI that processes all batch files automatically
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sora Archiver - Simple Unified CLI")
    parser.add_argument("--concurrency", type=int, default=25, help="Number of concurrent downloads")
    args = parser.parse_args()
    
    print("🚀 Starting Sora Archiver (Standard Mode)")
    print(f"📦 Files in 'input/' will be processed automatically.")
    
    manager = SoraManager(concurrency=args.concurrency)
    try:
        asyncio.run(manager.process_all_batches())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
