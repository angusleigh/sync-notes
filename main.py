import os
import pickle
import mimetypes
import hashlib
from pathlib import Path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload

# Configuration
LOCAL_FOLDER = "/home/angus/synced-gdrive"  # Change this to your desired folder
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'
DRIVE_FOLDER_NAME = 'backup-gs65'

def get_file_md5(file_path):
    """Calculate MD5 checksum of local file"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()

def upload_file(drive_service, drive_folder_id, file_path):
    try:
        file_name = Path(file_path).name
        local_md5 = get_file_md5(file_path)
        
        # Check if file already exists in Drive
        existing_files = drive_service.files().list(
            q=f"name='{file_name}' and parents in '{drive_folder_id}' and trashed=false",
            fields="files(id, name, md5Checksum)"
        ).execute()
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = 'application/octet-stream'
        
        media = MediaFileUpload(file_path, mimetype=mime_type)
        
        if existing_files.get('files'):
            # File exists - check if it has changed
            file_id = existing_files['files'][0]['id']
            drive_md5 = existing_files['files'][0].get('md5Checksum')
            
            if drive_md5 == local_md5:
                print(f"Skipped {file_name} (unchanged)")
                return
            
            # Update existing file
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print(f"Updated {file_name} in Google Drive")
        else:
            # Create new file
            file_metadata = {
                'name': file_name,
                'parents': [drive_folder_id]
            }
            drive_service.files().create(
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
    """Upload all existing files"""
    all_files = Path(local_folder).glob('*')
    for file_path in all_files:
        if file_path.is_file():
            upload_file(service, folder_id, str(file_path))

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
    print("Backing up files...")
    sync_existing_files(drive_service, drive_folder_id, LOCAL_FOLDER)
    print("Backup complete!")

if __name__ == "__main__":
    main()
