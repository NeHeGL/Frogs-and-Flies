"""
Physics Routine - Exact conversion from Subroutine_F5B4
Applies velocities to positions with /16 division and random offset
"""

class Physics:
    """
    Implements the physics routine from $F5B4 that applies velocities.
    This runs BEFORE the state machine in the main loop.
    """
    
    def __init__(self, memory):
        self.memory = memory
        self.df_offset = 0  # Random offset (0-15) updated each frame
        
    def update(self):
        """
        Apply physics to all objects (frogs, flies, etc.)
        
        Assembly: Subroutine_F5B4
        - Updates $DF offset
        - Applies velocities with /16 division
        - Handles signed values with EOR/SBC
        """
        # Update random offset ($DF)
        # Assembly: LDA $DF / CLC / ADC #$0B / AND #$0F / STA $DF
        self.df_offset = (self.df_offset + 0x0B) & 0x0F
        self.memory.write(0xDF, self.df_offset)
        
        # Apply physics to all 4 objects (X=3 down to 0)
        # In Frogs and Flies: 0=Player0, 1=Player1, 2=Fly0, 3=Fly1
        for x in range(3, -1, -1):
            self.apply_velocity_x(x)
            # Skip Y physics for frogs in state 6 (jump-off-screen).
            # state_6_jump_off() applies Y velocity directly to bypass the
            # < 0x4A Y-bound cap that would stop the upward arc too early.
            state_addr = 0xC5 + x  # $C5=P0, $C6=P1 (x=0,1); x=2,3 are flies (no state)
            if x <= 1 and self.memory.read(state_addr) == 6:
                pass  # Y handled by state_6_jump_off
            else:
                self.apply_velocity_y(x)
    
    def apply_velocity_x(self, x):
        """
        Apply X velocity to X position.
        
        Assembly at $F5BF:
        LDA $CB,X      ; Load X velocity
        CLC
        ADC $DF        ; Add random offset
        LSR            ; Divide by 2
        LSR            ; Divide by 2
        LSR            ; Divide by 2
        LSR            ; Divide by 2 (total: /16)
        EOR #$08       ; Sign conversion
        SEC
        SBC #$08
        CLC
        ADC $D3,X      ; Add to X position
        CMP #$9C       ; Check bounds
        BCS clear_x_vel
        STA $D3,X      ; Store new position
        """
        x_vel = self.memory.read(0xCB + x)
        
        # Add offset
        temp = (x_vel + self.df_offset) & 0xFF
        
        # Divide by 16
        temp = temp >> 4
        
        # Sign conversion: EOR #$08, SBC #$08
        temp = temp ^ 0x08
        temp = (temp - 0x08) & 0xFF
        
        # Convert to signed
        if temp > 127:
            temp = temp - 256
        
        # Add to position
        x_pos = self.memory.read(0xD3 + x)
        new_pos = (x_pos + temp) & 0xFF  # Wrap to 0-255 range (8-bit unsigned)
        
        # Check bounds (CMP #$9C / BCS)
        # In 8-bit unsigned: values >= 0x9C are out of bounds
        # Negative values wrap to 0x80-0xFF, which are >= 0x9C
        if new_pos >= 0x9C:
            # Out of bounds - clear velocity
            self.memory.write(0xCB + x, 0x00)
        else:
            # In bounds - update position
            self.memory.write(0xD3 + x, new_pos)
    
    def apply_velocity_y(self, x):
        """
        Apply Y velocity to Y position.
        
        Assembly at $F5DC:
        LDA $CF,X      ; Load Y velocity
        CLC
        ADC $DF        ; Add random offset
        LSR            ; Divide by 2
        LSR            ; Divide by 2
        LSR            ; Divide by 2
        LSR            ; Divide by 2 (total: /16)
        EOR #$08       ; Sign conversion
        SEC
        SBC #$08
        CLC
        ADC $D7,X      ; Add to Y position
        CMP #$4A       ; Check bounds
        BCS skip_update  ; If >= $4A, skip storing (don't update position)
        STA $D7,X      ; Store new position
        """
        y_vel = self.memory.read(0xCF + x)
        
        # Add offset
        temp = (y_vel + self.df_offset) & 0xFF
        
        # Divide by 16
        temp = temp >> 4
        
        # Sign conversion: EOR #$08, SBC #$08
        temp = temp ^ 0x08
        temp = (temp - 0x08) & 0xFF
        
        # Convert to signed
        if temp > 127:
            temp = temp - 256
        
        # Add to position
        y_pos = self.memory.read(0xD7 + x)
        new_pos = y_pos + temp
        
        # Wrap to 8-bit unsigned (0-255)
        new_pos_byte = new_pos & 0xFF
        
        # Check bounds (CMP #$4A / BCS skip_update)
        # If new_pos >= 0x4A (74), skip the update (don't store)
        # This prevents Y from wrapping to high values (0x4A-0xFF)
        # Values 0x00-0x49 (0-73) are allowed
        if new_pos_byte < 0x4A:
            # In bounds - update position
            self.memory.write(0xD7 + x, new_pos_byte)
        # If out of bounds (>= 0x4A), position unchanged
