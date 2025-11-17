"""Utility script to clear chat history from Redis for testing."""

import redis
import sys
from typing import Optional

def clear_chat_history(thread_id: Optional[str] = None):
    """Clear chat history from Redis.
    
    Args:
        thread_id: Specific thread ID to clear (e.g., "telegram:1751336201")
                  If None, will prompt for confirmation to clear all.
    """
    # Connect to Redis running in Docker container
    # Port 6379 is exposed from ai-agent-redis-1 container
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    
    try:
        if thread_id:
            # Clear specific thread
            pattern = f"*{thread_id}*"
            keys = r.keys(pattern)
            
            if not keys:
                print(f"No keys found for thread_id: {thread_id}")
                return
            
            print(f"Found {len(keys)} keys for thread_id: {thread_id}")
            for key in keys:
                print(f"  - {key}")
            
            confirm = input(f"\nDelete {len(keys)} keys? (yes/no): ")
            if confirm.lower() in ['yes', 'y']:
                for key in keys:
                    r.delete(key)
                print(f"✓ Deleted {len(keys)} keys")
            else:
                print("Cancelled")
        else:
            # Clear all checkpoint data
            pattern = "checkpoint:*"
            keys = r.keys(pattern)
            
            if not keys:
                print("No checkpoint keys found")
                return
            
            print(f"Found {len(keys)} checkpoint keys")
            confirm = input(f"\n⚠️  Delete ALL {len(keys)} checkpoint keys? (yes/no): ")
            if confirm.lower() in ['yes', 'y']:
                for key in keys:
                    r.delete(key)
                print(f"✓ Deleted {len(keys)} keys")
            else:
                print("Cancelled")
                
    except redis.ConnectionError:
        print("❌ Failed to connect to Redis.")
        print("Make sure the Redis container is running:")
        print("  docker ps | grep redis")
        print("  docker exec -it ai-agent-redis-1 redis-cli PING")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        thread_id = sys.argv[1]
        print(f"Clearing chat history for thread: {thread_id}")
        clear_chat_history(thread_id)
    else:
        print("Usage:")
        print("  python clear_chat_history.py telegram:1751336201  # Clear specific thread")
        print("  python clear_chat_history.py                       # Clear all (interactive)")
        print()
        
        choice = input("Clear specific thread or all? (thread/all/cancel): ").lower()
        if choice == 'thread':
            thread_id = input("Enter thread ID (e.g., telegram:1751336201): ")
            clear_chat_history(thread_id)
        elif choice == 'all':
            clear_chat_history()
        else:
            print("Cancelled")
