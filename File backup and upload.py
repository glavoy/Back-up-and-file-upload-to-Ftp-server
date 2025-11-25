import json
import base64
import time
import os
import sys
import warnings
import py7zr
import pysftp
from nacl.secret import SecretBox

# Suppress host key warnings
warnings.filterwarnings('ignore', '.*Failed to load HostKeys.*')

# --- LOAD CONFIGURATION ---
config_file = 'config.json'

try:
    with open(config_file, 'r') as f:
        config = json.load(f)
except FileNotFoundError:
    print(f"Error: '{config_file}' not found. Please ensure it is in the same directory.")
    sys.exit(1)

# --- VARIABLE SETUP FROM JSON ---
computer = config['computer_id']
timestamp = time.strftime("%Y_%m_%d-%H-%M-%S")
file_name = f"{computer}_{timestamp}"

# Build remote directory (e.g., /TES/cpu10)
remote_dir = f"{config['ftp']['remote_base_dir']}/{computer}"

# Local paths
folder_to_backup = config['paths']['source_folder']
# Ensure the staging folder exists, creates it if missing
backup_folder = config['paths']['backup_staging_folder']
if not os.path.exists(backup_folder):
    os.makedirs(backup_folder)

archive_path = os.path.join(backup_folder, file_name + ".7z")

# --- DECRYPTION ---
try:
    # Decode the master key
    key = base64.b64decode(config['security']['master_key'])
    box = SecretBox(key)

    # Read the encrypted password file
    with open(config['security']['encrypted_pwd_file'], "rb") as f:
        encrypted_data = base64.b64decode(f.read())

    # Decrypt the FTP password
    ftp_password = box.decrypt(encrypted_data).decode()
    print("Credentials decrypted successfully.")

except Exception as e:
    print(f"Error decrypting credentials: {e}")
    sys.exit(1)

# --- COMPRESSION ---
print('Please be patient, this may take a few moments.\n\nBacking up data.....')

try:
    with py7zr.SevenZipFile(archive_path, 'w') as archive:
        for root, dirs, files in os.walk(folder_to_backup):
            for file in files:
                file_path = os.path.join(root, file)
                # Create relative path for inside the archive to maintain structure
                archive_internal_path = os.path.relpath(file_path, folder_to_backup)
                archive.write(file_path, arcname=archive_internal_path)
    print(f"Archive created at: {archive_path}")

except Exception as e:
    print(f"Error creating backup archive: {e}")
    sys.exit(1)

# --- SFTP UPLOAD ---
cnopts = pysftp.CnOpts()
cnopts.hostkeys = None

print(f"Connecting to {config['ftp']['host']}...")

try:
    with pysftp.Connection(host=config['ftp']['host'], 
                           username=config['ftp']['username'], 
                           password=ftp_password, 
                           cnopts=cnopts) as ftp:
        
        # Ensure remote directory exists, if not, create it (optional safety check)
        if not ftp.exists(remote_dir):
            try:
                ftp.mkdir(remote_dir)
            except OSError:
                pass # Handle cases where parent dirs might be missing or perm issues

        with ftp.cd(remote_dir):
            print(f"Uploading {os.path.basename(archive_path)} to {remote_dir}...")
            ftp.put(archive_path)

    print('File Successfully Uploaded.........!')

except Exception as e:
    print(f"FTP Connection or Upload failed: {e}")