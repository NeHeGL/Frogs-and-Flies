"""
Sound System for Frogs and Flies
Loads real game sounds from WAV files
"""

import pygame
import os
import sys
import random


def _resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        # Running as a PyInstaller bundle
        return os.path.join(sys._MEIPASS, relative_path)
    # Running in development
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


class SoundSystem:
    """
    Sound system using real extracted game sounds.
    
    Based on assembly analysis:
    - Y=$01: Catch fly (eat sound)
    - Y=$02: Tongue snap
    - Y=$04/$05: Ambient sounds (4 variations)
    - Game end sounds: Leave pads, end cricket
    """
    
    def __init__(self, sample_rate=22050):
        """Initialize the sound system."""
        pygame.mixer.init(frequency=sample_rate, size=-16, channels=2, buffer=512)
        pygame.mixer.music.set_volume(1.0)  # Set mixer volume to max
        self.sample_rate = sample_rate
        
        # Load sounds from sounds directory
        self.sounds = {}
        self.load_sounds()
        
        # Track last played sounds to avoid repeats
        self.last_catch_frame = -100
        self.last_snap_frame = -100
        self.frame_counter = 0
        
        # Ambient sound state
        self.ambient_timer = 0
        self.next_ambient_time = 180  # Frames until next ambient sound
        
    def load_sounds(self):
        """Load all sound effects from files."""
        sound_dir = _resource_path("sounds")
        
        # Try to load each sound type
        # You'll need to rename your extracted sounds to these names:
        # - tongue.wav (tongue snap)
        # - catch.wav (eat fly)
        # - ambient_1.wav, ambient_2.wav, ambient_3.wav, ambient_4.wav
        # - leave_pads.wav (frogs jumping off at game end)
        # - end_cricket.wav (cricket sound during THE END)
        
        sound_files = {
            'tongue_snap': 'tongue.wav',
            'catch_fly': 'catch.wav',
            'splash': 'splash.wav',
            'leave_pads': 'leave_pads.wav',
            'end_cricket': 'end_cricket.wav',
        }
        
        # Load main sounds
        for key, filename in sound_files.items():
            filepath = os.path.join(sound_dir, filename)
            if os.path.exists(filepath):
                try:
                    sound = pygame.mixer.Sound(filepath)
                    sound.set_volume(1.0)  # Normal volume (WAV files pre-amplified)
                    self.sounds[key] = sound
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")
                    self.sounds[key] = None
            else:
                print(f"Sound file not found: {filepath}")
                self.sounds[key] = None
        
        # Load ambient sounds (4 variations)
        self.sounds['ambient'] = []
        for i in range(1, 5):
            filename = f'ambient_{i}.wav'
            filepath = os.path.join(sound_dir, filename)
            if os.path.exists(filepath):
                try:
                    sound = pygame.mixer.Sound(filepath)
                    sound.set_volume(1.0)  # Normal volume (WAV files pre-amplified)
                    self.sounds['ambient'].append(sound)
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")
            else:
                print(f"Ambient sound not found: {filepath}")
        
        if not self.sounds['ambient']:
            print("No ambient sounds loaded")
    
    def play_catch_fly(self):
        """Play the catch fly (eat) sound."""
        # Prevent rapid repeats (at least 10 frames between plays)
        if self.frame_counter - self.last_catch_frame > 10:
            if self.sounds.get('catch_fly'):
                self.sounds['catch_fly'].play()
            self.last_catch_frame = self.frame_counter
    
    def play_tongue_snap(self):
        """Play the tongue snap sound."""
        # Prevent rapid repeats (at least 10 frames between plays)
        if self.frame_counter - self.last_snap_frame > 10:
            if self.sounds.get('tongue_snap'):
                self.sounds['tongue_snap'].play()
            self.last_snap_frame = self.frame_counter
    
    def play_splash(self):
        """Play the splash sound (frog falls in water)."""
        if self.sounds.get('splash'):
            self.sounds['splash'].play()
    
    def play_leave_pads(self):
        """Play the leave pads sound (frogs jumping off at game end)."""
        if self.sounds.get('leave_pads'):
            self.sounds['leave_pads'].play()
    
    def play_end_cricket(self):
        """
        Play the end cricket sound (during THE END animation).
        
        Based on assembly analysis at F356:
        - Sound index Y=$06 (cricket)
        - Duration from $FA62 table: $40 (64 frames)
        - Called every frame while both frogs in state 6
        - Re-triggers every 64 frames (~1 second at 60fps)
        
        The sound plays repeatedly during the game over sequence.
        """
        if self.sounds.get('end_cricket'):
            # Check if cricket sound is already playing
            # If not playing, start it
            if not pygame.mixer.Channel(7).get_busy():
                pygame.mixer.Channel(7).play(self.sounds['end_cricket'])
    
    def update_ambient(self):
        """
        Update background ambient sounds.
        
        Plays occasional ambient sounds (4 variations).
        """
        self.ambient_timer += 1
        
        # Occasionally play random ambient sound
        if self.ambient_timer >= self.next_ambient_time:
            if self.sounds.get('ambient') and len(self.sounds['ambient']) > 0:
                # Pick random ambient sound
                ambient_sound = random.choice(self.sounds['ambient'])
                ambient_sound.play()
            
            # Random interval between ambient sounds (3-6 seconds)
            self.next_ambient_time = self.ambient_timer + random.randint(180, 360)
    
    def update(self):
        """Update sound system (call once per frame)."""
        self.frame_counter += 1
        self.update_ambient()
    
    def cleanup(self):
        """Clean up sound system."""
        pygame.mixer.quit()


# Singleton instance
_sound_system = None

def get_sound_system():
    """Get the global sound system instance."""
    global _sound_system
    if _sound_system is None:
        _sound_system = SoundSystem()
    return _sound_system
