"""
Frogs and Flies - Main Game
Exact conversion from Atari 2600 assembly to Python
"""

import pygame
import sys
from tia_emulator import Memory
from display_kernel import Renderer
from frog_state_machine import FrogStateMachine
from firefly import FireflyManager
from collision import CollisionDetector
from sound_system import get_sound_system
from physics import Physics
import config


class FrogsAndFlies:
    """Main game class."""
    def __init__(self):
        # Set Windows AppUserModelID BEFORE pygame.init() so the taskbar
        # shows our custom icon instead of the generic Python icon.
        import os, sys
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    u'NeHe.FrogsAndFlies.1')
            except Exception:
                pass

        pygame.init()

        # Set window icon from frog sprite (works both in source and frozen exe)
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(base, 'frog_icon.ico')
        if os.path.exists(icon_path):
            icon = pygame.image.load(icon_path)
            pygame.display.set_icon(icon)
        
        # Screen setup
        self.width = 160
        self.height = 192
        self.scale_x = 4
        self.scale_y = 2
        
        # Configure display mode based on config
        if config.FULLSCREEN:
            # Get desktop resolution BEFORE switching to fullscreen
            info = pygame.display.Info()
            # Use explicit desktop dimensions with FULLSCREEN flag
            self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
        else:
            # Normal resizable windowed mode
            self.screen = pygame.display.set_mode((self.width * self.scale_x, self.height * self.scale_y), pygame.RESIZABLE)
        
        self.atari_screen = pygame.Surface((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.running = True
        
        self.memory = Memory()
        self.renderer = Renderer(self.memory, self.width, self.height)
        
        # Initialize game state first
        self.init_game_state()
        
        # Create state machines for both frogs
        self.frog_p0 = FrogStateMachine(self.memory, 0)
        self.frog_p1 = FrogStateMachine(self.memory, 1)
        
        # Create firefly manager
        self.firefly_manager = FireflyManager(self.memory)
        
        # Create collision detector
        self.collision_detector = CollisionDetector(self.memory)
        
        # Create physics system
        self.physics = Physics(self.memory)
        
        # Initialize joystick subsystem
        pygame.joystick.init()
        self.joysticks = []
        self._refresh_joysticks()
        
        # Initialize sound system
        self.sound = get_sound_system()
        
        # Game over sequence state
        # 0=playing, 1=frogs jumping off, 2=THE END animation
        self.game_over_state = 0
        self.game_over_timer = 0
        self.game_over_substate = 0  # For processing frogs one at a time
        self.the_end_x = 160  # Start off-screen right
        self.the_end_y = 52   # 8 pixels higher (was 60)
        self.jump_triggered = False  # Track if we've triggered the jump
        self.firefly_x = 160  # Firefly X position (separate from text)
        
        # Store original difficulty settings (bit 7 of flags) from config
        self.p0_original_difficulty = 0x80 if config.PLAYER_0_EASY_MODE else 0x00
        self.p1_original_difficulty = 0x80 if config.PLAYER_1_EASY_MODE else 0x00
        
        # Auto-tongue cooldown timers (prevent rapid firing)
        self.p0_auto_tongue_cooldown = 0
        self.p1_auto_tongue_cooldown = 0
        
        # Set initial window title with difficulty settings
        self.update_window_title()
        
    def update_colors_from_timer(self):
        """
        Update colors based on current timer level ($B7).
        As $B7 counts down from 6 to 0, the sky gets progressively darker.
        """
        # Color tables from ROM
        lf7a2_table = [
            0x00, 0x00, 0x00, 0x70, 0x90, 0x90, 0x90, 0x70,
            0x92, 0x92, 0x92, 0x72, 0x94, 0x94, 0x94, 0x72,
            0x96, 0x96, 0x96, 0x74, 0x98, 0x98, 0x98, 0x74,
            0x9A, 0x9A, 0x9A, 0x74
        ]
        lf79e_table = [0xC4, 0xE4, 0xC6, 0xC6]
        
        # Get timer/level for color offset
        timer_level = self.memory.read(0xB7)
        y_offset = timer_level * 4
        
        # Load colors (day mode - normal mapping)
        # LF7A2 → $98 (background), LF79E → $9C (playfield)
        for x in range(3, -1, -1):
            y_index = y_offset - 1 - (3 - x)
            bg_color = lf7a2_table[y_index]
            self.memory.write(0x98 + x, bg_color)
        
        for x in range(4):
            pf_color = lf79e_table[x]
            self.memory.write(0x9C + x, pf_color)
        
        self.memory.write(0x87, self.memory.read(0x98))
    
    def update_day_night_colors(self):
        """
        Update background and playfield colors based on day/night mode.
        
        Assembly code (LF867 for day, LF880 for night):
        Day/night mode ONLY swaps the color table assignments.
        $80 (XOR mask) is NOT related to day/night - it's used for other purposes.
        
        The key difference:
        - Day: LF7A2 → $98 (background), LF79E → $9C (playfield)
        - Night: LF7A2 → $9C (playfield), LF79E → $98 (background) [SWAPPED]
        
        This creates the night effect by swapping which colors are used for
        background vs playfield, making trees/reeds blue and water green/brown.
        
        Day/night determined by bit 0 of $E6:
        - Even values (bit 0 = 0) = Day
        - Odd values (bit 0 = 1) = Night
        """
        # Color tables from ROM
        lf7a2_table = [
            0x00, 0x00, 0x00, 0x70, 0x90, 0x90, 0x90, 0x70,
            0x92, 0x92, 0x92, 0x72, 0x94, 0x94, 0x94, 0x72,
            0x96, 0x96, 0x96, 0x74, 0x98, 0x98, 0x98, 0x74,
            0x9A, 0x9A, 0x9A, 0x74
        ]
        lf79e_table = [0xC4, 0xE4, 0xC6, 0xC6]
        
        # Get timer/level for color offset
        timer_level = self.memory.read(0xB7)
        y_offset = timer_level * 4
        
        # Check day/night mode (bit 0 of $E6)
        day_night_counter = self.memory.read(0xE6)
        is_night = bool(day_night_counter & 0x01)
        
        if is_night:
            # Night mode (LF880):
            # Swap the color tables ONLY (no XOR change)
            # LF7A2 → $9C (playfield), LF79E → $98 (background)
            for x in range(3, -1, -1):
                y_index = y_offset - 1 - (3 - x)
                pf_color = lf7a2_table[y_index]
                self.memory.write(0x9C + x, pf_color)
            
            for x in range(4):
                bg_color = lf79e_table[x]
                self.memory.write(0x98 + x, bg_color)
            
            # Set score background to $9C[0]
            self.memory.write(0x87, self.memory.read(0x9C))
        else:
            # Day mode (LF867):
            # Normal color mapping
            # LF7A2 → $98 (background), LF79E → $9C (playfield)
            for x in range(3, -1, -1):
                y_index = y_offset - 1 - (3 - x)
                bg_color = lf7a2_table[y_index]
                self.memory.write(0x98 + x, bg_color)
            
            for x in range(4):
                pf_color = lf79e_table[x]
                self.memory.write(0x9C + x, pf_color)
            
            # Set score background to $98[0]
            self.memory.write(0x87, self.memory.read(0x98))
    
    def init_game_state(self):
        """Initialize game variables."""
        self.memory.write(0x26, 0x01)
        # Player colors (COLUP0/COLUP1 used for frogs)
        self.memory.write(0x06, 0x04)  # COLUP0
        self.memory.write(0x07, 0x32)  # COLUP1
        self.memory.write(0x88, 0x06)
        self.memory.write(0x89, 0x36)
        self.memory.write(0x08, 0xCC)
        self.memory.write(0x09, 0x72)
        
        # Initialize day/night counter  
        self.memory.write(0xE6, 0x00)
        
        # Initialize timer system
        # $B7 = game timer (counts down from 6 to 0, controls sky darkness)
        # $B8 = frame counter (counts down from $1A, decrements $B7 when it reaches 0)
        self.memory.write(0xB7, 0x06)  # Start at level 6 (brightest sky)
        self.memory.write(0xB8, 0x1A)  # Frame counter
        
        # Initialize colors based on current timer level
        self.update_colors_from_timer()
        self.memory.write(0xBB, 0x00)
        self.memory.write(0xBC, 0x00)
        
        # Initialize frog positions on lily pads
        # Assembly at $F3D8: LDA #$3C / STA $D7 / STA $D8
        # Frogs start at Y=0x07 (7) in Atari coordinates (lily pad at bottom)
        self.memory.write(0xD3, 0x20)  # P0 X position
        self.memory.write(0xD4, 0x6E)  # P1 X position
        self.memory.write(0xD7, 0x07)  # P0 Y position (7 = lily pad in Atari coords)
        self.memory.write(0xD8, 0x07)  # P1 Y position (7 = lily pad in Atari coords)
        self.memory.write(0xDB, 0xB7)  # P0 sprite pointer
        self.memory.write(0xDC, 0xB7)  # P1 sprite pointer
        
        # Initialize frog state machine variables
        self.memory.write(0xC5, 0x00)  # P0 state = sitting
        self.memory.write(0xC6, 0x00)  # P1 state = sitting
        
        # Set bit 7 for EASY MODE (difficulty B) or clear for NORMAL MODE (difficulty A)
        # EASY MODE: 0x80 (bit 7 set) - frogs auto-land on opposite lily pad
        # NORMAL MODE: 0x00 (bit 7 clear) - frogs use directional jumps
        # Load difficulty from config file
        p0_flags = 0x80 if config.PLAYER_0_EASY_MODE else 0x00  # P0 difficulty
        p1_flags = (0x80 if config.PLAYER_1_EASY_MODE else 0x00) | 0x08  # P1 difficulty + facing left
        self.memory.write(0xC3, p0_flags)  # P0 flags
        self.memory.write(0xC4, p1_flags)  # P1 flags
        self.memory.write(0xCB, 0x00)  # P0 X velocity
        self.memory.write(0xCC, 0x00)  # P1 X velocity
        self.memory.write(0xCF, 0x00)  # P0 Y velocity
        self.memory.write(0xD0, 0x00)  # P1 Y velocity
        self.memory.write(0xBF, 0x00)  # P0 hop counter
        self.memory.write(0xC0, 0x00)  # P1 hop counter
        
        # Initialize attract mode / inactivity timers
        self.memory.write(0xBD, 0x0F)  # P0 inactivity timer
        self.memory.write(0xBE, 0x0F)  # P1 inactivity timer
        
        # Initialize joystick direction indices ($E0/$E1)
        # These MUST be initialized to valid values (0-7), not $FF
        # $FF means "no direction" and blocks jumping
        # Initialize to 0xFF (no direction) as default
        self.memory.write(0xE0, 0xFF)  # P0 direction index
        self.memory.write(0xE1, 0xFF)  # P1 direction index
        
        # Initialize previous joystick state ($E2/$E3) for change detection
        # CRITICAL: Must initialize to 0x0F (no input) to prevent false change on first frame
        self.memory.write(0xE2, 0x0F)  # P0 previous joystick state
        self.memory.write(0xE3, 0x0F)  # P1 previous joystick state
        
        self.memory.write(0x0B, 0x08)  # REFP0 - start reflected (backwards L)
        self.memory.write(0x0C, 0x08)  # REFP1 - start reflected (backwards L)
        self.memory.write(0x80, 0xFF)  # XOR mask - game starts with playfield inverted
        
        # Initialize NUSIZ for missile (firefly) width
        # From assembly LF8C4: LDY #$10 / STY NUSIZ0 / STY NUSIZ1
        # Bits 4-5 control missile width: $10=2px, $20=4px, $30=8px
        self.memory.write(0x04, 0x10)  # NUSIZ0 - double-width missile (2 pixels) for fly 0
        self.memory.write(0x05, 0x10)  # NUSIZ1 - double-width missile (2 pixels) for fly 1
        
        # Initialize button state memory for edge detection (ASM uses $DD,$DE)
        # 0x80 = button not pressed (bit 7 set), 0x00 = button pressed (bit 7 clear)
        self.memory.write(0xDD, 0x80)  # P0 button state (not pressed)
        self.memory.write(0xDE, 0x80)  # P1 button state (not pressed)
        
    def render_frame(self):
        """Render a complete frame."""
        # Clear collision tracking at start of frame (simulates TIA CXCLR)
        self.renderer.clear_collision_tracking()
        
        # Update reflection based on direction flag (bit 3 of $C3/$C4)
        p0_flags = self.memory.read(0xC3)
        p1_flags = self.memory.read(0xC4)
        self.renderer.p0_reflect = bool(p0_flags & 0x08)
        self.renderer.p1_reflect = bool(p1_flags & 0x08)
        
        # Update hop frame based on state (hopping = state 2, 6, 7, tongue = state 4)
        p0_state = self.memory.read(0xC5)
        p1_state = self.memory.read(0xC6)
        # Show hop sprite when hopping (state 2, 6, 7) or tongue out (state 4)
        self.renderer.p0_hop_frame = 1 if p0_state in [2, 4, 6, 7] else 0
        self.renderer.p1_hop_frame = 1 if p1_state in [2, 4, 6, 7] else 0
        
        for y in range(self.height):
            scanline_pixels = self.renderer.render_scanline(y)
            for x, color in enumerate(scanline_pixels):
                self.atari_screen.set_at((x, y), color)
        
        # Draw THE END graphics if in game over state 4
        game_over_flag = self.memory.read(0xB4)
        if game_over_flag != 0 and self.game_over_state == 4:
            self.draw_the_end_graphics()
        
        # Scale to current window size (supports resizable window)
        window_size = self.screen.get_size()
        scaled = pygame.transform.scale(self.atari_screen, window_size)
        self.screen.blit(scaled, (0, 0))
        
        # Apply CRT effect if enabled
        if config.CRT:
            self.apply_scanlines(window_size)
        
        pygame.display.flip()
    
    def apply_scanlines(self, window_size):
        """
        Apply CRT scanline effect to the screen.
        Always draws exactly ONE dark pixel row at the bottom of each scaled
        Atari scanline band. Using a fixed 1-pixel gap avoids the rounding
        artifact where some bands got a 2-pixel gap (visible as thicker lines).
        """
        width, height = window_size

        # How many physical pixels per Atari scanline (float)
        scale_y = height / self.height

        # Always exactly 1 dark pixel — no rounding variation
        overlay = pygame.Surface((width, 1), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 130))  # semi-transparent black

        for atari_line in range(self.height):
            # Bottom edge of this band in physical pixels
            band_bottom = round((atari_line + 1) * scale_y)
            gap_y = band_bottom - 1  # last physical row of this band
            if 0 <= gap_y < height:
                self.screen.blit(overlay, (0, gap_y))
    
    def update_window_title(self):
        """Update the window title to show current difficulty settings."""
        p0_flags = self.memory.read(0xC3)
        p1_flags = self.memory.read(0xC4)
        p0_mode = "Easy" if (p0_flags & 0x80) else "Normal"
        p1_mode = "Easy" if (p1_flags & 0x80) else "Normal"
        title = f"Frogs and Flies:  Player 1: {p0_mode}    Player 2: {p1_mode}"
        pygame.display.set_caption(title)

    def _toggle_difficulty(self, player_num):
        """Toggle difficulty (Easy/Normal) for a player and reset frog to home pad."""
        if player_num == 0:
            flags_addr, x_addr, y_addr, state_addr, sprite_addr = 0xC3, 0xD3, 0xD7, 0xC5, 0xDB
            vx_addr, vy_addr, timer_addr = 0xCB, 0xCF, 0xBD
            home_x, face_bit = 0x20, 0x00   # P0 faces right (clear bit 3)
            cfg_attr = 'PLAYER_0_EASY_MODE'
            label = "Player 1 (left frog)"
        else:
            flags_addr, x_addr, y_addr, state_addr, sprite_addr = 0xC4, 0xD4, 0xD8, 0xC6, 0xDC
            vx_addr, vy_addr, timer_addr = 0xCC, 0xD0, 0xBE
            home_x, face_bit = 0x6E, 0x08   # P1 faces left (set bit 3)
            cfg_attr = 'PLAYER_1_EASY_MODE'
            label = "Player 2 (right frog)"

        flags = self.memory.read(flags_addr)
        flags ^= 0x80                    # Toggle Easy/Normal
        self.memory.write(x_addr, home_x)
        self.memory.write(y_addr, 0x07)
        self.memory.write(state_addr, 0x00)
        self.memory.write(sprite_addr, 0xB7)
        self.memory.write(vx_addr, 0x00)
        self.memory.write(vy_addr, 0x00)
        if face_bit:
            flags |= face_bit            # Set facing bit
        else:
            flags &= ~0x08               # Clear facing bit
        flags &= ~0x40                   # Disable attract mode
        self.memory.write(flags_addr, flags)
        self.memory.write(timer_addr, 0x0F)
        mode = "EASY" if (flags & 0x80) else "NORMAL"
        print(f"{label} difficulty: {mode}")
        setattr(config, cfg_attr, bool(flags & 0x80))
        config.save_config()
        self.update_window_title()

    def _refresh_joysticks(self):
        """
        Detect and initialize all connected joysticks.
        Assignment is fixed by index: joystick 0 → Player 1, joystick 1 → Player 2.
        No user configuration needed — just plug in and play.
        """
        self.joysticks = []
        count = pygame.joystick.get_count()
        for i in range(count):
            joy = pygame.joystick.Joystick(i)
            joy.init()
            self.joysticks.append(joy)

        # Fixed assignment: index determines player, always
        config.JOYSTICK_P0 = 0 if count >= 1 else -1
        config.JOYSTICK_P1 = 1 if count >= 2 else -1

        if count == 0:
            print("No joysticks detected — both players using keyboard.")
        else:
            for i, joy in enumerate(self.joysticks):
                player = i + 1
                print(f"Joystick {i} → Player {player}: {joy.get_name()}")
            if count == 1:
                print("  Player 2: keyboard (Arrow keys + Right Shift)")

    def _read_joystick(self, joy_index):
        """
        Read direction + fire from a joystick (analog or d-pad).
        Returns (swcha_nibble, fire_pressed).
        Returns (0x0F, False) if joystick index is invalid.

        Axis mapping (same as arrow keys / WASD):
          Up    → clear bit 0
          Down  → clear bit 1
          Left  → clear bit 2
          Right → clear bit 3
        D-pad (hat) also supported.
        Any button = fire (tongue).
        """
        if joy_index < 0 or joy_index >= len(self.joysticks):
            return 0x0F, False
        try:
            joy = self.joysticks[joy_index]
            nibble = 0x0F
            DEAD_ZONE = 0.5
            num_buttons = joy.get_numbuttons()

            # --- Analog stick (axes 0=X, 1=Y) ---
            if joy.get_numaxes() >= 2:
                x_axis = joy.get_axis(0)
                y_axis = joy.get_axis(1)
                if y_axis < -DEAD_ZONE:   nibble &= ~0x01  # Up
                if y_axis > DEAD_ZONE:    nibble &= ~0x02  # Down
                if x_axis < -DEAD_ZONE:   nibble &= ~0x04  # Left
                if x_axis > DEAD_ZONE:    nibble &= ~0x08  # Right

            # --- D-pad / hat ---
            if joy.get_numhats() > 0:
                hx, hy = joy.get_hat(0)
                if hy > 0:   nibble &= ~0x01  # Up
                if hy < 0:   nibble &= ~0x02  # Down
                if hx < 0:   nibble &= ~0x04  # Left
                if hx > 0:   nibble &= ~0x08  # Right

            # --- Any button = fire (tongue) ---
            fire = any(joy.get_button(b) for b in range(num_buttons))

            return nibble, fire
        except Exception:
            return 0x0F, False
    
    def draw_the_end_graphics(self):
        """Draw THE END graphics to the atari_screen surface."""
        from graphics_data import get_the_end_sprites
        sprite_8, sprite_9, sprite_10, sprite_11 = get_the_end_sprites()
        
        # Draw yellow firefly pulling the text
        fly_x = self.firefly_x - 6
        fly_y = self.the_end_y + 7
        fly_color = (255, 255, 0)
        
        # Get frame counter for wing-flapping animation
        b3 = self.memory.read(0xB3)
        show_vertical = bool(b3 & 0x02)
        
        # Backwards L animation - 2 PERFECT SQUARE blocks
        block_size = 2
        
        if show_vertical:
            # Vertical: 2 blocks stacked vertically (2px × 4 scanlines total)
            for dy in range(4):
                for dx in range(block_size):
                    if 0 <= fly_x + dx < self.width and 0 <= fly_y - 3 + dy < self.height:
                        self.atari_screen.set_at((fly_x + dx, fly_y - 3 + dy), fly_color)
        else:
            # Horizontal: 2 blocks side by side (4px × 2 scanlines total)
            for dy in range(2):
                for dx in range(block_size * 2):
                    if 0 <= fly_x + dx < self.width and 0 <= fly_y - 1 + dy < self.height:
                        self.atari_screen.set_at((fly_x + dx, fly_y - 1 + dy), fly_color)
        
        # Draw THE END sprites (flipped vertically)
        # Top line "THE": sprite_9 + sprite_11
        for i, sprite_data in enumerate([sprite_9, sprite_11]):
            x_offset = i * 8
            reversed_sprite = list(reversed(sprite_data))
            for y_line, byte_val in enumerate(reversed_sprite):
                for bit in range(8):
                    if byte_val & (1 << (7 - bit)):
                        px = self.the_end_x + x_offset + bit
                        py = self.the_end_y + y_line
                        if 0 <= px < self.width and 0 <= py < self.height:
                            self.atari_screen.set_at((px, py), fly_color)
        
        # Bottom line "END": sprite_8 + sprite_10
        for i, sprite_data in enumerate([sprite_8, sprite_10]):
            x_offset = i * 8
            reversed_sprite = list(reversed(sprite_data))
            for y_line, byte_val in enumerate(reversed_sprite):
                for bit in range(8):
                    if byte_val & (1 << (7 - bit)):
                        px = self.the_end_x + x_offset + bit
                        py = self.the_end_y + 8 + y_line
                        if 0 <= px < self.width and 0 <= py < self.height:
                            self.atari_screen.set_at((px, py), fly_color)
    
    def update_attract_mode_ai(self):
        """
        Attract mode AI logic - matches original ASM at Subroutine_F304 / F2EF.

        F304: Check bit 6 ($40) of flags → attract mode active
        F308: LDA $B3 / AND #$0E → only act when ($B3 & $0E) == 0 (every 16 frames)
        F30E: DEC $BF,X (hop counter) → BNE return (only proceed when counter == 0)
        F312: JSR random → AND #$07 / ADC #$01 → new counter 1-8
        F31B: BPL → Subroutine_F2EF (easy-mode hop - sets velocities DIRECTLY):
              F2EF: LDY #$0A or #$F6 (X velocity based on facing)
              F2F9: STY $CB,X (X vel), LDA #$1A / STA $CF,X (Y vel)
              F2FF: LDA #$07 / STA $C5,X (state = 7 = easy-mode hop)

        Key insight: F2EF sets state/velocity DIRECTLY - it doesn't use E0/SWCHA.
        Only triggers when frog is sitting (state 0) per the gating at F304.
        """
        import random

        game_over_flag = self.memory.read(0xB4)
        if game_over_flag != 0:
            return

        b3 = self.memory.read(0xB3)

        # Only act every 16 frames.
        # From ROM: LDA $B3 / AND #$0E / BNE return
        # $0E = bits 1,2,3. These are ALL zero only when B3 mod 16 == 0 or 1.
        # To match the original (fires once per 16 frames) we only trigger on the
        # exact cycle where B3 mod 16 == 0 (not 1 as well).
        if (b3 & 0x0F) != 0:
            return

        for player_num in range(2):
            flags_addr = 0xC3 + player_num
            x_vel_addr = 0xCB + player_num   # $CB=P0 X vel, $CC=P1 X vel
            y_vel_addr = 0xCF + player_num   # $CF=P0 Y vel, $D0=P1 Y vel
            state_addr = 0xC5 + player_num
            hop_counter_addr = 0xBF + player_num

            flags = self.memory.read(flags_addr)
            state = self.memory.read(state_addr)

            # Only act if attract mode is enabled (bit 6 set)
            if not (flags & 0x40):
                continue

            # Ensure EASY MODE (bit 7) is on while in attract mode
            if not (flags & 0x80):
                flags |= 0x80
                self.memory.write(flags_addr, flags)

            # Frog must be sitting (state 0) before we can trigger a jump
            # (The ASM at F304 gates on the E0/E1 direction index being $FF,
            #  but in our implementation we gate directly on state == 0)
            if state != 0:
                continue

            # Decrement hop counter; only jump when it reaches 0
            hop_count = self.memory.read(hop_counter_addr)
            if hop_count > 0:
                hop_count -= 1
                self.memory.write(hop_counter_addr, hop_count)
                if hop_count > 0:
                    continue   # Still waiting

            # Counter reached 0 → set new random delay and trigger jump.
            # Exact ASM (F312-F316): JSR random / AND #$07 / CLC / ADC #$01
            # Result: new counter = (rand & 7) + 1  →  1-8
            # Then BPL → Subroutine_F2EF (always taken since result is 1-8, always positive)
            new_delay = (random.randint(0, 255) & 0x07) + 1
            self.memory.write(hop_counter_addr, new_delay)
            # No fly proximity check in original ASM - frogs just bounce back and forth

            # ---- Subroutine_F2EF equivalent ----
            # Set velocities and state DIRECTLY (no E0/SWCHA needed).
            facing_left = bool(flags & 0x08)
            if facing_left:
                x_vel = 0xF6   # signed -10: move right
            else:
                x_vel = 0x0A   # +10: move left

            self.memory.write(x_vel_addr, x_vel)   # X velocity
            self.memory.write(y_vel_addr, 0x1A)    # Y velocity (upward)
            self.memory.write(state_addr, 0x07)    # state 7 = easy-mode hop

            # Clear E0/E1 so handle_input doesn't interfere this frame
            self.memory.write(0xE0 + player_num, 0xFF)
    
    def check_auto_tongue(self):
        """
        Check if frog is near a fly and automatically activate tongue.
        
        Based on assembly code around LF6F5 and the automatic tongue activation logic.
        When a frog is close to a fly, bit 6 of $C3/$C4 is automatically set.
        """
        # Check both frogs
        for player_num in range(2):
            flags_addr = 0xC3 + player_num
            state_addr = 0xC5 + player_num
            tongue_delay_addr = 0xC7 + player_num
            frog_x = self.memory.read(0xD3 + player_num)
            frog_y = self.memory.read(0xD7 + player_num)
            state = self.memory.read(state_addr)
            flags = self.memory.read(flags_addr)
            
            # Auto-tongue works while jumping (states 1, 2, and 7)
            # State 1: hop start (normal mode), State 2: hopping, State 7: easy mode hop
            # Manual tongue can work in state 0 (sitting), but auto-tongue should not
            if state not in [1, 2, 7]:
                continue
            
            # Don't auto-tongue if tongue is already active (bit 1 of flags)
            # ASM F5A6: Checks bit 1 of flags (AND #$02), not counter!
            if flags & 0x02:  # If tongue flag (bit 1) is already set
                continue
            
            # Check distance to each fly
            for fly_num in range(2):
                fly_x = self.memory.read(0xD5 + fly_num)
                fly_y_atari = self.memory.read(0xD9 + fly_num)
                
                # Skip if fly is off-screen
                if fly_y_atari == 0 or fly_y_atari == 0x50:
                    continue
                
                # Both frogs and flies now use the SAME inverted coordinate system:
                # screen_y = (82 - atari_y) * 2  (higher atari_y = higher on screen).
                # So we can compare frog_y and fly_y_atari directly in Atari space.
                # X range: ~25 pixels, Y range: ~8 Atari units (each unit = 2 px on screen)
                x_diff = abs(frog_x - fly_x)
                y_diff = abs(frog_y - fly_y_atari)
                
                if x_diff < 25 and y_diff < 8:
                    # Fly is close - check cooldown before activating
                    cooldown = self.p0_auto_tongue_cooldown if player_num == 0 else self.p1_auto_tongue_cooldown
                    
                    # Only activate if cooldown expired AND tongue not already active
                    if cooldown == 0 and not (flags & 0x02):
                        self.memory.write(tongue_delay_addr, 8)  # Set counter to 8
                        self.memory.write(0x1F, 0x02)  # Set tongue display flag
                        flags |= 0x02  # Set bit 1 (tongue active flag)
                        self.memory.write(flags_addr, flags)
                        sound = get_sound_system()
                        sound.play_tongue_snap()
                        
                        # Set cooldown to prevent rapid re-firing (30 frames = 0.5 seconds)
                        if player_num == 0:
                            self.p0_auto_tongue_cooldown = 30
                        else:
                            self.p1_auto_tongue_cooldown = 30
                        break  # Only activate once per frame
    
    def decrement_tongue_counters(self):
        """
        Decrement tongue counter for ONE player per frame (alternating).
        Assembly: label_F55C (called from F1C7)
        
        F55C: LDA $B3 / AND #$01 / TAX - alternate between players
        F561: LDA $C7,X - load tongue counter
        F563: BEQ - skip if 0
        F565: DEC $C7,X - decrement counter
        """
        b3 = self.memory.read(0xB3)
        player = b3 & 0x01  # Alternate between 0 and 1
        
        tongue_delay_addr = 0xC7 + player
        tongue_counter = self.memory.read(tongue_delay_addr)
        
        if tongue_counter > 0:
            tongue_counter -= 1
            self.memory.write(tongue_delay_addr, tongue_counter)
            
            if tongue_counter == 0:
                # Clear tongue flag and display
                flags_addr = 0xC3 + player
                flags = self.memory.read(flags_addr)
                flags &= ~0x02
                self.memory.write(flags_addr, flags)
                self.memory.write(0x1F, 0x00)
    
    def update_frog_movement(self):
        """
        Update frog state machines.
        
        CRITICAL: Assembly (LF293) only updates ONE frog per frame!
        LDA $B3 / AND #$01 / TAX - alternates between player 0 and 1
        This is why velocities seemed too fast - I was updating both frogs every frame!
        
        Order from ASM (F1C1-F1CA):
        1. F1C1: Physics (F5B4)
        2. F1C4: State machine (F293)
        3. F1C7: Tongue counter (F55C)
        4. F1CA: Button handler (F5FD)
        """
        swcha = self.memory.read(0x0280)
        b3 = self.memory.read(0xB3)
        
        # Check for auto-tongue activation before updating state machine
        self.check_auto_tongue()
        
        # Only update one frog per frame (alternating based on $B3 & 0x01)
        if (b3 & 0x01) == 0:
            # Update Player 0 state machine
            joy_p0 = swcha & 0x0F
            self.frog_p0.update(joy_p0)
        else:
            # Update Player 1 state machine
            joy_p1 = (swcha >> 4) & 0x0F
            self.frog_p1.update(joy_p1)
        
        # Decrement tongue counters AFTER state machine (assembly F55C, called from F1C7 AFTER F293)
        self.decrement_tongue_counters()
    
    def handle_input(self):
        """Handle keyboard and joystick input."""
        # CRITICAL: Run attract mode AI FIRST, before processing keyboard
        # This allows AI to set joystick values that won't be overwritten
        self.update_attract_mode_ai()
        
        keys = pygame.key.get_pressed()
        
        # --- Player 0: WASD + Q (left/grey frog) ---
        swcha_p0 = 0x0F
        if keys[pygame.K_w]:  swcha_p0 &= ~0x01
        if keys[pygame.K_s]:  swcha_p0 &= ~0x02
        if keys[pygame.K_a]:  swcha_p0 &= ~0x04
        if keys[pygame.K_d]:  swcha_p0 &= ~0x08
        p0_kb_fire = keys[pygame.K_q]

        # --- Player 0: Joystick (merged with keyboard — both always active) ---
        joy0_nibble, joy0_fire = self._read_joystick(config.JOYSTICK_P0)
        swcha_p0 &= joy0_nibble          # AND merge: 0 wins (direction active from either source)
        p0_fire_raw = p0_kb_fire or joy0_fire
        # Combined input for attract-mode exit detection (either keyboard or joystick)
        p0_combined = swcha_p0

        # --- Player 1: Arrow keys + Right Shift (right/red frog) ---
        swcha_p1 = 0x0F
        if keys[pygame.K_UP]:     swcha_p1 &= ~0x01
        if keys[pygame.K_DOWN]:   swcha_p1 &= ~0x02
        if keys[pygame.K_LEFT]:   swcha_p1 &= ~0x04
        if keys[pygame.K_RIGHT]:  swcha_p1 &= ~0x08
        p1_kb_fire = keys[pygame.K_RSHIFT]

        # --- Player 1: Joystick (merged with keyboard — both always active) ---
        joy1_nibble, joy1_fire = self._read_joystick(config.JOYSTICK_P1)
        swcha_p1 &= joy1_nibble          # AND merge: 0 wins
        p1_fire_raw = p1_kb_fire or joy1_fire
        p1_combined = swcha_p1

        # --- Fire button edge detection (keyboard + joystick combined) ---
        # ASM uses $DD/$DE to store previous button state for edge detection.
        # Encoding: 0x80 = not pressed, 0x00 = pressed (bit 7 semantics).
        prev_p0_button = self.memory.read(0xDD)
        curr_p0_button = 0x00 if p0_fire_raw else 0x80
        self.memory.write(0xDD, curr_p0_button)
        if curr_p0_button == 0x00 and prev_p0_button == 0x80:
            p0_flags = self.memory.read(0xC3)
            if not (p0_flags & 0x02):
                self.memory.write(0xC7, 8)
                self.memory.write(0x1F, 0x02)
                p0_flags |= 0x02
                self.memory.write(0xC3, p0_flags)
                self.sound.play_tongue_snap()
            self.memory.write(0xBD, 0x0F)

        prev_p1_button = self.memory.read(0xDE)
        curr_p1_button = 0x00 if p1_fire_raw else 0x80
        self.memory.write(0xDE, curr_p1_button)
        if curr_p1_button == 0x00 and prev_p1_button == 0x80:
            p1_flags = self.memory.read(0xC4)
            if not (p1_flags & 0x02):
                self.memory.write(0xC8, 8)
                self.memory.write(0x1F, 0x02)
                p1_flags |= 0x02
                self.memory.write(0xC4, p1_flags)
                self.sound.play_tongue_snap()
            self.memory.write(0xBE, 0x0F)
        
        # Update attract mode timers FIRST (assembly code around LF6F5)
        # Decrement timers every 32 frames ($B3 & $1F == 0)
        # CRITICAL: Don't update timers if game is over
        game_over_flag = self.memory.read(0xB4)
        b3 = self.memory.read(0xB3)
        if (b3 & 0x1F) == 0 and game_over_flag == 0:
            # Decrement P0 timer
            p0_timer = self.memory.read(0xBD)
            if p0_timer > 0:
                p0_timer -= 1
                self.memory.write(0xBD, p0_timer)
                if p0_timer == 0:
                    # Timer expired - enable attract mode
                    p0_flags = self.memory.read(0xC3)
                    # Save original difficulty BEFORE AI takes over
                    self.p0_original_difficulty = p0_flags & 0x80
                    p0_flags |= 0x40  # Set bit 6 (attract mode enabled)
                    p0_flags &= ~0x08  # Clear bit 3 (face RIGHT)
                    self.memory.write(0xC3, p0_flags)
                    # Teleport to home lily pad (P0 = left pad at 0x20)
                    self.memory.write(0xD3, 0x20)
                    self.memory.write(0xD7, 0x07)  # Y position at lily pad
                    self.memory.write(0xC5, 0x00)  # Set state to sitting
            
            # Decrement P1 timer
            p1_timer = self.memory.read(0xBE)
            if p1_timer > 0:
                p1_timer -= 1
                self.memory.write(0xBE, p1_timer)
                if p1_timer == 0:
                    # Timer expired - enable attract mode
                    p1_flags = self.memory.read(0xC4)
                    # Save original difficulty BEFORE AI takes over
                    self.p1_original_difficulty = p1_flags & 0x80
                    p1_flags |= 0x40  # Set bit 6 (attract mode enabled)
                    p1_flags |= 0x08  # Set bit 3 (face LEFT)
                    self.memory.write(0xC4, p1_flags)
                    # Teleport to home lily pad (P1 = right pad at 0x6E)
                    self.memory.write(0xD4, 0x6E)
                    self.memory.write(0xD8, 0x07)  # Y position at lily pad
                    self.memory.write(0xC6, 0x00)  # Set state to sitting
        
        # NOW check attract mode status AFTER timers have run
        p0_flags = self.memory.read(0xC3)
        p1_flags = self.memory.read(0xC4)
        p0_attract = bool(p0_flags & 0x40)  # Check bit 6 (attract mode)
        p1_attract = bool(p1_flags & 0x40)  # Check bit 6 (attract mode)
        
        # Only update SWCHA for players NOT in attract mode
        # Read current SWCHA to preserve AI values
        swcha = self.memory.read(0x0280)
        if not p0_attract:
            # Update P0 nibble from keyboard
            swcha = (swcha & 0xF0) | swcha_p0
        if not p1_attract:
            # Update P1 nibble from keyboard
            swcha = (swcha & 0x0F) | (swcha_p1 << 4)
        self.memory.write(0x0280, swcha)
        
        # Emulate LF758 joystick read routine
        # This routine reads SWCHA and converts to direction index using LF748 table
        # Also handles attract mode / inactivity timer (assembly code at LF776)
        lf748_table = [0xFF,0xFF,0xFF,0xFF,0xFF,0x07,0x01,0x00,
                      0xFF,0x05,0x03,0x04,0xFF,0x06,0x02,0xFF]
        
        # Process Player 0 (lower nibble)
        # Read from actual SWCHA (which may have been set by AI)
        swcha = self.memory.read(0x0280)
        p0_joy = swcha & 0x0F
        p0_index = lf748_table[p0_joy]
        
        # Only check for input changes if NOT in attract mode
        if not p0_attract:
            # Check if keyboard input changed for P0 (to reset timer)
            prev_p0_joy = self.memory.read(0xE2)
            if p0_joy != prev_p0_joy and p0_joy != 0x0F:
                self.memory.write(0xBD, 0x0F)  # Reset timer to 15
            self.memory.write(0xE2, p0_joy)  # Store current input
        else:
            # In attract mode, check if REAL player input (keyboard OR joystick) to exit
            if p0_combined != 0x0F:
                p0_flags = (p0_flags & 0x7F) | self.p0_original_difficulty
                p0_flags &= ~0x40  # Clear bit 6 (disable attract mode)
                self.memory.write(0xC3, p0_flags)
                self.memory.write(0xBD, 0x0F)  # Reset timer to 15
                self.memory.write(0xE2, p0_combined)  # Store combined input
        
        # Only update direction index if NOT in attract mode (AI sets it)
        if not p0_attract:
            self.memory.write(0xE0, p0_index)  # Store in $E0
        
        # Process Player 1 (upper nibble)
        # Read from actual SWCHA (which may have been set by AI)
        p1_joy = (swcha >> 4) & 0x0F
        p1_index = lf748_table[p1_joy]
        
        # Only check for input changes if NOT in attract mode
        if not p1_attract:
            # Check if input changed for P1 (to reset timer)
            prev_p1_joy = self.memory.read(0xE3)
            if p1_joy != prev_p1_joy and p1_joy != 0x0F:
                self.memory.write(0xBE, 0x0F)  # Reset timer to 15
            self.memory.write(0xE3, p1_joy)  # Store current input
        else:
            # In attract mode, check if REAL player input (keyboard OR joystick) to exit
            if p1_combined != 0x0F:
                p1_flags = (p1_flags & 0x7F) | self.p1_original_difficulty
                p1_flags &= ~0x40  # Clear bit 6 (disable attract mode)
                self.memory.write(0xC4, p1_flags)
                self.memory.write(0xBE, 0x0F)  # Reset timer to 15
                self.memory.write(0xE3, p1_combined)  # Store combined input
        
        # Only update direction index if NOT in attract mode (AI sets it)
        if not p1_attract:
            self.memory.write(0xE1, p1_index)  # Store in $E1
        
    
    def run(self):
        """Main game loop."""
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    elif event.key == pygame.K_f:
                        # Toggle fullscreen - quit and reinitialize display
                        config.FULLSCREEN = not config.FULLSCREEN
                        
                        # Quit the display module
                        pygame.display.quit()
                        # Reinitialize display
                        pygame.display.init()
                        
                        if config.FULLSCREEN:
                            # Get desktop resolution for fullscreen
                            info = pygame.display.Info()
                            self.screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
                        else:
                            # Windowed mode with RESIZABLE
                            self.screen = pygame.display.set_mode((self.width * self.scale_x, self.height * self.scale_y), pygame.RESIZABLE)
                        
                        # Restore window title
                        self.update_window_title()
                        
                        print(f"Fullscreen: {'ON' if config.FULLSCREEN else 'OFF'}")
                        config.save_config()
                    elif event.key == pygame.K_c:
                        # Toggle CRT effect
                        config.CRT = not config.CRT
                        print(f"CRT Effect: {'ON' if config.CRT else 'OFF'}")
                        config.save_config()
                    elif event.key == pygame.K_b:
                        # Toggle bounding boxes
                        self.renderer.show_collision_boxes = not self.renderer.show_collision_boxes
                    elif event.key == pygame.K_1:
                        # Toggle Player 1 (left frog) difficulty
                        p0_flags = self.memory.read(0xC3)
                        p0_flags ^= 0x80  # Toggle bit 7 (EASY MODE)
                        # Reset P0 to starting position on left lily pad, facing right
                        self.memory.write(0xD3, 0x20)  # P0 X position (left pad)
                        self.memory.write(0xD7, 0x07)  # P0 Y position (lily pad)
                        self.memory.write(0xC5, 0x00)  # P0 state = sitting
                        self.memory.write(0xDB, 0xB7)  # P0 sprite = sitting
                        self.memory.write(0xCB, 0x00)  # P0 X velocity = 0
                        self.memory.write(0xCF, 0x00)  # P0 Y velocity = 0
                        p0_flags &= ~0x08  # Clear bit 3 (face RIGHT)
                        p0_flags &= ~0x40  # Clear bit 6 (disable attract mode)
                        self.memory.write(0xC3, p0_flags)
                        self.memory.write(0xBD, 0x0F)  # Reset inactivity timer
                        mode = "EASY" if (p0_flags & 0x80) else "NORMAL"
                        print(f"Player 1 (left frog) difficulty: {mode}")
                        # Update config and save
                        config.PLAYER_0_EASY_MODE = bool(p0_flags & 0x80)
                        config.save_config()
                        # Update window title
                        self.update_window_title()
                    elif event.key == pygame.K_2:
                        # Toggle Player 2 (right frog) difficulty
                        p1_flags = self.memory.read(0xC4)
                        p1_flags ^= 0x80  # Toggle bit 7 (EASY MODE)
                        # Reset P1 to starting position on right lily pad, facing left
                        self.memory.write(0xD4, 0x6E)  # P1 X position (right pad)
                        self.memory.write(0xD8, 0x07)  # P1 Y position (lily pad)
                        self.memory.write(0xC6, 0x00)  # P1 state = sitting
                        self.memory.write(0xDC, 0xB7)  # P1 sprite = sitting
                        self.memory.write(0xCC, 0x00)  # P1 X velocity = 0
                        self.memory.write(0xD0, 0x00)  # P1 Y velocity = 0
                        p1_flags |= 0x08  # Set bit 3 (face LEFT)
                        p1_flags &= ~0x40  # Clear bit 6 (disable attract mode)
                        self.memory.write(0xC4, p1_flags)
                        self.memory.write(0xBE, 0x0F)  # Reset inactivity timer
                        mode = "EASY" if (p1_flags & 0x80) else "NORMAL"
                        print(f"Player 2 (right frog) difficulty: {mode}")
                        # Update config and save
                        config.PLAYER_1_EASY_MODE = bool(p1_flags & 0x80)
                        config.save_config()
                        # Update window title
                        self.update_window_title()
                elif event.type == pygame.JOYDEVICEADDED:
                    print("Joystick connected - refreshing...")
                    self._refresh_joysticks()
                elif event.type == pygame.JOYDEVICEREMOVED:
                    print("Joystick disconnected - refreshing...")
                    self._refresh_joysticks()
                elif event.type == pygame.VIDEORESIZE:
                    # Handle window resize - update screen surface
                    self.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            
            # Check if game is over ($B4 flag)
            game_over_flag = self.memory.read(0xB4)
            
            if game_over_flag == 0:
                # Normal game play - update everything
                self.handle_input()
                # CRITICAL: Physics MUST run BEFORE state machine (assembly F1C1 then F1C4)
                self.physics.update()
                self.update_frog_movement()
                self.firefly_manager.update()
            else:
                # Game over sequence - disable BOTH fireflies
                # Set flies completely off-screen (both X and Y)
                self.memory.write(0xD5, 200)  # Fly 0 X off-screen right
                self.memory.write(0xD6, 200)  # Fly 1 X off-screen right
                self.memory.write(0xD9, 200)  # Fly 0 Y off-screen
                self.memory.write(0xDA, 200)  # Fly 1 Y off-screen
                
                # Game over sequence
                if self.game_over_state == 0:
                    # State 0: Wait for frogs to land naturally, then proceed
                    self.physics.update()
                    self.update_frog_movement()
                    
                    p0_state = self.memory.read(0xC5)
                    p1_state = self.memory.read(0xC6)
                    
                    if p0_state == 0 and p1_state == 0:
                        p0_x = self.memory.read(0xD3)
                        p1_x = self.memory.read(0xD4)
                        p0_needs_jump = (p0_x > 0x50)
                        p1_needs_jump = (p1_x < 0x50)
                        
                        if p0_needs_jump or p1_needs_jump:
                            self.game_over_state = 1
                            self.game_over_timer = 120
                            self.jump_triggered = False
                        else:
                            p0_flags = self.memory.read(0xC3)
                            p1_flags = self.memory.read(0xC4)
                            p0_flags &= ~0x08  # Face right
                            p1_flags |= 0x08   # Face left
                            self.memory.write(0xC3, p0_flags)
                            self.memory.write(0xC4, p1_flags)
                            self.game_over_state = 2
                            self.game_over_timer = 30

                elif self.game_over_state == 1:
                    # State 1: Frogs jumping to home lily pads
                    self.game_over_timer -= 1
                    
                    p0_x = self.memory.read(0xD3)
                    p1_x = self.memory.read(0xD4)
                    p0_state = self.memory.read(0xC5)
                    p1_state = self.memory.read(0xC6)
                    p0_needs_jump = (p0_x > 0x50)
                    p1_needs_jump = (p1_x < 0x50)
                    
                    if not self.jump_triggered:
                        lf748_table = [0xFF,0xFF,0xFF,0xFF,0xFF,0x07,0x01,0x00,
                                      0xFF,0x05,0x03,0x04,0xFF,0x06,0x02,0xFF]
                        p0_joy = 0x0F
                        p1_joy = 0x0F
                        if p0_needs_jump:
                            p0_joy &= ~0x02  # Press LEFT
                        if p1_needs_jump:
                            p1_joy &= ~0x01  # Press RIGHT
                        self.memory.write(0xE0, lf748_table[p0_joy])
                        self.memory.write(0xE1, lf748_table[p1_joy])
                        self.frog_p0.update(p0_joy)
                        self.frog_p1.update(p1_joy)
                        self.memory.write(0xE0, 0xFF)
                        self.memory.write(0xE1, 0xFF)
                        self.jump_triggered = True
                    else:
                        self.physics.update()
                        self.update_frog_movement()
                    
                    p0_state = self.memory.read(0xC5)
                    p1_state = self.memory.read(0xC6)
                    if p0_state == 0 and p1_state == 0:
                        self.memory.write(0xD3, 0x20)
                        self.memory.write(0xD4, 0x6E)
                        self.memory.write(0xD7, 0x07)
                        self.memory.write(0xD8, 0x07)
                        p0_flags = self.memory.read(0xC3)
                        p1_flags = self.memory.read(0xC4)
                        p0_flags &= ~0x08  # Face right
                        p1_flags |= 0x08   # Face left
                        self.memory.write(0xC3, p0_flags)
                        self.memory.write(0xC4, p1_flags)
                        self.game_over_state = 2
                        self.game_over_timer = 30

                elif self.game_over_state == 2:
                    # State 2: Brief pause then jump off
                    self.game_over_timer -= 1
                    if self.game_over_timer <= 0:
                        self.game_over_state = 3
                        self.game_over_timer = 90
                        self.game_over_substate = 0

                elif self.game_over_state == 3:
                    # State 3: Frogs jumping off screen - process ONE frog at a time
                    # Assembly F320-F349: Processes frogs alternately (one per frame)
                    self.game_over_timer -= 1
                    
                    # Substate 0: Process P0 first
                    if self.game_over_substate == 0:
                        # Play leave pads sound
                        self.sound.play_leave_pads()
                        
                        # Set P0 velocities and state.
                        # Physics formula: pixel_delta = ((vel + df_offset) >> 4) ^ 0x08 - 0x08
                        # P0 X: 0xE4 (228) → (228+df)>>4 = 14 → 14^8=6, 6-8=-2 → -2/frame LEFT
                        # P0 Y: 0x18 (24) → (24+df)>>4 = 1-2 → 1^8=9,9-8=1 → +1/frame UP
                        # At -2px/frame: ~16 frames to reach left edge from x=32
                        # At +1px/frame up with gravity slowing it: gentle arc
                        self.memory.write(0xCB, 0xE4)  # P0 X velocity (LEFT, gentle)
                        self.memory.write(0xCF, 0x18)  # P0 Y velocity (UP, gentle arc)
                        self.memory.write(0xC5, 0x06)  # P0 state = 6
                        self.memory.write(0xDB, 0x93)  # P0 sprite
                        
                        # Set P0 direction flags (assembly F320-F32B)
                        p0_flags = self.memory.read(0xC3)
                        p0_flags = (p0_flags & 0xFD) & 0xF7  # Clear bit 1 (tongue) and bit 3
                        p0_flags |= 0x08  # Set bit 3 (face LEFT)
                        self.memory.write(0xC3, p0_flags)
                        
                        self.game_over_substate = 1  # Move to P1 next frame
                        
                    # Substate 1: Process P1 (next frame)
                    elif self.game_over_substate == 1:
                        # Play sound again (both frogs now launching)
                        self.sound.play_leave_pads()
                        
                        # Set P1 velocities and state.
                        # P1 X: 0x20 (32) → (32+df)>>4 = 2-3 → 2^8=10,10-8=2 → +2/frame RIGHT
                        # P1 Y: 0x18 (24) → same +1/frame UP as P0
                        # At +2px/frame: ~23 frames to reach right edge from x=110
                        self.memory.write(0xCC, 0x20)  # P1 X velocity (RIGHT, gentle)
                        self.memory.write(0xD0, 0x18)  # P1 Y velocity (UP, gentle arc)
                        self.memory.write(0xC6, 0x06)  # P1 state = 6
                        self.memory.write(0xDC, 0x93)  # P1 sprite
                        
                        # Set P1 direction flags (assembly F320-F32F)
                        p1_flags = self.memory.read(0xC4)
                        p1_flags = (p1_flags & 0xFD) & 0xF7  # Clear bit 1 (tongue) and bit 3 (face RIGHT)
                        self.memory.write(0xC4, p1_flags)
                        
                        self.game_over_substate = 2  # Both frogs now jumping
                    
                    # Substate 2: Both frogs jumping
                    # CRITICAL: Use normal update order to avoid double gravity
                    # 1. Physics applies velocities to positions
                    # 2. State 6 applies gravity to velocities
                    
                    # Run physics FIRST to apply velocities
                    self.physics.update()
                    
                    # Then call state 6 for both frogs (applies gravity)
                    self.frog_p0.state_6_jump_off()
                    self.frog_p1.state_6_jump_off()
                    
                    if self.game_over_timer <= 0:
                        # Move frogs off-screen
                        self.memory.write(0xD3, 0)  # P0 off left
                        self.memory.write(0xD4, 200)  # P1 off right
                        self.memory.write(0xD7, 0)  # P0 off top
                        self.memory.write(0xD8, 0)  # P1 off top
                        self.game_over_state = 4
                        self.game_over_timer = 420  # 7 seconds for THE END animation (was 180/3 sec)
                        # Reset THE END animation positions
                        self.the_end_x = 160  # Start off-screen right
                        self.firefly_x = 160  # Firefly starts with text
                        # Play end cricket sound when THE END animation starts
                        self.sound.play_end_cricket()
                        
                elif self.game_over_state == 4:
                    # State 4: THE END text animation (firefly pulling text)
                    self.game_over_timer -= 1

                    # FIXED: Auto-reset game when animation completes
                    if self.game_over_timer <= 0:
                        # Reset game state
                        self.init_game_state()
                        self.game_over_state = 0
                        self.game_over_timer = 0
                        # Clear game over flag
                        self.memory.write(0xB4, 0x00)
                    else:
                        # Play cricket sound continuously (re-triggers when previous play finishes)
                        self.sound.play_end_cricket()

                        # Move THE END text from right to center
                        # Text is 16 pixels wide (2 sprites × 8px), center at 80 - 8 = 72
                        if self.the_end_x > 72 and (self.game_over_timer % 2) == 0:
                            self.the_end_x -= 1  # Move left 1 pixel every 2 frames
                            self.firefly_x -= 1  # Firefly moves with text
                        # After text stops, firefly continues moving left
                        elif self.the_end_x <= 72 and (self.game_over_timer % 2) == 0:
                            self.firefly_x -= 1  # Firefly keeps moving left
            
            # Update NUSIZ for missile (firefly) width (assembly code at LF8C4)
            # Alternates between $20 (4 pixels) and $10 (2 pixels) based on bit 1 of $B3
            b3 = self.memory.read(0xB3)
            if b3 & 0x02:  # Bit 1 set
                nusiz_value = 0x10  # 2 pixels (double-width)
            else:  # Bit 1 clear
                nusiz_value = 0x20  # 4 pixels (quad-width)
            self.memory.write(0x04, nusiz_value)  # NUSIZ0
            self.memory.write(0x05, nusiz_value)  # NUSIZ1
            
            # REFP0/REFP1 are set by frog direction (assembly F809-F80D)
            # Missiles (flies) inherit the same reflection as their corresponding frog
            # This is a hardware limitation of the Atari 2600 - REFP0 affects both P0 and M0
            # The flies don't have independent reflection control
            
            # Update timer system (assembly code at LF8F0)
            # Timer only decrements when ($B3 & 0x3F) == 0 (every 64 frames)
            # Only update timer if game is not over
            game_over_flag = self.memory.read(0xB4)
            if game_over_flag == 0:
                b3 = self.memory.read(0xB3)
                if (b3 & 0x3F) == 0:
                    # Decrement $B8 frame counter
                    b8 = self.memory.read(0xB8)
                    b8 = (b8 - 1) & 0xFF
                    self.memory.write(0xB8, b8)
                    
                    if b8 == 0:
                        # Reset frame counter and decrement game timer
                        self.memory.write(0xB8, 0x1A)
                        b7 = self.memory.read(0xB7)
                        b7 = (b7 - 1) & 0xFF
                        self.memory.write(0xB7, b7)
                        
                        if b7 == 0:
                            # Game over - timer expired (assembly code at LF90F)
                            # LF90F: INC $B7 (reset to 1, prevent underflow)
                            #        INC $B4 (set game over flag)
                            self.memory.write(0xB7, 0x01)  # Prevent underflow
                            self.memory.write(0xB4, 0x01)  # Set game over flag
                            # IMMEDIATELY disable flies when game over is triggered
                            self.memory.write(0xD9, 0)  # Disable fly 0 Y position
                            self.memory.write(0xDA, 0)  # Disable fly 1 Y position
                            # CRITICAL: Disable attract mode so frogs can land
                            p0_flags = self.memory.read(0xC3)
                            p1_flags = self.memory.read(0xC4)
                            p0_flags &= ~0x40  # Clear bit 6 (disable attract mode)
                            p1_flags &= ~0x40  # Clear bit 6 (disable attract mode)
                            self.memory.write(0xC3, p0_flags)
                            self.memory.write(0xC4, p1_flags)
                            # CRITICAL: Clear direction indices so frogs stop jumping
                            self.memory.write(0xE0, 0xFF)  # Clear P0 direction
                            self.memory.write(0xE1, 0xFF)  # Clear P1 direction
                            p0_score = self.memory.read(0xBB)
                            p1_score = self.memory.read(0xBC)
                        else:
                            # Update colors for new timer level (sky gets darker)
                            self.update_colors_from_timer()
            
            self.render_frame()
            
            # CRITICAL: Collision detection happens AFTER display kernel (ASM F19F)
            # TIA hardware detects collisions during rendering, then we read the registers
            if game_over_flag == 0:
                self.collision_detector.check_collisions()
            
            # Update sound system
            self.sound.update()
            
            # Decrement auto-tongue cooldown timers
            if self.p0_auto_tongue_cooldown > 0:
                self.p0_auto_tongue_cooldown -= 1
            if self.p1_auto_tongue_cooldown > 0:
                self.p1_auto_tongue_cooldown -= 1
            
            # Always increment frame counter (needed for firefly animation during game over)
            self.memory.ram[0xB3] = (self.memory.ram[0xB3] + 1) & 0xFF
            
            self.clock.tick(60)
        
        self.sound.cleanup()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    print("Frogs and Flies - Exact Conversion")
    print("===================================")
    print("Controls:")
    print("  Player 1 (left frog):  WASD to hop, Q for tongue")
    print("  Player 2 (right frog): Arrow keys to hop, Right Shift for tongue")
    print("  Joystick 0 → Player 1, Joystick 1 → Player 2 (plug in and play)")
    print("  Joystick: analog stick or d-pad to hop, any button for tongue")
    print("  1/2 = toggle difficulty | F = fullscreen | C = CRT scanlines | B = bounding boxes | ESC = quit")
    print()
    
    game = FrogsAndFlies()
    game.run()
