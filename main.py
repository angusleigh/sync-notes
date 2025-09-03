import os
import pickle
import time
import mimetypes
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# Configuration
LOCAL_FOLDER = "/home/angus/synced-gdrive"  # Change this to your desired folder
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'
DRIVE_FOLDER_NAME = 'synced-files'

class FileSyncHandler(FileSystemEventHandler):
    def __init__(self, drive_service, drive_folder_id):
        self.drive_service = drive_service
        self.drive_folder_id = drive_folder_id
        
    def on_modified(self, event):
        if not event.is_directory:
            print(f"Detected change: {event.src_path}")
            self.upload_file(event.src_path)
    
    def on_created(self, event):
        if not event.is_directory:
            print(f"Detected new file: {event.src_path}")
            self.upload_file(event.src_path)
    
    def upload_file(self, file_path):
        try:
            file_name = Path(file_path).name
            
            # Check if file already exists in Drive
            existing_files = self.drive_service.files().list(
                q=f"name='{file_name}' and parents in '{self.drive_folder_id}' and trashed=false",
                fields="files(id, name)"
            ).execute()
            
            # Detect MIME type
            mime_type, _ = mimetypes.guess_type(file_path)
            if mime_type is None:
                mime_type = 'application/octet-stream'
            
            media = MediaFileUpload(file_path, mimetype=mime_type)
            
            if existing_files.get('files'):
                # Update existing file
                file_id = existing_files['files'][0]['id']
                self.drive_service.files().update(
                    fileId=file_id,
                    media_body=media
                ).execute()
                print(f"Updated {file_name} in Google Drive")
            else:
                # Create new file
                file_metadata = {
                    'name': file_name,
                    'parents': [self.drive_folder_id]
                }
                self.drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                print(f"Uploaded {file_name} to Google Drive")
                
        except Exception as e:
            print(f"Error uploading {file_path}: {e}")

def authenticate_drive():
    creds = None
    
    # Load existing token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"Please place your {CREDENTIALS_FILE} file in the current directory")
                print("Get it from: https://console.cloud.google.com/apis/credentials")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save credentials for next run
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def create_drive_folder(service, folder_name):
    # Check if folder already exists
    existing_folders = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        fields="files(id, name)"
    ).execute()
    
    if existing_folders.get('files'):
        folder_id = existing_folders['files'][0]['id']
        print(f"Using existing Drive folder: {folder_name}")
    else:
        # Create new folder
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        folder = service.files().create(body=folder_metadata, fields='id').execute()
        folder_id = folder.get('id')
        print(f"Created Drive folder: {folder_name}")
    
    return folder_id

def sync_existing_files(service, folder_id, local_folder):
    """Upload all existing files on startup"""
    all_files = Path(local_folder).glob('*')
    for file_path in all_files:
        if file_path.is_file():
            handler = FileSyncHandler(service, folder_id)
            handler.upload_file(str(file_path))

def main():
    # Ensure local folder exists
    os.makedirs(LOCAL_FOLDER, exist_ok=True)
    
    # Authenticate with Google Drive
    print("Authenticating with Google Drive...")
    drive_service = authenticate_drive()
    if not drive_service:
        return
    
    print("Authentication successful!")
    
    # Create/get Drive folder
    drive_folder_id = create_drive_folder(drive_service, DRIVE_FOLDER_NAME)
    
    # Sync existing files
    print("Syncing existing files...")
    sync_existing_files(drive_service, drive_folder_id, LOCAL_FOLDER)
    
    # Set up file monitoring
    print(f"Starting file monitoring on: {LOCAL_FOLDER}")
    print("Monitoring for all file changes... Press Ctrl+C to stop")
    
    event_handler = FileSyncHandler(drive_service, drive_folder_id)
    observer = Observer()
    observer.schedule(event_handler, LOCAL_FOLDER, recursive=True)
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopping file monitor...")
    
    observer.join()

if __name__ == "__main__":
    main()
