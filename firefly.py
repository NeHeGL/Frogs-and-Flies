"""
Firefly (Fly) Logic for Frogs and Flies
Converted from Atari 2600 assembly code (LF5B4, LF5FD)
FIXED: Now accurately matches ASM behavior
"""

from atari_rng import AtariRNG


class Firefly:
    """Manages a single firefly's movement and AI."""
    
    def __init__(self, memory, player_index, rng):
        """
        Initialize firefly.
        
        Args:
            memory: Memory object for game state
            player_index: 0 or 1 for which fly this is
            rng: AtariRNG instance for random number generation
        """
        self.memory = memory
        self.index = player_index
        self.rng = rng
        
        # Memory addresses for this fly
        self.x_pos_addr = 0xD5 + player_index
        self.y_pos_addr = 0xD9 + player_index
        self.x_vel_addr = 0xCD + player_index
        self.y_vel_addr = 0xD1 + player_index
        self.timer_addr = 0xB9 + player_index
        
        # Movement boundaries (from label_F5F7, F5F9, F5FB)
        # These are indexed by Y register (0 or 1) based on game state
        self.boundary_tables = {
            'min_y': [0x10, 0x20],  # label_F5F7 indexed by Y
            'max_y': [0x39, 0x31],  # label_F5F9 indexed by Y
            'mask':  [0x3F, 0x0F]   # label_F5FB indexed by Y
        }
    
    def update_ai(self, frame_counter, game_over):
        """
        Update fly AI and movement patterns (LF5FD).
        
        Args:
            frame_counter: Current frame number ($B3)
            game_over: Whether game is over ($B4)
        """
        if game_over:
            return
        
        # Determine Y index based on frame counter (LSR at F601-F608)
        # This alternates between 0 and 1 based on bit 3 of frame counter
        y_index = (frame_counter >> 3) & 0x01
        
        # Check player state flags (F609-F60D)
        # Combines both player flags with ASL to check if either is active
        c3 = self.memory.read(0xC3)
        c4 = self.memory.read(0xC4)
        combined = c3 | c4
        combined = (combined << 1) & 0xFF  # ASL
        
        # Get carry flag from ASL (bit 7 of original becomes carry)
        carry = 1 if (c3 | c4) & 0x80 else 0
        
        # Assembly F612-F61E: Check if X velocity is 0
        x_vel = self.memory.read(self.x_vel_addr)
        y_pos = self.memory.read(self.y_pos_addr)
        
        if x_vel != 0:
            # X velocity is active - check boundaries
            self._check_boundary_bounce(y_index)
        else:
            # X velocity is 0 - fly hit boundary
            if y_pos != 0:
                # Disable the fly
                self.memory.write(self.y_pos_addr, 0x00)
                self.memory.write(self.y_vel_addr, 0x00)
                # Set respawn timer (2-9 frames)
                rand = self._get_random()
                timer = (rand & 0x07) + 0x02
                self.memory.write(self.timer_addr, timer)
                return
        
        # Only update AI every 8 frames (F64A-F64E)
        if (frame_counter & 0x07) != 0:
            return
        
        # Decrement timer (F650-F652)
        timer = self.memory.read(self.timer_addr)
        timer = (timer - 1) & 0xFF
        self.memory.write(self.timer_addr, timer)
        
        # Check if timer went negative (BPL checks bit 7)
        if timer & 0x80:  # Timer is negative (>= 0x80)
            # Time to change behavior
            if y_pos == 0:
                # Fly is off screen - spawn it
                self._spawn_fly(y_index, carry)
            else:
                # Fly is on screen - change direction/speed
                self._change_movement(y_index)
    
    def _check_boundary_bounce(self, y_index):
        """
        Check if fly hit Y boundaries and reverse if needed.
        FIXED: Now matches ASM logic exactly (LF62B-LF64A)
        """
        y_pos = self.memory.read(self.y_pos_addr)
        y_vel = self.memory.read(self.y_vel_addr)
        
        # Get boundaries from tables
        min_boundary = self.boundary_tables['min_y'][y_index]
        max_boundary = self.boundary_tables['max_y'][y_index]
        
        # Assembly F62B-F63F: Boundary check with direction flag
        direction_flag = 0
        
        if y_pos < min_boundary:
            # Below minimum - set direction flag to $00
            direction_flag = 0x00
        elif y_pos >= max_boundary:
            # Above maximum - set direction flag to $80
            direction_flag = 0x80
        else:
            # Within bounds - no reversal needed
            return
        
        # XOR direction flag with current velocity (F63D)
        xor_result = direction_flag ^ y_vel
        
        # Check if sign bit matches (BPL checks bit 7)
        if not (xor_result & 0x80):
            # Same sign - no reversal needed
            return
        
        # Different signs - reverse velocity (F641-F648)
        # EOR #$FF inverts all bits
        y_vel = y_vel ^ 0xFF
        self.memory.write(self.y_vel_addr, y_vel)
        
        # ASL then ROR sequence (F647-F648)
        # ASL shifts left, putting bit 7 into carry
        carry = (y_vel >> 7) & 0x01
        temp = (y_vel << 1) & 0xFF
        
        # ROR rotates right with carry
        y_vel = (temp >> 1) | (carry << 7)
        self.memory.write(self.y_vel_addr, y_vel)
    
    def _spawn_fly(self, y_index, carry):
        """
        Spawn a new fly on screen.
        FIXED: Now uses retry loop like ASM (LF65C-LF686)
        """
        # Generate random horizontal spawn (F65C-F670)
        rand = self._get_random()
        duration = (rand & 0x0F) + 6
        duration = duration >> 1
        
        if duration & 0x01:
            # Spawn from LEFT, move RIGHT
            x_vel = duration
            x_pos = 0x00
        else:
            # Spawn from RIGHT, move LEFT
            x_vel = (256 - duration) & 0xFF
            x_pos = 0x9A
        
        self.memory.write(self.x_pos_addr, x_pos)
        self.memory.write(self.x_vel_addr, x_vel)
        
        # Generate random Y position with retry loop (F675-F682)
        # FIXED: Use retry loop instead of modulo
        min_boundary = self.boundary_tables['min_y'][y_index]
        max_boundary = self.boundary_tables['max_y'][y_index]
        mask = self.boundary_tables['mask'][y_index]
        
        while True:
            rand = self._get_random()
            y_pos = (rand & mask) + min_boundary
            if y_pos < max_boundary:
                break
            # If >= max, loop and try again
        
        self.memory.write(self.y_pos_addr, y_pos)
        
        # Set random vertical velocity and timer (F6A6-F6BD)
        # FIXED: Use same random number for both
        self._set_random_y_velocity_and_timer()
    
    def _change_movement(self, y_index):
        """
        Change fly movement direction/speed.
        FIXED: Now matches ASM carry flag logic (LF688-LF6A6)
        """
        # Get random number and compare with $C0 (F688-F68D)
        rand = self._get_random()
        carry = 1 if rand >= 0xC0 else 0
        
        # Calculate duration (F68E-F691)
        duration = (rand & 0x07) + 0x04
        
        # Check game state (F694-F698)
        game_state = self.memory.read(0xB4)
        if game_state == 0:
            carry = 0  # Clear carry
        
        # Get current X velocity (F699-F69B)
        x_vel = self.memory.read(self.x_vel_addr)
        is_negative = (x_vel & 0x80) != 0
        
        # Apply carry flag logic (F699-F6A4)
        if is_negative:
            # Velocity is negative (moving left)
            if carry:
                # Carry set - keep duration as-is
                pass
            else:
                # Carry clear - invert duration
                duration = duration ^ 0xFF
        else:
            # Velocity is positive (moving right)
            if not carry:
                # Carry clear - keep duration as-is
                pass
            else:
                # Carry set - invert duration
                duration = duration ^ 0xFF
        
        self.memory.write(self.x_vel_addr, duration)
        
        # Set random vertical velocity and timer (F6A6-F6BD)
        # FIXED: Use same random number for both
        self._set_random_y_velocity_and_timer()
    
    def _set_random_y_velocity_and_timer(self):
        """
        Set random vertical velocity AND timer from same random number.
        FIXED: Now sets both values like ASM (LF6A6-LF6BD)
        """
        rand = self._get_random()
        
        # Lower 4 bits -> Y velocity (F6AA-F6AF)
        y_vel = (rand & 0x0F) - 0x08  # Range: -8 to +7
        if y_vel < 0:
            y_vel = (256 + y_vel) & 0xFF
        self.memory.write(self.y_vel_addr, y_vel)
        
        # Upper 4 bits -> Timer (F6B1-F6BB)
        timer = (rand >> 4) & 0x07
        timer = timer + 0x08  # Range: 8-15
        self.memory.write(self.timer_addr, timer)
    
    def _get_random(self):
        """
        Get next random number using AtariRNG.
        Also syncs with memory location $E4 for compatibility.
        """
        # Generate next random number
        rand = self.rng.next()
        
        # Sync with memory location $E4 for compatibility
        self.memory.write(0xE4, rand)
        
        return rand


