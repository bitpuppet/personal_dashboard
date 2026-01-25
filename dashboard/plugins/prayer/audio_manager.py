import pygame
import threading
from datetime import datetime, timedelta
import logging
from pathlib import Path
from typing import Dict, Optional, Any
import requests
import os
import json

class AdhanManager:
    def __init__(self, config: Dict[str, Any]):
        pygame.mixer.init()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.config = config
        self.audio_dir = Path(__file__).parent / "audio"
        self.is_playing = False
        self.next_adhan: Dict[str, datetime] = {}
        self.current_thread = None
        self.initialized = False
        self.adhan_cache = {}
        
        # Ensure audio directory exists
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize adhan files and start background downloads
        self.adhan_files = {}
        self._setup_adhan_files(download=True)
        
        # Create cache directory if it doesn't exist
        cache_dir_str = os.path.expanduser("~/.personal_dashboard/adhan_cache")
        self.cache_dir = Path(cache_dir_str)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Load saved volumes
        self.volumes_file = os.path.expanduser(config['adhan'].get('volumes_file', '~/.personal_dashboard/adhan_volume.json'))
        self.load_volumes()
    
    def _setup_adhan_files(self, download: bool = True):
        """Setup adhan files and download if missing"""
        prayer_specific = self.config.get('adhan', {}).get('prayer_specific', {})
        default_url = self.config.get('adhan', {}).get('default_url')
        
        for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
            file_name = f"adhan_{prayer.lower()}.mp3"
            self.adhan_files[prayer] = self.audio_dir / file_name
            
            # Start background download if file doesn't exist
            if download and not self.adhan_files[prayer].exists():
                url = prayer_specific.get(prayer, {}).get('url', default_url)
                if url:
                    self._start_background_download(prayer, url)
    
    def _start_background_download(self, prayer: str, url: str):
        """Start a background thread to download adhan file"""
        def download():
            try:
                self.logger.info(f"Starting background download for {prayer} adhan")
                self._download_adhan(url, self.adhan_files[prayer])
            except Exception as e:
                self.logger.error(f"Background download failed for {prayer}: {e}")
        
        thread = threading.Thread(target=download, daemon=True)
        thread.start()
    
    def _download_adhan(self, url: str, file_path: Path) -> bool:
        """Download adhan file if not present"""
        try:
            if not url:
                self.logger.error("No adhan URL configured")
                return False
                
            self.logger.info(f"Downloading adhan from: {url} to {file_path}")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(file_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
            self.logger.info(f"Adhan file downloaded successfully to {file_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error downloading adhan file: {e}")
            return False
    
    def _load_volume(self) -> float:
        """Load saved volume from file"""
        if not self.config.get('save_volume'):
            return self.config.get('volume', 0.7)
            
        try:
            if os.path.exists(self.volumes_file):
                with open(self.volumes_file, 'r') as f:
                    saved = json.load(f)
                    return saved.get('volume', self.config.get('volume', 0.7))
        except Exception as e:
            self.logger.error(f"Error loading saved volume: {e}")
        
        return self.config.get('volume', 0.7)
    
    def _save_volume(self) -> None:
        """Save current volume to file"""
        if not self.config.get('save_volume'):
            return
            
        try:
            os.makedirs(os.path.dirname(self.volumes_file), exist_ok=True)
            with open(self.volumes_file, 'w') as f:
                json.dump({'volume': self.volume}, f)
        except Exception as e:
            self.logger.error(f"Error saving volume: {e}")
    
    def get_volume(self) -> float:
        """Get current volume"""
        return self.volume
    
    def set_volume(self, volume: float) -> None:
        """Set master volume"""
        self.volume = max(0.0, min(1.0, volume))
        # Always update pygame mixer volume, even when not playing
        pygame.mixer.music.set_volume(self.volume)
        self._save_volume()
    
    def stop_adhan(self) -> None:
        """Stop currently playing adhan"""
        if self.is_playing:
            pygame.mixer.music.stop()
            self.is_playing = False
            # Clean up thread
            if self.current_thread and self.current_thread.is_alive():
                self.current_thread.join(0)
            self.current_thread = None
    
    def play_adhan(self, url: str, volume: float = 1.0) -> bool:
        """Play adhan from URL or file path with specified volume"""
        try:
            self.logger.info(f"Playing adhan from {url} at volume {volume}")
            
            # Stop any currently playing adhan
            self.stop_adhan()
            
            # Check if url is a local file path
            adhan_file = Path(url) if os.path.exists(url) else self._get_adhan_file(url)
            if not adhan_file or not adhan_file.exists():
                self.logger.error("Failed to get adhan file")
                return False
            
            # Set volume
            pygame.mixer.music.set_volume(volume)
            
            # Load and play the audio file
            pygame.mixer.music.load(str(adhan_file))
            pygame.mixer.music.play()
            self.is_playing = True
            self.logger.info("Adhan playback started")
            return True
            
        except Exception as e:
            self.logger.error(f"Error playing adhan: {e}", exc_info=True)
            return False
    
    def check_prayer_times(self, prayer_times: Dict[str, datetime]) -> Optional[str]:
        """Check if it's time for adhan, returns prayer name if adhan starts playing"""
        now = datetime.now()
        
        # Skip first check to prevent playing on launch
        if not self.initialized:
            self.initialized = True
            # Initialize next_adhan times
            for prayer, time in prayer_times.items():
                if now >= time:
                    self.next_adhan[prayer] = time + timedelta(days=1)
                else:
                    self.next_adhan[prayer] = time
            self.logger.info(f"Next adhan times: {self.next_adhan}")
            return None
        
        for prayer, time in prayer_times.items():
            self.logger.debug(f"Checking prayer: {prayer} at time: {time}")
            if not self.adhan_files.get(prayer):
                self.logger.info(f"No adhan file found for {prayer}")
                continue
                
            if now >= time and (
                prayer not in self.next_adhan or 
                time > self.next_adhan[prayer]
            ):
                self.logger.debug(f"Time for {prayer} prayer")
                if self.play_adhan(self.adhan_files[prayer].as_posix()):
                    self.logger.debug(f"Playing adhan for {prayer}")
                    self.next_adhan[prayer] = time + timedelta(days=1)
                    return prayer

        return None
    
    def needs_download(self, prayer: str) -> bool:
        """Check if adhan file needs to be downloaded"""
        return not self.adhan_files.get(prayer).exists()
    
    def download_adhan(self, prayer: str) -> bool:
        """Download adhan file for specific prayer"""
        try:
            url = self.config.get('adhan', {}).get('prayer_specific', {}).get(prayer, {}).get('url')
            if not url:
                url = self.config.get('adhan', {}).get('default_url')
            
            if not url:
                self.logger.error(f"No URL configured for {prayer} adhan")
                return False
            
            return self._download_adhan(url, self.adhan_files[prayer])
            
        except Exception as e:
            self.logger.error(f"Error downloading adhan for {prayer}: {e}")
            return False
    
    def _get_adhan_file(self, url: str) -> Optional[Path]:
        """Get cached adhan file or download if not cached"""
        if url in self.adhan_cache:
            return self.adhan_cache[url]
        
        # Generate a unique filename for the cached file
        cache_file = self.cache_dir / f"{hash(url)}.mp3"
        
        if not cache_file.exists():
            self.logger.info(f"Downloading adhan from {url} to cache")
            if not self._download_adhan(url, cache_file):
                return None
        
        self.adhan_cache[url] = cache_file
        return cache_file
    
    def load_volumes(self) -> None:
        """Load saved volumes from file"""
        self.volume = self._load_volume()
        pygame.mixer.music.set_volume(self.volume)
    
    def save_volumes(self) -> None:
        """Save current volumes to file"""
        self._save_volume()
    
    def _get_adhan_file_path(self, url: str) -> Optional[Path]:
        """Get cached adhan file path or generate a new one"""
        if url in self.adhan_cache:
            return self.adhan_cache[url]
        
        # Generate a unique filename for the cached file
        cache_file = self.cache_dir / f"{hash(url)}.mp3"
        
        if not cache_file.exists():
            self.logger.info(f"Downloading adhan from {url} to cache")
            if not self._download_adhan(url, cache_file):
                return None
        
        self.adhan_cache[url] = cache_file
        return cache_file 