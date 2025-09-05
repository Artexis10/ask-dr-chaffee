#!/usr/bin/env python3
"""
Proxy management for YouTube ingestion
"""

import os
import random
import logging
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ProxyConfig:
    """Configuration for proxy usage"""
    enabled: bool = False
    rotation_enabled: bool = False
    rotation_interval: int = 10  # Minutes
    current_proxy_index: int = 0
    last_rotation_time: float = 0
    
    # Proxy sources
    proxy_list: List[str] = None
    proxy_file: str = None
    proxy_env_var: str = None

class ProxyManager:
    """Manages proxy rotation and selection for API requests"""
    
    def __init__(self, config: Optional[ProxyConfig] = None):
        """Initialize proxy manager with optional config"""
        self.config = config or ProxyConfig()
        self._proxies = []
        self._load_proxies()
    
    def _load_proxies(self) -> None:
        """Load proxies from all configured sources"""
        if not self.config.enabled:
            return
            
        # Clear existing proxies
        self._proxies = []
        
        # Load from direct list
        if self.config.proxy_list:
            self._proxies.extend(self.config.proxy_list)
            
        # Load from file
        if self.config.proxy_file and os.path.exists(self.config.proxy_file):
            try:
                with open(self.config.proxy_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self._proxies.append(line)
            except Exception as e:
                logger.error(f"Failed to load proxies from file: {e}")
                
        # Load from environment variable
        if self.config.proxy_env_var:
            env_proxies = os.getenv(self.config.proxy_env_var)
            if env_proxies:
                for proxy in env_proxies.split(','):
                    proxy = proxy.strip()
                    if proxy:
                        self._proxies.append(proxy)
        
        # Log results
        if self._proxies:
            logger.info(f"Loaded {len(self._proxies)} proxies")
        else:
            logger.warning("No proxies loaded")
    
    def get_proxy(self) -> Optional[Dict[str, str]]:
        """Get current proxy in requests format"""
        if not self.config.enabled or not self._proxies:
            return None
            
        # Check if we need to rotate
        if self.config.rotation_enabled:
            current_time = time.time()
            minutes_since_rotation = (current_time - self.config.last_rotation_time) / 60
            
            if minutes_since_rotation >= self.config.rotation_interval:
                self._rotate_proxy()
        
        # Get current proxy
        if self._proxies:
            proxy_url = self._proxies[self.config.current_proxy_index % len(self._proxies)]
            
            # Convert to requests format
            if '://' not in proxy_url:
                # Assume http if no protocol specified
                proxy_url = f"http://{proxy_url}"
                
            return {
                'http': proxy_url,
                'https': proxy_url
            }
        
        return None
    
    def _rotate_proxy(self) -> None:
        """Rotate to next proxy"""
        if not self._proxies:
            return
            
        self.config.current_proxy_index = (self.config.current_proxy_index + 1) % len(self._proxies)
        self.config.last_rotation_time = time.time()
        logger.info(f"Rotated to proxy {self.config.current_proxy_index + 1}/{len(self._proxies)}")
    
    def force_rotate(self) -> None:
        """Force rotation to next proxy"""
        self._rotate_proxy()
    
    def get_random_proxy(self) -> Optional[Dict[str, str]]:
        """Get a random proxy instead of the current one"""
        if not self._proxies:
            return None
            
        random_index = random.randint(0, len(self._proxies) - 1)
        proxy_url = self._proxies[random_index]
        
        # Convert to requests format
        if '://' not in proxy_url:
            # Assume http if no protocol specified
            proxy_url = f"http://{proxy_url}"
            
        return {
            'http': proxy_url,
            'https': proxy_url
        }

# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Example with direct proxy list
    config = ProxyConfig(
        enabled=True,
        rotation_enabled=True,
        rotation_interval=5,
        proxy_list=[
            "http://proxy1.example.com:8080",
            "http://proxy2.example.com:8080",
            "socks5://proxy3.example.com:1080"
        ]
    )
    
    manager = ProxyManager(config)
    
    # Get current proxy
    proxy = manager.get_proxy()
    print(f"Current proxy: {proxy}")
    
    # Force rotation
    manager.force_rotate()
    proxy = manager.get_proxy()
    print(f"After rotation: {proxy}")
    
    # Get random proxy
    random_proxy = manager.get_random_proxy()
    print(f"Random proxy: {random_proxy}")
