"""
Supabase Storage Utility for Mastex SchoolOS
Handles uploading and managing files on Supabase Storage
"""

import os
import uuid
import requests
from django.conf import settings


class SupabaseStorage:
    """Handle file uploads to Supabase Storage"""
    
    def __init__(self):
        self.url = getattr(settings, 'SUPABASE_URL', None)
        self.anon_key = getattr(settings, 'SUPABASE_ANON_KEY', None)
        self.bucket = getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'media')
        
    def _get_headers(self):
        """Get headers for Supabase API requests"""
        return {
            'Authorization': f'Bearer {self.anon_key}',
            'apikey': self.anon_key,
        }
    
    def upload_file(self, file, folder='uploads'):
        """
        Upload a file to Supabase Storage
        
        Args:
            file: Django UploadedFile object
            folder: Folder path within bucket
            
        Returns:
            Public URL of uploaded file or None on failure
        """
        if not self.url or not self.anon_key:
            print("Supabase Storage not configured")
            return None
        
        # Generate unique filename
        ext = os.path.splitext(file.name)[1].lower()
        # If no extension, try to detect from content type or use a default
        if not ext:
            content_type = getattr(file, 'content_type', '')
            if 'jpeg' in content_type or 'jpg' in content_type:
                ext = '.jpg'
            elif 'png' in content_type:
                ext = '.png'
            elif 'gif' in content_type:
                ext = '.gif'
            elif 'webp' in content_type:
                ext = '.webp'
            else:
                ext = '.jpg'  # Default to jpg for images
        filename = f"{uuid.uuid4().hex}{ext}"
        full_path = f"{folder}/{filename}"
        
        # Read file content
        file_content = file.read()
        
        # Upload to Supabase Storage
        upload_url = f"{self.url}/storage/v1/object/{self.bucket}/{full_path}"
        
        try:
            response = requests.post(
                upload_url,
                headers=self._get_headers(),
                files={'file': (filename, file_content, file.content_type)},
            )
            
            if response.status_code in [200, 201]:
                # Return public URL
                return f"{self.url}/storage/v1/object/public/{self.bucket}/{full_path}"
            else:
                print(f"Upload failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Upload error: {e}")
            return None
    
    def delete_file(self, public_url):
        """
        Delete a file from Supabase Storage
        
        Args:
            public_url: Full public URL of the file
            
        Returns:
            True on success, False on failure
        """
        if not self.url or not self.anon_key:
            return False
        
        # Extract storage path from public URL
        # URL format: https://xxx.supabase.co/storage/v1/object/public/media/folder/file.jpg
        path_part = public_url.split('/storage/v1/object/public/')
        if len(path_part) < 2:
            return False
            
        storage_path = path_part[1]
        
        delete_url = f"{self.url}/storage/v1/object/{self.bucket}/{storage_path}"
        
        try:
            response = requests.delete(
                delete_url,
                headers=self._get_headers(),
            )
            
            return response.status_code in [200, 204, 404]
            
        except Exception as e:
            print(f"Delete error: {e}")
            return False


# Global instance for easy importing
supabase_storage = SupabaseStorage()