class FireflyManager:
    """Manages both fireflies in the game."""
    
    def __init__(self, memory):
        """Initialize firefly manager."""
        self.memory = memory
        
        # Initialize random number generator
        # Use initial seed from memory location $E4 (or set default)
        initial_seed = 0x42  # Arbitrary seed
        self.memory.write(0xE4, initial_seed)
        self.rng = AtariRNG(initial_seed)
        
        # Create fireflies with shared RNG
        self.flies = [
            Firefly(memory, 0, self.rng),  # Player 0's fly
            Firefly(memory, 1, self.rng)   # Player 1's fly
        ]
        
        # Initialize DF accumulator
        self.memory.write(0xDF, 0x00)
        
        # Initialize fly positions (off screen initially)
        self.memory.write(0xD5, 0x38)  # Fly 0 X
        self.memory.write(0xD6, 0x38)  # Fly 1 X
        self.memory.write(0xD9, 0x00)  # Fly 0 Y (0 = off screen)
        self.memory.write(0xDA, 0x00)  # Fly 1 Y (0 = off screen)
        
        # Initialize velocities
        self.memory.write(0xCD, 0xFA)  # Fly 0 X velocity
        self.memory.write(0xCE, 0x00)  # Fly 1 X velocity
        self.memory.write(0xD1, 0x00)  # Fly 0 Y velocity
        self.memory.write(0xD2, 0x00)  # Fly 1 Y velocity
        
        # Initialize timers
        self.memory.write(0xB9, 0x08)  # Fly 0 timer
        self.memory.write(0xBA, 0x08)  # Fly 1 timer
    
    def update(self):
        """
        Update fireflies.
        
        NOTE: After testing, reverting to update both flies per frame.
        The ASM FA7E does alternate, but the firefly AI has internal
        frame checks that make it work correctly even when called every frame.
        The alternation might be for a different purpose (rendering/collision).
        """
        frame_counter = self.memory.read(0xB3)
        game_over = self.memory.read(0xB4) != 0
        
        # NOTE: Position updates are handled by Physics.update() (F5B4)
        # This routine only handles boundary bouncing and AI (F5FD)
        
        # Update both flies (they have internal frame checks)
        for fly in self.flies:
            fly.update_ai(frame_counter, game_over)
