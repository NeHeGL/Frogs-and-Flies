"""
Renderer - Handles scanline-by-scanline rendering
Converts the assembly display kernel logic to Python
"""

from tia_emulator import COLORS, decode_playfield_scanline
from graphics_data import (GRAPHICS_ROM, LFEB5_TABLE, SCORE_DIGIT_OFFSET, 
                           SCORE_DIGIT_OFFSET_WIDE, SCORE_DIGIT_OFFSET_NARROW,
                           get_frog_sprite, PF0_BASE_OFFSET, PF1_BASE_OFFSET, 
                           PF2_BASE_OFFSET, PLAYFIELD_COLORS, SCORE_COLORS,
                           FIREFLY_SIZE, FIREFLY_COLOR_INDEX, SPRITE_POINTER_MAP)


class GraphicsData:
    """Contains all graphics data extracted from the ROM."""
    def __init__(self):
        # Full ROM graphics data
        self.rom = GRAPHICS_ROM
        
        # Import data tables from graphics_data module
        self.score_digit_offset = SCORE_DIGIT_OFFSET
        self.playfield_colors = PLAYFIELD_COLORS
        self.score_colors = SCORE_COLORS
        self.lfeb5_table = LFEB5_TABLE
        self.pf0_base_offset = PF0_BASE_OFFSET
        self.pf1_base_offset = PF1_BASE_OFFSET
        self.pf2_base_offset = PF2_BASE_OFFSET
        
    def get_score_digit(self, digit, scanline, use_narrow=False):
        """
        Get a scanline of a score digit (0-9).
        
        Args:
            digit: Digit 0-9
            scanline: Scanline 0-4
            use_narrow: If True, use narrow font (lower nibble), else wide font (upper nibble)
        """
        if digit < 0 or digit > 9 or scanline < 0 or scanline >= 5:
            return 0
        # Assembly: LDY #$04, then loops with DEY (reads Y=4,3,2,1,0)
        # First scanline drawn uses Y=4, last uses Y=0
        # We call with scanline=0 for first line, scanline=4 for last
        # So: our scanline 0 = assembly's Y=4, our scanline 4 = assembly's Y=0
        # Therefore: Y = 4 - scanline
        y_index = 4 - scanline
        
        # Choose font: wide (offset 89) or narrow (offset 139)
        base_offset = SCORE_DIGIT_OFFSET_NARROW if use_narrow else SCORE_DIGIT_OFFSET_WIDE
        offset = base_offset + (digit * 5) + y_index
        
        if offset < len(self.rom):
            return self.rom[offset]
        return 0
    
    def get_sprite_data(self, offset):
        """Get sprite data at a specific offset."""
        if 0 <= offset < len(self.rom):
            return self.rom[offset]
        return 0


