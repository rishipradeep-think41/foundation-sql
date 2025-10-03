import os
from typing import Optional


class SQLTemplateCache:
    """
    Simple file-based cache using file names as keys.
    
    Attributes:
        cache_dir (str): Directory to store cached templates
    """
    
    def __init__(self, cache_dir: str):
        """
        Initialize the SQL template cache.
        
        Args:
            cache_dir (str): Directory to store cached templates
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
    
    def _get_cache_path(self, key: str) -> str:
        """
        Get the full path for a cache file.
        
        Args:
            key (str): File name to use as cache key
        
        Returns:
            str: Full path to the cache file
        """
        return os.path.join(self.cache_dir, key)
    
    def set(self, key: str, template: str) -> None:
        """
        Store an SQL template in the cache.
        
        Args:
            key (str): File name to use as cache key
            template (str): SQL template to cache
        """
        cache_file = self._get_cache_path(key)
        with open(cache_file, 'w') as f:
            f.write(template)
    
    def get(self, key: str) -> Optional[str]:
        """
        Retrieve a cached SQL template.
        
        Args:
            key (str): File name to use as cache key
        
        Returns:
            Optional[str]: Cached SQL template or None if not found
        """
        cache_file = self._get_cache_path(key)
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return f.read()
        return None
    
    def exists(self, key: str) -> bool:
        """
        Check if a cache entry exists.
        
        Args:
            key (str): File name to use as cache key
        
        Returns:
            bool: True if cache entry exists, False otherwise
        """
        cache_file = self._get_cache_path(key)
        return os.path.exists(cache_file)
    
    def clear(self, key: Optional[str] = None) -> None:
        """
        Clear cached templates.
        
        Args:
            key (Optional[str]): Specific key to clear. 
                                 If None, clears entire cache.
        """
        if key:
            cache_file = self._get_cache_path(key)
            if os.path.exists(cache_file):
                os.remove(cache_file)
        else:
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
