"""AWS S3 utility for Cekat AI platform."""

import os
import boto3
from typing import Optional, Dict, Any
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class CekatS3Client:
    """S3 client for Cekat AI platform operations."""
    
    def __init__(self):
        """Initialize S3 client with credentials from environment."""
        self.aws_access_key = os.getenv('AWS_S3_ACCESS_KEY')
        self.aws_secret_key = os.getenv('AWS_S3_SECRET_ACCESS_KEY')
        self.bucket_name = os.getenv('AWS_S3_BUCKET_NAME', 'cekat-ai')
        self.region = os.getenv('AWS_S3_BUCKET_REGION', 'us-east-2')
        
        if not self.aws_access_key or not self.aws_secret_key:
            logger.warning("AWS credentials not found in environment variables")
            self.s3_client = None
            return
            
        try:
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=self.region
            )
            logger.info(f"S3 client initialized for bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to initialize S3 client: {e}")
            self.s3_client = None
    
    def upload_file(self, file_path: str, s3_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """Upload file to S3 bucket."""
        if not self.s3_client:
            return {"success": False, "error": "S3 client not initialized"}
        
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
                
            self.s3_client.upload_file(
                file_path, 
                self.bucket_name, 
                s3_key,
                ExtraArgs=extra_args
            )
            
            url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            logger.info(f"File uploaded successfully: {s3_key}")
            
            return {
                "success": True,
                "url": url,
                "bucket": self.bucket_name,
                "key": s3_key
            }
            
        except Exception as e:
            logger.error(f"Failed to upload file {s3_key}: {e}")
            return {"success": False, "error": str(e)}
    
    def upload_fileobj(self, file_obj, s3_key: str, content_type: Optional[str] = None) -> Dict[str, Any]:
        """Upload file object to S3 bucket."""
        if not self.s3_client:
            return {"success": False, "error": "S3 client not initialized"}
        
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
                
            self.s3_client.upload_fileobj(
                file_obj, 
                self.bucket_name, 
                s3_key,
                ExtraArgs=extra_args
            )
            
            url = f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{s3_key}"
            logger.info(f"File object uploaded successfully: {s3_key}")
            
            return {
                "success": True,
                "url": url,
                "bucket": self.bucket_name,
                "key": s3_key
            }
            
        except Exception as e:
            logger.error(f"Failed to upload file object {s3_key}: {e}")
            return {"success": False, "error": str(e)}
    
    def download_file(self, s3_key: str, local_path: str) -> Dict[str, Any]:
        """Download file from S3 bucket."""
        if not self.s3_client:
            return {"success": False, "error": "S3 client not initialized"}
        
        try:
            self.s3_client.download_file(self.bucket_name, s3_key, local_path)
            logger.info(f"File downloaded successfully: {s3_key}")
            
            return {
                "success": True,
                "local_path": local_path,
                "bucket": self.bucket_name,
                "key": s3_key
            }
            
        except Exception as e:
            logger.error(f"Failed to download file {s3_key}: {e}")
            return {"success": False, "error": str(e)}
    
    def delete_file(self, s3_key: str) -> Dict[str, Any]:
        """Delete file from S3 bucket."""
        if not self.s3_client:
            return {"success": False, "error": "S3 client not initialized"}
        
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=s3_key)
            logger.info(f"File deleted successfully: {s3_key}")
            
            return {
                "success": True,
                "bucket": self.bucket_name,
                "key": s3_key
            }
            
        except Exception as e:
            logger.error(f"Failed to delete file {s3_key}: {e}")
            return {"success": False, "error": str(e)}
    
    def list_files(self, prefix: str = "") -> Dict[str, Any]:
        """List files in S3 bucket with optional prefix."""
        if not self.s3_client:
            return {"success": False, "error": "S3 client not initialized"}
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    files.append({
                        "key": obj['Key'],
                        "size": obj['Size'],
                        "last_modified": obj['LastModified'].isoformat(),
                        "url": f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{obj['Key']}"
                    })
            
            return {
                "success": True,
                "files": files,
                "count": len(files)
            }
            
        except Exception as e:
            logger.error(f"Failed to list files with prefix {prefix}: {e}")
            return {"success": False, "error": str(e)}
    
    def generate_presigned_url(self, s3_key: str, expiration: int = 3600) -> Dict[str, Any]:
        """Generate presigned URL for file access."""
        if not self.s3_client:
            return {"success": False, "error": "S3 client not initialized"}
        
        try:
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expiration
            )
            
            return {
                "success": True,
                "url": url,
                "expires_in": expiration
            }
            
        except Exception as e:
            logger.error(f"Failed to generate presigned URL for {s3_key}: {e}")
            return {"success": False, "error": str(e)}


# Global instance
cekat_s3_client = CekatS3Client()

def get_cekat_s3_client() -> CekatS3Client:
    """Get the global CekatS3Client instance."""
    return cekat_s3_client