class Renderer:
    """Handles rendering of each scanline."""
    def __init__(self, memory, width=160, height=192):
        self.memory = memory
        self.graphics = GraphicsData()
        self.width = width
        self.height = height
        # Sprite reflection flags (set by main game loop)
        self.p0_reflect = False
        self.p1_reflect = False
        # Hop animation frames (0 = sitting, 1-8 = hopping)
        self.p0_hop_frame = 0
        self.p1_hop_frame = 0
        # Track previous Y positions for animation
        self.p0_prev_y = 0x99
        self.p1_prev_y = 0x99
        # Actual screen positions (scanlines 0-192) - updated during rendering
        self.p0_screen_y = 0
        self.p1_screen_y = 0
        self.fly0_screen_y = 0
        self.fly1_screen_y = 0
        # Debug visualization toggle
        self.show_collision_boxes = False
        
        # TIA collision detection - track pixels per player tongue and per fly
        # Split by player so we know WHICH frog's tongue hit WHICH fly
        self.p0_ball_pixels = set()  # (x, y) tuples where P0 tongue is drawn
        self.p1_ball_pixels = set()  # (x, y) tuples where P1 tongue is drawn
        self.missile0_pixels = set()  # (x, y) tuples where fly 0 is drawn
        self.missile1_pixels = set()  # (x, y) tuples where fly 1 is drawn
        # Keep combined set for debug rendering
        self.ball_pixels = set()

    def clear_collision_tracking(self):
        """Clear collision pixel tracking at start of frame."""
        self.p0_ball_pixels.clear()
        self.p1_ball_pixels.clear()
        self.ball_pixels.clear()
        self.missile0_pixels.clear()
        self.missile1_pixels.clear()
        # Clear TIA collision registers
        self.memory.write(0x02, 0x00)  # CXM0FB
        self.memory.write(0x03, 0x00)  # CXM1FB
        # Clear per-fly collision player attribution ($F0=fly0 catcher, $F1=fly1 catcher)
        # 0xFF = no collision yet
        self.memory.write(0xF0, 0xFF)
        self.memory.write(0xF1, 0xFF)

    def render_scanline(self, scanline_num):
        """
        Render a single scanline at 192-line resolution.
        Returns a list of RGB tuples (one per pixel).
        
        Scanline structure (192 total - double resolution):
        - 0-3: Blank (4 WSYNC, doubled from 2)
        - 4-17: Score area (14 scanlines, doubled from 7)
        - 18-21: Gap (4 WSYNC, doubled from 2)
        - 22-191: Playfield (170 scanlines, doubled from 85)
        
        IMPORTANT: Playfield (including scores) renders with each line DOUBLED
        Sprites render at full resolution (single lines)
        """
        # Get background color
        bg_color_index = self.memory.read(0x09)
        bg_color = COLORS.get(bg_color_index, (0, 0, 0))
        
        # Create scanline buffer (160 pixels wide)
        scanline = [bg_color] * self.width
        
        # Render based on scanline number (doubled resolution)
        if 0 <= scanline_num <= 21:
            # Score section: scanlines 0-21 (doubled from 0-10)
            # Set background to $87 for entire score section
            score_bg_index = self.memory.read(0x87)
            score_bg_color = COLORS.get(score_bg_index, (0, 0, 0))
            for i in range(len(scanline)):
                scanline[i] = score_bg_color
            
            # Render score digits only on scanlines 4-17 (doubled from 2-8)
            # Each score line renders TWICE (chunky playfield effect)
            if 4 <= scanline_num <= 17:
                # Divide by 2 to get original scanline (4-5→2, 6-7→3, etc.)
                original_scanline = (scanline_num - 4) // 2 + 2  # Maps to 2-8
                scanline_to_digit = [0, 0, 1, 2, 3, 4, 4]  # Index 0-6 maps to Y values
                rel_scanline = original_scanline - 2  # 0-6
                digit_line = scanline_to_digit[rel_scanline]
                self.render_score_digits(scanline, digit_line)
        elif scanline_num >= 22:
            # Playfield starts at scanline 22 (doubled from 11)
            self.render_playfield(scanline, scanline_num)
            # Render tongues BEFORE sprites so frog covers the tongue base
            self.render_tongues(scanline, scanline_num)
            # Render sprites on top of playfield (at full resolution - NOT doubled)
            self.render_sprites(scanline, scanline_num)
        
        # Render fireflies on top of everything (all scanlines)
        self.render_fireflies(scanline, scanline_num)
        
        # DEBUG: Render collision boxes (semi-transparent)
        self.render_collision_debug(scanline, scanline_num)
        
        return scanline
    
    def render_score_digits(self, scanline, scanline_num):
        """Render the score digits (called only for scanlines 2-8)."""
        # Get light blue background color from $87
        bg_color_index = self.memory.read(0x87)
        bg_color = COLORS.get(bg_color_index, (0, 0, 0))
        
        # Fill scanline with light blue background
        for i in range(len(scanline)):
            scanline[i] = bg_color
        
        # Get score colors: $88 for left (grey), $89 for right (orange)
        left_color_index = self.memory.read(0x88)
        right_color_index = self.memory.read(0x89)
        left_color = COLORS.get(left_color_index, (255, 255, 255))
        right_color = COLORS.get(right_color_index, (255, 255, 255))
        
        # Render score digits using PF1 register (matching assembly logic)
        # Assembly writes PF1 twice per scanline: once for left, once for right
        if scanline_num < 5:
            # Get scores (BCD format)
            score1 = self.memory.read(0xBB)
            score2 = self.memory.read(0xBC)
            
            # Extract digits
            p1_tens = (score1 >> 4) & 0x0F
            p1_ones = score1 & 0x0F
            p2_tens = (score2 >> 4) & 0x0F
            p2_ones = score2 & 0x0F
            
            # Get digit graphics data using BOTH fonts!
            # Tens uses WIDE font (upper nibble already in bits 7-4)
            # Ones uses NARROW font (lower nibble already in bits 3-0)
            p1_tens_data = self.graphics.get_score_digit(p1_tens, scanline_num, use_narrow=False)
            p1_ones_data = self.graphics.get_score_digit(p1_ones, scanline_num, use_narrow=True)
            p2_tens_data = self.graphics.get_score_digit(p2_tens, scanline_num, use_narrow=False)
            p2_ones_data = self.graphics.get_score_digit(p2_ones, scanline_num, use_narrow=True)
            
            # Assembly: LDA ($8A),Y / EOR ($8C),Y / STA PF1
            # XORs tens (wide font, upper nibble) with ones (narrow font, lower nibble)
            # This combines two different-sized digits into one PF1 byte!
            p1_combined = p1_tens_data ^ p1_ones_data
            p2_combined = p2_tens_data ^ p2_ones_data
            
            # Render using PF1 register positioning (assembly method)
            self.render_pf1_score(scanline, p1_combined, left_color, is_right_side=False)
            self.render_pf1_score(scanline, p2_combined, right_color, is_right_side=True)
    
    def render_pf1_score(self, scanline, pf1_data, color, is_right_side=False):
        """
        Render PF1 register data for score display.
        
        PF1 bit mapping (from TIA spec):
        - Bit 7 → pixels 16-19 (left half) or 112-115 (right half mirrored)
        - Bit 6 → pixels 20-23 or 116-119
        - Bit 5 → pixels 24-27 or 120-123
        - Bit 4 → pixels 28-31 or 124-127
        - Bit 3 → pixels 32-35 or 128-131
        - Bit 2 → pixels 36-39 or 132-135
        - Bit 1 → pixels 40-43 or 136-139
        - Bit 0 → pixels 44-47 or 140-143
        
        Score digits only use upper 4 bits (7-4).
        PF1 has NORMAL bit order (bit 7 leftmost, bit 0 rightmost).
        """
        # PF1 starts at pixel 16 (left) or 112 (right with mirroring)
        base_x = 112 if is_right_side else 16
        
        # Render each bit of PF1 (bits 7-0, left to right - NORMAL order)
        for bit in range(8):
            if (pf1_data >> (7 - bit)) & 1:
                # Each bit = 4 pixels wide
                pixel_start = base_x + (bit * 4)
                for dx in range(4):
                    pixel_x = pixel_start + dx
                    if 0 <= pixel_x < len(scanline):
                        scanline[pixel_x] = color
    
    def render_sprites(self, scanline, scanline_num):
        """
        Render player sprites (frogs) on the scanline.
        
        COORDINATE SYSTEM EXPLANATION:
        ==============================
        The ROM uses an INVERTED Y coordinate system where:
        - Y=0 is at the BOTTOM of the playfield (water level)
        - Higher Y values go UP toward the top of the screen
        - Y=7 (0x07) is the lily pad position (near bottom)
        - Y=82 (0x52) would be near the top
        
        Assembly code at $F7F1-$F7F4 converts this to screen coordinates:
            LDA #$52      ; Load 82 (max Y value)
            SEC           ; Set carry for subtraction
            SBC $D7,X     ; Subtract frog Y position
        
        This inverts the Y axis: screen_y = (82 - rom_y)
        - ROM Y=7 (lily pad) → screen Y=75 → scanline 150 (doubled)
        - ROM Y=50 (mid-air) → screen Y=32 → scanline 64 (doubled)
        - ROM Y=82 (top) → screen Y=0 → scanline 0 (doubled)
        
        We double all values because our renderer uses 192 scanlines vs ROM's 96.
        
        Memory locations:
        - $D3 = Player 0 X position
        - $D7 = Player 0 Y position (ROM inverted coords, 7 = lily pad)
        - $D4 = Player 1 X position  
        - $D8 = Player 1 Y position (ROM inverted coords, 7 = lily pad)
        """
        # Read frog Y positions from memory (ROM's inverted coordinate system)
        p0_y_atari = self.memory.read(0xD7)
        p1_y_atari = self.memory.read(0xD8)
        
        # Convert ROM's inverted Y to screen coordinates, or hide if Y=0
        # Assembly formula: LDA #$52 / SEC / SBC $D7,X → screen_y = 82 - rom_y
        # NOTE: Only hide the individual frog when Y=0, never bail on both at once.
        # When P0 jumps off-screen (Y=0) during game-over, P1 may still be visible.
        # The *2 is because we render at 192 scanlines vs ROM's 96.
        p0_y = -100 if p0_y_atari == 0 else ((82 - p0_y_atari) * 2)
        p1_y = -100 if p1_y_atari == 0 else ((82 - p1_y_atari) * 2)


        
        # Read sprite pointers from memory (set by state machine)
        # F51B dynamically sets $DB/$DC based on Y position:
        # - 0xC9, 0xDB, 0xED, 0xFF (dynamic based on jump height)
        # - 0xB7 (sitting), 0x93 (hopping) - legacy pointers
        # - 0x81, 0x6F, 0x5D, 0x4B (splash animation frames)
        p0_sprite_ptr = self.memory.read(0xDB)
        p1_sprite_ptr = self.memory.read(0xDC)
        
        # ATARI SPRITE HEIGHT CALCULATION (from assembly $F800-$F806):
        # The assembly calculates: sprite_data_index = sprite_pointer - (Y_position × 2)
        # This index determines how many scanlines of sprite data to render
        # When Y decreases (sinking from 7 to 0), index increases, rendering FEWER lines
        # 
        # Example with sitting sprite (ptr=0xB7=183):
        # - Y=7 (lily pad): index = 183 - 14 = 169, renders ~14 lines
        # - Y=3 (sinking):  index = 183 - 6 = 177, renders ~6 lines  
        # - Y=0 (underwater): index = 183 - 0 = 183, renders 0 lines (hidden)
        #
        # The sprite data is 16 bytes, indexed 0-15
        # The kernel reads with Y counting down from the calculated index
        # So effective_height = 16 - (sprite_ptr - (Y_pos × 2) - base_index)
        
        p0_data_index = p0_sprite_ptr - (p0_y_atari * 2)
        p1_data_index = p1_sprite_ptr - (p1_y_atari * 2) if p1_y_atari != 0 else p1_sprite_ptr
        
        # Use SPRITE_POINTER_MAP to get ROM offset
        # Map sprite pointer to ROM offset, defaulting to sitting sprite
        p0_offset = SPRITE_POINTER_MAP.get(p0_sprite_ptr, 517)
        p1_offset = SPRITE_POINTER_MAP.get(p1_sprite_ptr, 517)
        
        # Calculate sprite height based on the data index
        # The sprite pointer value represents the LAST byte of sprite data
        # So: height = sprite_pointer - data_index
        # This gives us how many bytes to read from the sprite
        # Add 2 to account for the sprite pointer offset (empirically determined)
        # At Y=7 (lily pad): ptr=0xB7, index=0xA9, height=14+2=16 (full sprite)
        # At Y=0 (underwater): ptr=0xB7, index=0xB7, height=0+2=2 (mostly hidden)
        p0_height = (p0_sprite_ptr - p0_data_index) + 2
        p1_height = (p1_sprite_ptr - p1_data_index) + 2
        
        # Clamp to valid range (0-16)
        p0_height = max(0, min(16, p0_height))
        p1_height = max(0, min(16, p1_height))
        
        # Read sprite data directly from ROM at the offset
        # Read the LAST p0_height bytes of the 16-byte sprite
        p0_sprite = GRAPHICS_ROM[p0_offset + (16 - p0_height):p0_offset + 16]
        p1_sprite = GRAPHICS_ROM[p1_offset + (16 - p1_height):p1_offset + 16]
        
        # Get frog X positions from memory
        # CONFIRMED: X and Y are swapped!
        # $D3/$D4 = X positions, $D7/$D8 = Y positions
        p0_x = self.memory.read(0xD3)  # X position
        p1_x = self.memory.read(0xD4)  # X position
        # Y positions already retrieved above
        
        # Get sprite colors from memory
        p0_color_index = self.memory.read(0x06)  # COLUP0
        p1_color_index = self.memory.read(0x07)  # COLUP1
        p0_color = COLORS.get(p0_color_index, (128, 128, 128))
        p1_color = COLORS.get(p1_color_index, (255, 0, 0))
        
        # Use reflection flags passed from main game loop
        p0_reflect = self.p0_reflect
        p1_reflect = self.p1_reflect
        
        # Get NUSIZ registers to check for multiple sprite copies
        nusiz0 = self.memory.read(0x04) & 0x07  # NUSIZ0 - lower 3 bits
        nusiz1 = self.memory.read(0x05) & 0x07  # NUSIZ1 - lower 3 bits
        
        # Only render if NUSIZ is 0 (single copy) - ignore multiple copies for now
        # This prevents the vertical bars from appearing
        if nusiz0 != 0:
            p0_y = -100  # Move offscreen
        if nusiz1 != 0:
            p1_y = -100  # Move offscreen
        
        # Render Player 0 frog
        if p0_y <= scanline_num < p0_y + p0_height:
            sprite_line = scanline_num - p0_y
            # Assembly reads with Y counting down: Y=14 for first line, Y=0 for last
            # So: sprite_line 0 (top) = ROM byte 14, sprite_line 14 (bottom) = ROM byte 0
            y_index = p0_height - 1 - sprite_line
            sprite_data = p0_sprite[y_index]
            
            # Render 8 bits (standard Atari 2600 sprite width)
            for bit in range(8):
                if (sprite_data >> (7 - bit)) & 1:
                    # If reflected, flip the bit position horizontally
                    if p0_reflect:
                        pixel_x = p0_x + (7 - bit)
                    else:
                        pixel_x = p0_x + bit
                    if 0 <= pixel_x < len(scanline):
                        scanline[pixel_x] = p0_color
        
        # Render Player 1 frog
        if p1_y <= scanline_num < p1_y + p1_height:
            sprite_line = scanline_num - p1_y
            # Assembly reads with Y counting down
            y_index = p1_height - 1 - sprite_line
            sprite_data = p1_sprite[y_index]
            
            # Render 8 bits
            for bit in range(8):
                if (sprite_data >> (7 - bit)) & 1:
                    # If reflected, flip the bit position horizontally
                    if p1_reflect:
                        pixel_x = p1_x + (7 - bit)
                    else:
                        pixel_x = p1_x + bit
                    if 0 <= pixel_x < len(scanline):
                        scanline[pixel_x] = p1_color
    
    def render_playfield(self, scanline, scanline_num):
        """
        Render playfield in a single unified loop (trees, reeds, water, lily pads).
        
        Assembly structure:
        - Score area: 5 scanlines (LF0B6 loop with LDY #$04)
        - Main kernel (LF000): 74 scanlines counting down
        - Lily pad kernel (LF11B): 11 scanlines counting down  
        - Both kernels read from SAME continuous ROM data at $92/$94/$96 (PF0/PF1/PF2)
        - Separation is only for timing/sprite handling, NOT data organization
        
        ROM data layout (single continuous table):
        - ROM indices 0-10: Lily pads (bottom 11 scanlines)
        - ROM indices 11-84: Trees/reeds/water (top 74 scanlines)
        - Total: 85 scanlines, all rendered in this single loop
        
        Scanline mapping (96 scanlines total):
        - scanline_num 0-1: Blank gap (2 WSYNC before scores)
        - scanline_num 2-8: Score area (7 scanlines with 1.5x stretch)
        - scanline_num 9-10: Gap after scores (2 WSYNC)
        - scanline_num 11-95: Main playfield kernel (85 scanlines from ROM)
        
        Note: Both kernels read from same ROM data, just different loop structures
        """
        # Calculate playfield-relative scanline
        # Playfield kernel starts at absolute scanline 22 (doubled from 11)
        if scanline_num < 22:
            return  # Background only (blank or score gap scanlines)
        
        # Divide by 2 to get original playfield scanline (each ROM line renders twice)
        # Scanlines 22-23 → playfield 0, 24-25 → playfield 1, etc.
        playfield_scanline = (scanline_num - 22) // 2  # 0-based from start of playfield
        
        # Map to ROM index: playfield 0→ROM 84, playfield 84→ROM 0
        # Main kernel renders ROM indices 84 down to 11 (74 scanlines)
        # Lily pad kernel renders ROM indices 10 down to 0 (11 scanlines)
        y_index = 84 - playfield_scanline
        
        if y_index < 0:
            return  # Beyond playfield data
        
        # Get color index from LFEB5 table (determines bg/pf colors per scanline)
        y_value = y_index - 10

        
        # Clamp to valid LFEB5 range
        if y_value < 0:
            y_value = 0
        elif y_value >= len(self.graphics.lfeb5_table):
            y_value = len(self.graphics.lfeb5_table) - 1
        
        color_idx = self.graphics.lfeb5_table[y_value]
        
        # Get background and playfield colors from memory
        # SWAPPED: $9C holds background colors, $98 holds playfield colors
        bg_color_index = self.memory.read(0x9C + color_idx)
        pf_color_index = self.memory.read(0x98 + color_idx)
        
        bg_color = COLORS.get(bg_color_index, (0, 0, 0))
        pf_color = COLORS.get(pf_color_index, (0, 0, 0))
        
        # Set background color for this scanline
        for i in range(len(scanline)):
            scanline[i] = bg_color
        
        # Get playfield data from ROM using imported base offsets
        pf0_offset = self.graphics.pf0_base_offset + y_index
        pf1_offset = self.graphics.pf1_base_offset + y_index
        pf2_offset = self.graphics.pf2_base_offset + y_index
        
        pf0 = self.graphics.get_sprite_data(pf0_offset)
        pf1 = self.graphics.get_sprite_data(pf1_offset)
        pf2 = self.graphics.get_sprite_data(pf2_offset)
        
        # XOR with $80 if needed
        xor_mask = self.memory.read(0x80)
        pf0 ^= xor_mask
        pf1 ^= xor_mask
        pf2 ^= xor_mask
        
        # Decode playfield with mirroring
        pf_pixels = decode_playfield_scanline(pf0, pf1, pf2, reflect=True)
        
        # Render playfield pixels
        for i, pf_pixel in enumerate(pf_pixels):
            if pf_pixel:
                for j in range(4):
                    x = i * 4 + j
                    if 0 <= x < len(scanline):
                        scanline[x] = pf_color
    
    def render_fireflies(self, scanline, scanline_num):
        """
        Render fireflies using missiles (ENAM0, ENAM1).
        
        COORDINATE SYSTEM EXPLANATION:
        ==============================
        Fireflies use NORMAL (non-inverted) Y coordinates where:
        - Y=0 is at the TOP of the screen
        - Higher Y values go DOWN toward the bottom
        - This is OPPOSITE of the frog coordinate system!
        
        Assembly code at $F7F9-$F7FB does NOT invert firefly Y:
        The firefly Y value in memory is used directly for positioning.
        We simply double it for our 192-scanline resolution.
        
        Formula: screen_y = firefly_y * 2
        - Firefly Y=10 → scanline 20
        - Firefly Y=50 → scanline 100
        - Firefly Y=80 → scanline 160
        
        Memory locations:
        - $D5 = Fly 0 X position
        - $D6 = Fly 1 X position
        - $D9 = Fly 0 Y position (0 = off screen, normal coords)
        - $DA = Fly 1 Y position (0 = off screen, normal coords)
        """
        # Get NUSIZ values to determine missile width
        nusiz0 = self.memory.read(0x04)
        nusiz1 = self.memory.read(0x05)

        # Decode missile width from NUSIZ (bits 4-5)
        # $10 = 2 pixels, $20 = 4 pixels, $30 = 8 pixels
        missile_widths = {0x00: 1, 0x10: 2, 0x20: 4, 0x30: 8}
        fly0_width = missile_widths.get(nusiz0 & 0x30, 1)
        fly1_width = missile_widths.get(nusiz1 & 0x30, 1)
        
        # Get fly X velocities to determine which way they're moving
        fly0_x_vel = self.memory.read(0xCD)
        fly1_x_vel = self.memory.read(0xCE)
        # Moving LEFT (negative) = vertical on LEFT side
        # Moving RIGHT (positive) = vertical on RIGHT side
        fly0_moving_left = bool(fly0_x_vel & 0x80)
        fly1_moving_left = bool(fly1_x_vel & 0x80)
        
        # Render fly 0
        fly0_x = self.memory.read(0xD5)
        fly0_y_atari = self.memory.read(0xD9)
        
        # Get frame counter for wing-flapping animation
        # Creates backwards L shape: alternates between vertical and horizontal
        b3 = self.memory.read(0xB3)
        show_vertical = bool(b3 & 0x02)  # When bit 1 is set, show vertical line
        
        # On the real Atari 2600, the display kernel swaps the P0/P1 sprite pointers
        # every frame (ASM line 1832-1839: LDX/LDY PointerB0, swap, LDX/LDY VarA4/A6, swap).
        # This means each fly alternates between COLUP0 and COLUP1 every frame,
        # so both flies visually flicker between BOTH frog colors — neither fly is
        # permanently one color. We simulate this by swapping which color each fly
        # uses based on the frame counter parity (b3 & 0x01).
        colup0 = self.memory.read(0x06)  # COLUP0 - player 0 / grey frog color
        colup1 = self.memory.read(0x07)  # COLUP1 - player 1 / red frog color
        if b3 & 0x01:
            fly0_color = COLORS.get(colup0, (200, 100, 0))
            fly1_color = COLORS.get(colup1, (200, 100, 0))
        else:
            fly0_color = COLORS.get(colup1, (200, 100, 0))
            fly1_color = COLORS.get(colup0, (200, 100, 0))
        
        # Only render if Y position is valid (not 0 or 0x50 which means off-screen)
        if fly0_y_atari != 0 and fly0_y_atari != 0x50:
            # Convert Atari Y to screen coordinates using the SAME formula as frogs.
            # ASM line F7E9: LDA #$52 / SEC / SBC <ArrayD9,X  → screen_y = 82 - fly_y_atari
            # Both frogs and flies use inverted coordinates (high Y = high on screen).
            # screen_y = (82 - atari_y) * 2
            fly0_y_screen = (82 - fly0_y_atari) * 2
            
            # Backwards L animation - 2 PERFECT SQUARE blocks alternating orientation
            # Each block is a perfect square: 2 pixels wide × 2 scanlines tall
            # Vertical frame: 2 blocks stacked vertically (2px × 4 scanlines total)
            # Horizontal frame: 2 blocks side-by-side (4px × 2 scanlines total)
            # The bottom-left corner stays constant creating the backwards L effect
            
            block_size = 2  # Perfect square: 2×2
            
            if show_vertical:
                # Vertical: 2 blocks stacked vertically
                # Position vertical line based on movement direction
                # Moving LEFT = vertical on LEFT (x offset 0)
                # Moving RIGHT = vertical on RIGHT (x offset 2)
                x_offset = 0 if fly0_moving_left else 2
                if fly0_y_screen - 3 <= scanline_num <= fly0_y_screen:
                    for dx in range(block_size):
                        pixel_x = fly0_x + x_offset + dx
                        if 0 <= pixel_x < len(scanline):
                            scanline[pixel_x] = fly0_color
                            self.missile0_pixels.add((pixel_x, scanline_num))
                            # Check per-player tongue collision with fly 0
                            pt = (pixel_x, scanline_num)
                            if pt in self.p0_ball_pixels:
                                self.memory.write(0x02, 0x80)
                                if self.memory.read(0xF0) == 0xFF:
                                    self.memory.write(0xF0, 0)  # P0 caught fly 0
                            elif pt in self.p1_ball_pixels:
                                self.memory.write(0x02, 0x80)
                                if self.memory.read(0xF0) == 0xFF:
                                    self.memory.write(0xF0, 1)  # P1 caught fly 0
            else:
                # Horizontal: 2 blocks side by side (always at bottom)
                if fly0_y_screen - 1 <= scanline_num <= fly0_y_screen:
                    for dx in range(block_size * 2):  # 4 pixels wide
                        pixel_x = fly0_x + dx
                        if 0 <= pixel_x < len(scanline):
                            scanline[pixel_x] = fly0_color
                            self.missile0_pixels.add((pixel_x, scanline_num))
                            pt = (pixel_x, scanline_num)
                            if pt in self.p0_ball_pixels:
                                self.memory.write(0x02, 0x80)
                                if self.memory.read(0xF0) == 0xFF:
                                    self.memory.write(0xF0, 0)
                            elif pt in self.p1_ball_pixels:
                                self.memory.write(0x02, 0x80)
                                if self.memory.read(0xF0) == 0xFF:
                                    self.memory.write(0xF0, 1)
        
        # Render fly 1
        fly1_x = self.memory.read(0xD6)
        fly1_y_atari = self.memory.read(0xDA)
        
        # Only render if Y position is valid (not 0 or 0x50 which means off-screen)
        if fly1_y_atari != 0 and fly1_y_atari != 0x50:
            # Convert Atari Y to screen coordinates using the SAME formula as frogs.
            # ASM line F7E9: LDA #$52 / SEC / SBC <ArrayD9,X  → screen_y = 82 - fly_y_atari
            # Both frogs and flies use inverted coordinates (high Y = high on screen).
            # screen_y = (82 - atari_y) * 2
            fly1_y_screen = (82 - fly1_y_atari) * 2
            
            # Backwards L animation - 2 PERFECT SQUARE blocks alternating orientation
            # Each block is a perfect square: 2 pixels wide × 2 scanlines tall
            # Vertical frame: 2 blocks stacked vertically (2px × 4 scanlines total)
            # Horizontal frame: 2 blocks side-by-side (4px × 2 scanlines total)
            # The bottom-left corner stays constant creating the backwards L effect
            
            block_size = 2  # Perfect square: 2×2
            
            if show_vertical:
                # Vertical: 2 blocks stacked vertically
                x_offset = 0 if fly1_moving_left else 2
                if fly1_y_screen - 3 <= scanline_num <= fly1_y_screen:
                    for dx in range(block_size):
                        pixel_x = fly1_x + x_offset + dx
                        if 0 <= pixel_x < len(scanline):
                            scanline[pixel_x] = fly1_color
                            self.missile1_pixels.add((pixel_x, scanline_num))
                            pt = (pixel_x, scanline_num)
                            if pt in self.p0_ball_pixels:
                                self.memory.write(0x03, 0x80)
                                if self.memory.read(0xF1) == 0xFF:
                                    self.memory.write(0xF1, 0)  # P0 caught fly 1
                            elif pt in self.p1_ball_pixels:
                                self.memory.write(0x03, 0x80)
                                if self.memory.read(0xF1) == 0xFF:
                                    self.memory.write(0xF1, 1)  # P1 caught fly 1
            else:
                # Horizontal: 2 blocks side by side (always at bottom)
                if fly1_y_screen - 1 <= scanline_num <= fly1_y_screen:
                    for dx in range(block_size * 2):  # 4 pixels wide
                        pixel_x = fly1_x + dx
                        if 0 <= pixel_x < len(scanline):
                            scanline[pixel_x] = fly1_color
                            self.missile1_pixels.add((pixel_x, scanline_num))
                            pt = (pixel_x, scanline_num)
                            if pt in self.p0_ball_pixels:
                                self.memory.write(0x03, 0x80)
                                if self.memory.read(0xF1) == 0xFF:
                                    self.memory.write(0xF1, 0)
                            elif pt in self.p1_ball_pixels:
                                self.memory.write(0x03, 0x80)
                                if self.memory.read(0xF1) == 0xFF:
                                    self.memory.write(0xF1, 1)
    
    def render_tongues(self, scanline, scanline_num):
        """
        Render frog tongues using the ball register (ENABL).
        
        COORDINATE SYSTEM EXPLANATION:
        ==============================
        Tongues use the SAME inverted Y coordinate system as frogs because
        they are positioned relative to the frog's mouth position.
        
        The tongue Y position is calculated from the frog's Y position:
        - Get frog Y from memory (ROM inverted coords)
        - Convert using same formula as frogs: (82 - frog_y) * 2
        - Add offset for mouth position (depends on sitting vs hopping sprite)
        
        Assembly details (LF826-LF856):
        - Tongue counter at $C1,X (counts down from 23 to 0)
        - Extension length from LF795 table: [04,06,08,08,08,08,06,04]
        - Ball uses COLUPF color (playfield color)
        - Horizontal position: frog_x ± offset (depends on facing direction)
        - Each frog has tongue flag in bit 1 of $C3,X
        """
        # Get ball color from playfield color (tongues use COLUPF)
        ball_color_index = self.memory.read(0x08)  # COLUPF
        ball_color = COLORS.get(ball_color_index, (255, 255, 255))
        
        # LF795 table - tongue extension offsets
        lf795_table = [0x04, 0x06, 0x08, 0x08, 0x08, 0x08, 0x06, 0x04]
        
        # Check both frogs for tongue animation
        # Each frog has its own tongue flag (bit 1 of $C3,X)
        for player_idx in range(2):
            # Check if this frog's tongue is active (bit 1 of flags)
            frog_flags = self.memory.read(0xC3 + player_idx)
            tongue_active = bool(frog_flags & 0x02)
            
            if not tongue_active:
                continue
            
            # Get tongue animation counter (counts down from 23 to 0)
            # CRITICAL: Always use $C7,X (tongue_delay_addr) for tongue counter
            tongue_counter = self.memory.read(0xC7 + player_idx)
            
            # Only render if counter is active (1-23)
            if tongue_counter == 0 or tongue_counter > 23:
                continue
            
            # Get frog position
            frog_x = self.memory.read(0xD3 + player_idx)
            frog_y_atari = self.memory.read(0xD7 + player_idx)
            
            # Convert frog Y to sprite-space screen coordinates (same as render_sprites).
            frog_y_screen = (82 - frog_y_atari) * 2
            
            # Get direction (bit 3 of flags = facing left)
            frog_flags = self.memory.read(0xC3 + player_idx)
            facing_left = bool(frog_flags & 0x08)
            
            # Get sprite pointer to determine which sprite and mouth position
            sprite_ptr = self.memory.read(0xDB + player_idx)
            
            # Map counter to table index (counter goes 23->0, we want index 0->7)
            table_index = min(7, max(0, (23 - tongue_counter) // 3))
            tongue_offset = lf795_table[table_index]
            
            # Tongue Y position (visual) - same coordinate system as the frog sprite.
            # Different sprites have different mouth positions:
            # - Sitting sprites (0xB7, 0xAC): mouth at frog_y + 9
            # - Low jump sprites (0xC9): mouth at frog_y + 4 (mid-height)
            # - Mid jump sprites (0xDB): mouth at frog_y + 6 (lower mid-height)
            # - High jump sprites (0xED, 0xFF): mouth at frog_y + 2 (highest)
            # - Legacy hopping sprite (0x93): mouth at frog_y + 2
            if sprite_ptr in {0xB7, 0xAC}:  # Sitting
                tongue_y_visual = frog_y_screen + 9
            elif sprite_ptr == 0xC9:  # Low jump
                tongue_y_visual = frog_y_screen + 4
            elif sprite_ptr == 0xDB:  # Mid jump (2 pixels lower than low jump)
                tongue_y_visual = frog_y_screen + 6
            else:  # High jumps (0xED, 0xFF, 0x93)
                tongue_y_visual = frog_y_screen + 2
            
            # Assembly logic (LF826-LF856):
            # If facing right: ball_x = frog_x + LF795[index] + 1
            # If facing left:  ball_x = frog_x - LF795[index] + 1
            # The ball is 8 pixels wide (CTRLPF = $31)
            if facing_left:
                ball_x = frog_x - tongue_offset + 1
            else:
                ball_x = frog_x + tongue_offset

            # True per-pixel collision: register tongue pixels on the exact visual
            # scanline only.  The fly pixels are also registered at their exact
            # rendered scanlines, so overlap detection is genuinely pixel-perfect.
            # We extend one scanline above and below only to cover the fly's 2-pixel
            # height (the fly spans scanline_y-1 to scanline_y, or scanline_y-3 to
            # scanline_y for the vertical frame), ensuring the tongue centre line
            # always intersects at least one fly scanline.
            TONGUE_HALF_HEIGHT = 1

            if abs(scanline_num - tongue_y_visual) <= TONGUE_HALF_HEIGHT:
                for dx in range(8):
                    pixel_x = ball_x + dx
                    if 0 <= pixel_x < len(scanline):
                        # Draw and register collision only on the exact centre scanline
                        if scanline_num == tongue_y_visual:
                            scanline[pixel_x] = ball_color
                        # Register collision pixels (centre ± 1 to overlap fly height)
                        pt = (pixel_x, scanline_num)
                        self.ball_pixels.add(pt)
                        if player_idx == 0:
                            self.p0_ball_pixels.add(pt)
                        else:
                            self.p1_ball_pixels.add(pt)
    
    def render_collision_debug(self, scanline, scanline_num):
        """
        Highlight the exact pixels used for collision detection.
        Tongue collision pixels → bright green.
        Fly collision pixels    → bright red.
        Called per-scanline so the pixels are painted directly into the scanline buffer.
        """
        if not self.show_collision_boxes:
            return

        TONGUE_COLOR = (0, 255, 80)   # bright green
        FLY_COLOR    = (255, 60, 60)  # bright red

        # Tongue pixels (both players combined)
        for (px, py) in self.ball_pixels:
            if py == scanline_num and 0 <= px < len(scanline):
                scanline[px] = TONGUE_COLOR

        # Fly 0 pixels
        for (px, py) in self.missile0_pixels:
            if py == scanline_num and 0 <= px < len(scanline):
                scanline[px] = FLY_COLOR

        # Fly 1 pixels
        for (px, py) in self.missile1_pixels:
            if py == scanline_num and 0 <= px < len(scanline):
                scanline[px] = FLY_COLOR
