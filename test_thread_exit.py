#!/usr/bin/env python3
"""
Test program to observe SystemExit behavior when called from a thread.
"""

import sys
import threading
import time


def thread_function():
    """Function that runs in a separate thread and calls sys.exit()"""
    print(f"Thread {threading.current_thread().name} started")
    time.sleep(1)
    print(f"Thread {threading.current_thread().name} calling sys.exit(42)")
    sys.exit(42)  # This raises SystemExit
    print("This line should never be reached")


def main():
    print("Main thread started")

    # Create and start the thread
    thread = threading.Thread(target=thread_function, name="TestThread")
    print(f"Starting thread: {thread.name}")
    thread.start()

    # Wait a bit and check if main thread continues
    time.sleep(2)
    print("Main thread still running after 2 seconds")

    # Check thread status
    if thread.is_alive():
        print(f"Thread {thread.name} is still alive")
    else:
        print(f"Thread {thread.name} has terminated")

    # Try to join the thread
    print("Attempting to join thread...")
    thread.join(timeout=1)

    print("Main thread exiting normally")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(f"Caught SystemExit in main: {e.code}")
    except Exception as e:
        print(f"Caught exception in main: {type(e).__name__}: {e}")
