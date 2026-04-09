"""
Supabase Storage Utility for Mastex SchoolOS
Handles uploading and managing files on Supabase Storage
"""

import logging
import os
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_TYPES = frozenset([
    'image/jpeg', 'image/png', 'image/gif', 'image/webp',
])
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB


class SupabaseStorage:
    """Handle file uploads to Supabase Storage"""
    
    def __init__(self):
        self.url = getattr(settings, 'SUPABASE_URL', None)
        self.anon_key = getattr(settings, 'SUPABASE_ANON_KEY', None)
        self.bucket = getattr(settings, 'SUPABASE_STORAGE_BUCKET', 'media')
        
    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.anon_key}',
            'apikey': self.anon_key,
        }
    
    def upload_file(self, file, folder='uploads'):
        """
        Upload a file to Supabase Storage.
        Validates content type and file size before uploading.
        
        Returns:
            Public URL of uploaded file or None on failure.
        """
        if not self.url or not self.anon_key:
            logger.warning("Supabase Storage not configured")
            return None
        
        content_type = getattr(file, 'content_type', '')
        if content_type not in ALLOWED_IMAGE_TYPES:
            logger.warning("Upload rejected: unsupported content type %s", content_type)
            return None
        
        file_size = getattr(file, 'size', 0)
        if file_size > MAX_UPLOAD_SIZE:
            logger.warning("Upload rejected: file too large (%d bytes)", file_size)
            return None
        
        ext = os.path.splitext(file.name)[1].lower()
        if not ext:
            ext_map = {
                'image/jpeg': '.jpg', 'image/png': '.png',
                'image/gif': '.gif', 'image/webp': '.webp',
            }
            ext = ext_map.get(content_type, '.jpg')
        filename = f"{uuid.uuid4().hex}{ext}"
        full_path = f"{folder}/{filename}"
        
        file_content = file.read()
        upload_url = f"{self.url}/storage/v1/object/{self.bucket}/{full_path}"
        
        try:
            response = requests.post(
                upload_url,
                headers=self._get_headers(),
                files={'file': (filename, file_content, content_type)},
                timeout=30,
            )
            
            if response.status_code in (200, 201):
                return f"{self.url}/storage/v1/object/public/{self.bucket}/{full_path}"
            else:
                logger.error("Supabase upload failed: %d - %s", response.status_code, response.text[:200])
                return None
                
        except Exception as e:
            logger.error("Supabase upload error: %s", e)
            return None
    
    def delete_file(self, public_url):
        """Delete a file from Supabase Storage."""
        if not self.url or not self.anon_key:
            return False
        
        path_part = public_url.split('/storage/v1/object/public/')
        if len(path_part) < 2:
            return False
            
        storage_path = path_part[1]
        delete_url = f"{self.url}/storage/v1/object/{self.bucket}/{storage_path}"
        
        try:
            response = requests.delete(
                delete_url,
                headers=self._get_headers(),
                timeout=30,
            )
            return response.status_code in (200, 204, 404)
        except Exception as e:
            logger.error("Supabase delete error: %s", e)
            return False


supabase_storage = SupabaseStorage()