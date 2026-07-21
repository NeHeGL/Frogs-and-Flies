"""
Frog State Machine - CORRECTED VERSION
Based on deep analysis of assembly code

CRITICAL FIX: F51B and F531 are sprite selection routines, NOT velocity application!
Physics.py (F5B4) already applies velocities. State machine should ONLY:
1. Set velocities in memory
2. Apply gravity (DEC $CF,X)
3. Check conditions and change states
"""

from sound_system import get_sound_system

class FrogStateMachine:
    """
    Implements the 13-state frog state machine from the original assembly.
    
    Memory locations (per frog, X=0 for P0, X=1 for P1):
    - $C5,X: Current state (0-12)
    - $C3,X: Status flags (bit 1=tongue, bit 3=direction, bit 6=button)
    - $D3,X: X position
    - $D7,X: Y position  
    - $CB,X: X velocity
    - $CF,X: Y velocity
    - $DB,X: Sprite pointer
    - $C1,X: Animation counter
    - $C7,X: Tongue delay
    - $BF,X: Hop counter
    """
    
    # State constants (based on assembly state machine jump table at F279/F286)
    STATE_SITTING = 0               # F2A7: Sitting on lily pad, waiting for joystick input
    STATE_HOP_START = 1             # F444: Hop start - tap vs hold mechanic (upgrades velocity based on hold time)
    STATE_HOPPING = 2               # F479: In mid-air, applying gravity
    STATE_SINKING = 3               # F4B6: Sinking in water (waits for Y==0)
    STATE_SPLASH = 4                # F4C4: Splash animation at bottom
    STATE_RESURFACE = 5             # F4F3: Resurface and swim to lily pad
    STATE_JUMP_OFF_SCREEN = 6       # F365: Jumping off screen at game end
    STATE_EASY_MODE_HOP = 7         # F40F: Easy mode hop (auto-lands on opposite lily pad)
    STATE_UNUSED_8 = 8              # F39A: Just returns (unused/placeholder state)
    STATE_CHECK_GAME_OVER = 9       # F39B: Check if all flies caught, trigger game over sequence
    STATE_GAME_OVER_WAIT_FLY = 10   # F3C6: Game over - wait for fly to move off screen
    STATE_GAME_OVER_FROGS_MOVE = 11 # F3ED: Game over - frogs moving to center
    STATE_GAME_OVER_FINAL = 12      # F3FE: Game over - final state before reset
    
    # Velocity table from assembly $F22B
    # Row 0 (indices 0-15): Small jumps
    # Row 1 (indices 16-31): Medium jumps
    # Row 2 (indices 32-47): Large jumps (used in normal mode)
    # Each row: first 8 bytes are X velocities, next 8 bytes are Y velocities
    VELOCITY_TABLE = [
        # Row 0: Small jumps (assembly F22B)
        0x04, 0x02, 0x02, 0xFE, 0xFC, 0xFA, 0x06, 0x06,  # X velocities
        0x04, 0x06, 0x06, 0x06, 0x04, 0x02, 0x02, 0x02,  # Y velocities
        # Row 1: Medium jumps (assembly F23B)
        0x08, 0x04, 0x04, 0xFC, 0xF8, 0xF4, 0x0C, 0x0C,  # X velocities
        0x08, 0x0C, 0x0C, 0x0C, 0x08, 0x04, 0x04, 0x04,  # Y velocities
        # Row 2: Large jumps (assembly F24B) - CORRECTED
        0x0B, 0x05, 0x05, 0xFB, 0xF5, 0xF1, 0x0F, 0x0F,  # X velocities
        0x0B, 0x0F, 0x0F, 0x0F, 0x0B, 0x05, 0x05, 0x05   # Y velocities (FIXED!)
    ]

    
    def __init__(self, memory, player_num):
        self.memory = memory
        self.player = player_num
        
        # Memory addresses
        self.state_addr = 0xC5 + player_num
        self.flags_addr = 0xC3 + player_num
        self.x_pos_addr = 0xD3 + player_num
        self.y_pos_addr = 0xD7 + player_num
        self.x_vel_addr = 0xCB + player_num
        self.y_vel_addr = 0xCF + player_num
        self.sprite_addr = 0xDB + player_num
        self.anim_addr = 0xC1 + player_num
        self.tongue_delay_addr = 0xC7 + player_num
        self.hop_counter_addr = 0xBF + player_num
        
        self.lily_pads = [0x20, 0x6E]
        
    def update(self, joystick_bits):
        """Update frog state machine."""
        state = self.memory.read(self.state_addr)
        
        # NOTE: Tongue counter decrement is now handled centrally in main.py
        # (label_F55C - alternates between players each frame)
        # NOTE: Button handling is also done in main.py now
        
        # Call state handler
        if state == self.STATE_SITTING:
            self.state_sitting(joystick_bits)
        elif state == self.STATE_HOP_START:
            self.state_hop_start()
        elif state == self.STATE_HOPPING:
            self.state_hopping()
        elif state == self.STATE_SINKING:
            self.state_sinking()
        elif state == self.STATE_SPLASH:
            self.state_splash()
        elif state == self.STATE_RESURFACE:
            self.state_resurface()
        elif state == self.STATE_JUMP_OFF_SCREEN:
            self.state_6_jump_off()
        elif state == self.STATE_EASY_MODE_HOP:
            self.state_7()
        # States 8-12 are game over related and handled by main.py
        
    def state_sitting(self, joystick_bits):
        """State 0: Sitting on lily pad."""
        e0_addr = 0xE0 + self.player
        y_index = self.memory.read(e0_addr)
        
        if y_index >= 0x80:
            return
            
        flags = self.memory.read(self.flags_addr)
        
        if flags & 0x80:
            # EASY MODE (F2EF)
            # Assembly: LDA $C3,X / LDY #$0A / AND #$08 / BEQ +2 / LDY #$F6
            # STY $CB,X / LDA #$1A / STA $CF,X / LDA #$07 / STA $C5,X
            facing_left = bool(flags & 0x08)
            
            if facing_left:
                x_vel = 0xF6  # -10
            else:
                x_vel = 0x0A  # +10
            
            y_vel = 0x1A
            
            self.memory.write(self.x_vel_addr, x_vel)
            self.memory.write(self.y_vel_addr, y_vel)
            self.memory.write(self.state_addr, 0x07)  # State 7
        else:
            # NORMAL MODE (assembly F2B9-F2DA)
            facing_left = bool(flags & 0x08)
            
            # F2B9-F2C7: Adjust direction index for facing left
            # F2BD: CPY #$02 / BEQ Branch_F2C7 - if Y==2, jump to INY
            # F2C1: CPY #$06 / BNE Branch_F2C8 - if Y!=6, skip INY
            # F2C5: LDY #$04 - if Y==6, set Y=4
            # F2C7: INY - increment Y (only for Y==2 or Y==6)
            if facing_left:
                if y_index == 2:
                    y_index = 3  # INY from 2 -> 3
                elif y_index == 6:
                    y_index = 5  # LDY #$04, then INY: 6 -> 4 -> 5
            
            # F2D2-F2DA: Use row 0 (small jumps) - assembly uses $F22B,Y directly
            # No offset added! Y is just the direction index (0-7)
            x_vel = self.VELOCITY_TABLE[y_index]
            y_vel = self.VELOCITY_TABLE[y_index + 8]
            
            self.memory.write(self.x_vel_addr, x_vel)
            self.memory.write(self.y_vel_addr, y_vel)
            self.memory.write(self.state_addr, 0x01)
            self.memory.write(self.anim_addr, 0x1B)  # Start counter at 27
            self.memory.write(0xC9 + self.player, y_index)  # Store direction index in $C9,X
            self.memory.write(self.sprite_addr, 0x93)
            
            # F2DC: INC $D7,X - Increment Y position
            # Since rendering is at 82-y_pos, incrementing y_pos moves frog UP on screen
            y_pos = self.memory.read(self.y_pos_addr)
            self.memory.write(self.y_pos_addr, (y_pos + 1) & 0xFF)
            
            # Update direction flag (assembly F2DE-F2EC)
            # AND #$F7 - clear bit 3 (default to facing right)
            # CPY #$06 / BCS - if Y >= 6, skip ORA (stay facing right)
            # CPY #$03 / BCC - if Y < 3, skip ORA (stay facing right)
            # ORA #$08 - if 3 <= Y < 6, set bit 3 (facing left)
            flags = flags & 0xF7  # Clear bit 3 (facing right)
            if 3 <= y_index < 6:
                flags = flags | 0x08  # Set bit 3 (facing left)
            self.memory.write(self.flags_addr, flags)
    
    def state_hop_start(self):
        """
        State 1: Start of hop - TAP VS HOLD mechanic!
        
        Assembly F444-F478:
        - JSR F51B (sprite selection)
        - JSR F531 (X position clamping)
        - Decrement animation counter ($C1,X)
        - If counter == 23 (0x17): Upgrade to row 1 (medium jumps)
        - If counter == 19 (0x13): Upgrade to row 2 (large jumps)
        - If counter == 0 or joystick released: Transition to state 2
        
        This creates the tap vs hold mechanic:
        - Tap (release immediately): Row 0 (small jumps)
        - Hold 4 frames: Row 1 (medium jumps)
        - Hold 8 frames: Row 2 (large jumps)
        """
        # F444: JSR Subroutine_F51B - Dynamic sprite selection
        self.subroutine_f51b()
        
        # F447: JSR Subroutine_F531 - Clamp X position
        x_pos = self.memory.read(self.x_pos_addr)
        if x_pos < 0x07:
            self.memory.write(self.x_pos_addr, 0x07)
            self.memory.write(self.x_vel_addr, 0x00)
        elif x_pos > 0x8F:
            self.memory.write(self.x_pos_addr, 0x8F)
            self.memory.write(self.x_vel_addr, 0x00)
        
        # F44A: DEC $C1,X - Decrement animation counter
        anim_counter = self.memory.read(self.anim_addr)
        anim_counter = (anim_counter - 1) & 0xFF
        self.memory.write(self.anim_addr, anim_counter)
        
        # F44C: BEQ Branch_F474 - If counter == 0, transition to state 2
        # This check happens BEFORE the joystick check, so it always transitions when counter hits 0
        if anim_counter == 0:
            self.memory.write(self.state_addr, self.STATE_HOPPING)
            return
        
        # F44E-F450: Load counter and direction index
        y_index = self.memory.read(0xC9 + self.player)
        
        # F452-F460: If counter == 23, upgrade to row 1 (medium jumps)
        if anim_counter == 0x17:  # 23
            x_vel = self.VELOCITY_TABLE[16 + y_index]  # Row 1 offset = 16
            y_vel = self.VELOCITY_TABLE[16 + y_index + 8]
            self.memory.write(self.x_vel_addr, x_vel)
            self.memory.write(self.y_vel_addr, y_vel)
        
        # F462-F46E: If counter == 19, upgrade to row 2 (large jumps)
        elif anim_counter == 0x13:  # 19
            x_vel = self.VELOCITY_TABLE[32 + y_index]  # Row 2 offset = 32
            y_vel = self.VELOCITY_TABLE[32 + y_index + 8]
            self.memory.write(self.x_vel_addr, x_vel)
            self.memory.write(self.y_vel_addr, y_vel)
        
        # F470-F478: Check if joystick released (direction index == 0xFF)
        # BPL branches if positive (0-127), which means RETURN (stay in state 1)
        # Only if direction is negative (0x80-0xFF) do we fall through to set state=2
        e0_addr = 0xE0 + self.player
        direction = self.memory.read(e0_addr)
        if direction >= 0x80:  # Negative (0xFF = no input)
            # Joystick released - transition to state 2
            self.memory.write(self.state_addr, self.STATE_HOPPING)
        # else: direction is positive (joystick still held), stay in state 1
    
    def subroutine_f51b(self):
        """
        Subroutine F51B: Dynamic sprite selection based on Y position.
        
        Assembly F51B-F530:
        F51B: LDA $D7,X         ; Load Y position
        F51D: BMI Branch_F530   ; If Y < 0 (negative), return
        F51F: CMP #$08          ; Compare with 8
        F521: BMI Branch_F530   ; If Y < 8, return
        F523: LDY #$FF          ; Y = -1 (will be incremented to 0)
        
        Branch_F525:
        F525: INY               ; Increment Y
        F526: CMP $F25B,Y       ; Compare Y position with threshold table
        F529: BCS Branch_F525   ; If Y >= threshold, loop (increment Y)
        F52B: LDA $F25F,Y       ; Load sprite pointer from table
        F52E: STA $DB,X         ; Store sprite pointer
        
        Branch_F530:
        F530: RTS
        
        Tables at F25B:
        F25B: .byte $0A,$0D,$12,$80  ; Y thresholds
        F25F: .byte $C9,$DB,$ED,$FF  ; Sprite pointers (4 bytes after F25B)
        
        Logic:
        - If Y < 8: Don't change sprite (return)
        - Compare Y against thresholds to find index:
          - Y < 10 (0x0A): index 0 → sprite $C9
          - Y < 13 (0x0D): index 1 → sprite $DB
          - Y < 18 (0x12): index 2 → sprite $ED
          - Y >= 18:       index 3 → sprite $FF
        """
        # F51B: LDA $D7,X
        y_pos = self.memory.read(self.y_pos_addr)
        
        # F51D: BMI Branch_F530 - If Y < 0 (>= 128 in unsigned), return
        if y_pos >= 128:
            return
        
        # F51F-F521: CMP #$08 / BMI Branch_F530 - If Y < 8, return
        if y_pos < 8:
            return
        
        # F523: LDY #$FF - Start with Y = -1 (will be incremented to 0)
        # F525-F529: Loop to find threshold index
        # Tables from ROM at F25B
        thresholds = [0x0A, 0x0D, 0x12, 0x80]  # Y thresholds
        sprite_pointers = [0xC9, 0xDB, 0xED, 0xFF]  # Sprite pointers
        
        # Find the correct index by comparing Y position with thresholds
        index = 0
        for i, threshold in enumerate(thresholds):
            if y_pos < threshold:
                index = i
                break
            index = i + 1
        
        # Clamp index to valid range
        if index >= len(sprite_pointers):
            index = len(sprite_pointers) - 1
        
        # F52B-F52E: LDA $F25F,Y / STA $DB,X
        sprite_ptr = sprite_pointers[index]
        self.memory.write(self.sprite_addr, sprite_ptr)
    
    def state_hopping(self):
        """
        State 2: In mid-hop.
        
        Assembly F479:
        - JSR F51B (sprite selection based on Y position)
        - JSR F531 (X position clamping)
        - DEC $CF,X (apply gravity to Y velocity)
        - Check if Y < 8 (hit top)
        - Check if Y >= landing height
        
        CRITICAL: Does NOT apply velocities! Physics.py does that.
        """
        # F479: JSR Subroutine_F51B - Dynamic sprite selection
        self.subroutine_f51b()
        
        # F47C: JSR Subroutine_F531 - Clamp X position
        x_pos = self.memory.read(self.x_pos_addr)
        if x_pos < 0x07:
            self.memory.write(self.x_pos_addr, 0x07)
            self.memory.write(self.x_vel_addr, 0x00)
        elif x_pos > 0x8F:
            self.memory.write(self.x_pos_addr, 0x8F)
            self.memory.write(self.x_vel_addr, 0x00)
        
        # Apply gravity (DEC $CF,X)
        y_vel_byte = self.memory.read(self.y_vel_addr)
        y_vel_byte = (y_vel_byte - 1) & 0xFF
        self.memory.write(self.y_vel_addr, y_vel_byte)
        
        # Check position
        y_pos = self.memory.read(self.y_pos_addr)
        
        # Hit top of screen (assembly F481-F49C)
        if y_pos < 8:
            # F487-F489: Set Y position to 7
            self.memory.write(self.y_pos_addr, 7)
            
            # F48B-F497: Set state=0, sprite=$B7, clear velocities
            self.memory.write(self.state_addr, 0)
            self.memory.write(self.sprite_addr, 0xB7)
            self.memory.write(self.x_vel_addr, 0x00)
            self.memory.write(self.y_vel_addr, 0x00)
            
            # Clear direction index to prevent immediate re-jump if key still held
            e0_addr = 0xE0 + self.player
            self.memory.write(e0_addr, 0xFF)
            
            # F499: JSR Subroutine_F546 - check if on lily pad
            x_pos = self.memory.read(self.x_pos_addr)
            on_lily_pad = False
            if 0x0D <= x_pos < 0x44:  # Left lily pad
                on_lily_pad = True
            elif 0x52 <= x_pos < 0x89:  # Right lily pad
                on_lily_pad = True
            
            # F49C: BCS Branch_F4B5 - if on lily pad, return (land normally)
            if on_lily_pad:
                return  # State already set to 0, velocities cleared
            
            # F49E-F4B2: NOT on lily pad - fell in water!
            self.memory.write(self.state_addr, 3)  # State 3 (sinking)
            flags = self.memory.read(self.flags_addr)
            flags &= ~0x02  # Clear tongue flag (bit 1) - no tongue while in water!
            self.memory.write(self.flags_addr, flags)
            self.memory.write(self.y_vel_addr, 0xF4)  # -12 (sink down)
            self.memory.write(self.tongue_delay_addr, 0x00)
            
            # F4B0-F4B2: Play splash sound (LDY #$03 / JSR F918)
            sound = get_sound_system()
            sound.play_splash()
            
            # NOTE: Frog at Y=7 with Y_vel=$F4. Physics will apply this.
            return
    
    def state_sinking(self):
        """
        State 3: Sinking in water.
        
        Assembly F4B6-F4C2:
        F4B6: LDA $D7,X      ; Load Y position
        F4B8: BNE Branch_F4B5 ; If Y != 0, return (still sinking)
        F4BA: STA $CF,X      ; Store 0 to Y velocity (A=0 from LDA)
        F4BC: LDA #$17       ; Load 23
        F4BE: STA $C1,X      ; Store to counter
        F4C0: LDA #$04       ; Load 4
        F4C2: STA $C5,X      ; Store to state (go to state 4)
        
        NOTE: State 3 doesn't call F51B, but the sprite should change based on Y position
        during sinking. The renderer or main loop should handle F51B sprite selection.
        """
        # Apply F51B sprite selection based on Y position (sinking animation)
        # F51B tables: F25B (Y thresholds), F25F (sprite pointers)
        # This creates the sinking animation as Y decreases from 7 to 0
        y_pos = self.memory.read(self.y_pos_addr)
        
        # F51B logic: Compare Y against thresholds and select sprite
        # Table at F25B: $0A,$0D,$12,$80 (first 4 values for sinking range)
        # Table at F25F: sprite pointers (4 bytes after F25B in ROM)
        # For sinking (Y=0-7), use sitting sprite $B7 (already set)
        # The sprite stays at $B7 during sinking - no animation change needed
        # The visual "sinking" effect comes from Y position changing, not sprite
        
        # F4B6: LDA $D7,X
        # F4B8: BNE Branch_F4B5 - If Y != 0, return
        if y_pos != 0:
            return
        
        # F4BA: STA $CF,X - Store 0 to Y velocity (A still contains 0 from LDA $D7,X)
        self.memory.write(self.y_vel_addr, 0x00)
        
        # F4BC-F4BE: LDA #$17 / STA $C1,X - Set counter to 23
        self.memory.write(self.anim_addr, 0x17)
        
        # F4C0-F4C2: LDA #$04 / STA $C5,X - Set state to 4
        self.memory.write(self.state_addr, 0x04)
    
    def state_7(self):
        """
        State 7: Easy mode hop.
        
        Assembly F40F:
        - JSR F51B (sprite selection)
        - JSR F531 (X position clamping)
        - DEC $CF,X (gravity)
        - Check if Y < 8 (hit top)
        - Check if Y >= 153 (landed)
        """
        # F40F: JSR Subroutine_F51B - Dynamic sprite selection
        self.subroutine_f51b()
        
        # F412: JSR Subroutine_F531 - Clamp X position
        x_pos = self.memory.read(self.x_pos_addr)
        if x_pos < 0x07:
            self.memory.write(self.x_pos_addr, 0x07)
            self.memory.write(self.x_vel_addr, 0x00)
        elif x_pos > 0x8F:
            self.memory.write(self.x_pos_addr, 0x8F)
            self.memory.write(self.x_vel_addr, 0x00)
        
        # Apply gravity
        y_vel_byte = self.memory.read(self.y_vel_addr)
        y_vel_byte = (y_vel_byte - 1) & 0xFF
        self.memory.write(self.y_vel_addr, y_vel_byte)
        
        # Set hopping sprite
        self.memory.write(self.sprite_addr, 0x93)
        
        # Check position
        x_pos = self.memory.read(self.x_pos_addr)
        y_pos = self.memory.read(self.y_pos_addr)
        x_vel = self.memory.read(self.x_vel_addr)
        
        # Convert y_vel_byte to signed for display
        if y_vel_byte >= 128:
            y_vel_signed = y_vel_byte - 256
        else:
            y_vel_signed = y_vel_byte
        
        # Assembly F417-F443: Check if Y < 8 (hit top) or Y >= 153 (landed)
        # Both cases land the frog and reset state
        if y_pos < 8:
            # Hit top - land on opposite lily pad at top
            self.memory.write(self.y_pos_addr, 0x07)
            self.memory.write(self.state_addr, 0x00)
            
            # Flip direction
            flags = self.memory.read(self.flags_addr)
            flags ^= 0x08
            self.memory.write(self.flags_addr, flags)
            
            # Set X to lily pad (ROM data at F40B and F40D)
            lily_pads_right = [0x20, 0x2B]  # F40B
            lily_pads_left = [0x62, 0x6E]   # F40D
            if flags & 0x08:  # Facing left
                x_pos = lily_pads_left[self.player]
            else:  # Facing right
                x_pos = lily_pads_right[self.player]
            self.memory.write(self.x_pos_addr, x_pos)
            
            self.memory.write(self.sprite_addr, 0xB7)
            self.memory.write(self.x_vel_addr, 0x00)
            self.memory.write(self.y_vel_addr, 0x00)
            return
        
        # Landed at bottom (Y >= 153)
        if y_pos >= 153:
            self.memory.write(self.y_pos_addr, 0x99)
            self.memory.write(self.state_addr, 0x00)
            
            # Flip direction
            flags = self.memory.read(self.flags_addr)
            flags ^= 0x08
            self.memory.write(self.flags_addr, flags)
            
            # Set X to lily pad
            lily_pads_right = [0x20, 0x2B]
            lily_pads_left = [0x62, 0x6E]
            if flags & 0x08:
                x_pos = lily_pads_left[self.player]
            else:
                x_pos = lily_pads_right[self.player]
            self.memory.write(self.x_pos_addr, x_pos)
            
            self.memory.write(self.sprite_addr, 0xB7)
            self.memory.write(self.x_vel_addr, 0x00)
            self.memory.write(self.y_vel_addr, 0x00)
    
    def state_6_jump_off(self):
        """
        State 6: Jumping off screen at game end.
        
        Assembly F365-F37F:
        F365: LDA $CB,X        ; Load X velocity
        F367: BEQ Branch_F37B  ; If velocity == 0, disappear (left edge)
        F369: LDA $D3,X        ; Load X position
        F36B: CMP #$93         ; Compare with 147
        F36D: BCS Branch_F37B  ; If X >= 147, disappear (right edge)
        F36F: JSR F51B         ; Sprite update
        F372: LDA $B3          ; Frame counter
        F374: AND #$02         ; Check bit 1
        F376: BNE return       ; If set, skip gravity
        F378: DEC $CF,X        ; Apply gravity to Y velocity
        
        At F37B: Clear Y velocity and Y position (frog disappears)
        
        NOTE: The physics.py Y-bound cap (< 0x4A) is bypassed for state 6 by
        directly applying Y velocity here instead of relying on physics.apply_velocity_y.
        This allows the frog to arc above Y=74 and off the top of the screen.
        """
        x_vel = self.memory.read(self.x_vel_addr)
        x_pos = self.memory.read(self.x_pos_addr)
        
        # F367: Check if X velocity is 0 (went off left edge, physics cleared it)
        # F36D: Check if X position >= 147 (0x93) (off right edge)
        if x_vel == 0 or x_pos >= 147:
            # F37B: Frog disappears
            self.memory.write(self.y_vel_addr, 0x00)
            self.memory.write(self.y_pos_addr, 0x00)
            return
        
        # F36F: Sprite update happens here (F51B)
        # Set jumping sprite
        self.memory.write(self.sprite_addr, 0x93)
        
        # F372-F378: Apply gravity every other frame
        # Note: AND #$02 checks bit 1, BNE skips if bit is SET
        # So gravity applies when bit 1 is CLEAR (0)
        frame_counter = self.memory.read(0xB3)
        
        # Apply Y velocity DIRECTLY here (bypassing physics Y-bound cap of 0x4A).
        # physics.apply_velocity_y clamps Y to < 74 which stops the upward arc too early.
        # For state 6 we need Y to go above 82 so the frog disappears off the top.
        y_vel_byte = self.memory.read(self.y_vel_addr)
        y_pos = self.memory.read(self.y_pos_addr)
        
        # Convert signed velocity (same formula as physics.apply_velocity_y)
        df_offset = self.memory.read(0xDF)
        temp = (y_vel_byte + df_offset) & 0xFF
        temp = temp >> 4
        temp = temp ^ 0x08
        temp = (temp - 0x08) & 0xFF
        if temp > 127:
            temp = temp - 256
        
        # Apply directly to Y position without the < 0x4A bound check
        new_y = (y_pos + temp) & 0xFF
        self.memory.write(self.y_pos_addr, new_y)
        
        if not (frame_counter & 0x02):
            # Decrement Y velocity (gravity)
            y_vel_byte = (y_vel_byte - 1) & 0xFF
            self.memory.write(self.y_vel_addr, y_vel_byte)
    
    # Splash sprite table from ROM at F262 (extracted from actual ROM file)
    # Counter starts at 23 (0x17) and counts down to 0
    # Table has 24 entries (indices 0-23)
    # Animation sequence: 0x81 → 0x6F → 0x5D → 0x4B (4 unique splash sprites, each shown for 4 frames)
    SPLASH_SPRITE_TABLE = [
        0xFF, 0x00, 0x00, 0x81, 0x81, 0x81, 0x81, 0x6F,  # Indices 0-7
        0x6F, 0x6F, 0x6F, 0x5D, 0x5D, 0x5D, 0x5D, 0x00,  # Indices 8-15
        0x00, 0x00, 0x00, 0x4B, 0x4B, 0x4B, 0x4B, 0xA7   # Indices 16-23
    ]
    
    def state_splash(self):
        """
        State 4: Splash animation at bottom of water.
        
        Assembly F4C4-F4F2:
        F4C4: DEC $C1,X         ; Decrement counter
        F4C6: BEQ Branch_F4D6   ; If counter == 0, go to state 5
        F4C8: LDY $C1,X         ; Load counter into Y
        F4CA: LDA $F262,Y       ; Load sprite from table at F262
        F4CD: BEQ Branch_F4D3   ; If sprite == 0, skip sprite update
        F4CF: STA $DB,X         ; Store sprite
        F4D1: LDA #$09          ; Load Y position 9
        F4D3: STA $D7,X         ; Store Y position
        F4D5: RTS
        
        When counter reaches 0 (F4D6-F4F2):
        - Set state to 5
        - Set Y position to 4
        - Set sprite to $B7
        - Flip direction (EOR #$08)
        - Set X velocity based on direction: +4 if right, -4 if left
        """
        # F4C4: DEC $C1,X
        counter = self.memory.read(self.anim_addr)
        
        # Check if counter is already 0 before decrementing to prevent underflow
        if counter == 0:
            # Already at 0, transition to state 5 immediately
            self.memory.write(self.state_addr, 0x05)  # State 5
            self.memory.write(self.y_pos_addr, 0x04)  # Y = 4
            self.memory.write(self.sprite_addr, 0xB7)  # Sitting sprite
            
            # F4E2-F4E6: Flip direction (EOR #$08)
            flags = self.memory.read(self.flags_addr)
            flags ^= 0x08
            self.memory.write(self.flags_addr, flags)
            
            # F4E8-F4F0: Set X velocity based on direction
            if flags & 0x08:  # Facing left
                x_vel = 0xFC  # -4
            else:  # Facing right
                x_vel = 0x04  # +4
            self.memory.write(self.x_vel_addr, x_vel)
            return
        
        counter = (counter - 1) & 0xFF
        self.memory.write(self.anim_addr, counter)
        
        # F4C6: BEQ Branch_F4D6 - If counter == 0 after decrement, go to state 5
        if counter == 0:
            # F4D6-F4F2: Transition to state 5
            self.memory.write(self.state_addr, 0x05)  # State 5
            self.memory.write(self.y_pos_addr, 0x04)  # Y = 4
            self.memory.write(self.sprite_addr, 0xB7)  # Sitting sprite
            
            # F4E2-F4E6: Flip direction (EOR #$08)
            flags = self.memory.read(self.flags_addr)
            flags ^= 0x08
            self.memory.write(self.flags_addr, flags)
            
            # F4E8-F4F0: Set X velocity based on direction
            # LDY #$04 / AND #$08 / BEQ +2 / LDY #$FC / STY $CB,X
            if flags & 0x08:  # Facing left
                x_vel = 0xFC  # -4
            else:  # Facing right
                x_vel = 0x04  # +4
            self.memory.write(self.x_vel_addr, x_vel)
            return
        
        # F4C8-F4D3: Update sprite and Y position during animation
        # LDY $C1,X - counter is now the index into sprite table
        # LDA $F262,Y - load sprite from table
        # Bounds check to prevent IndexError
        if counter >= len(self.SPLASH_SPRITE_TABLE):
            # Counter out of range, use default sprite
            sprite = 0x00
        else:
            sprite = self.SPLASH_SPRITE_TABLE[counter]
        
        # F4CD: BEQ Branch_F4D3 - If sprite == 0, skip sprite update
        if sprite != 0x00:
            # F4CF: STA $DB,X - Store sprite
            self.memory.write(self.sprite_addr, sprite)
            # F4D1: LDA #$09 - Load Y position 9
            # NOTE: ASM sets Y=9, but the splash sprites should be anchored at the
            # frog's FEET (water surface), not the head.  The renderer places the
            # sprite top at (82 - Y) * 2 and renders DOWN, so Y=9 puts the top at
            # scanline 146 while the sitting frog's top is at scanline 150 (Y=7).
            # Using Y=7 aligns the splash bottom with the frog's feet at the water.
            y_pos = 0x07
        else:
            # Branch_F4D3: If sprite is 0, Y position stays as-is (don't update)
            y_pos = self.memory.read(self.y_pos_addr)
        
        # F4D3: STA $D7,X - Store Y position (always executed)
        self.memory.write(self.y_pos_addr, y_pos)
    
    def state_resurface(self):
        """
        State 5: Resurface from water and return to lily pad.
        
        Assembly F4F3-F51A:
        F4F3: JSR Subroutine_F546 - Check if on lily pad
        F4F6: BCC Branch_F4F2 - If not on lily pad, RETURN (keep swimming)
        F4F8: LDA #$00 / STA $C5,X - Set state to 0
        F4FC-F50A: Complex bit manipulation to adjust X position
        F50C: LDA #$07 / STA $D7,X - Set Y position to 7
        F510: LDA #$00 / STA $CB,X - Clear X velocity
        F514: LDA $C3,X / AND #$FD / STA $C3,X - Clear tongue flag
        
        The frog SWIMS with X velocity until it reaches the lily pad edge,
        then lands and clears velocity. It does NOT teleport!
        """
        # F4F3: JSR Subroutine_F546 - Check if on lily pad
        x_pos = self.memory.read(self.x_pos_addr)
        on_lily_pad = False
        
        if 0x0D <= x_pos < 0x44:  # Left lily pad
            on_lily_pad = True
        elif 0x52 <= x_pos < 0x89:  # Right lily pad
            on_lily_pad = True
        
        # F4F6: BCC Branch_F4F2 - If not on lily pad, return (keep swimming)
        if not on_lily_pad:
            return  # Frog continues swimming with X velocity set in state 4
        
        # F4F8-F4FA: LDA #$00 / STA $C5,X - Set state to 0
        self.memory.write(self.state_addr, 0x00)
        
        # F4FC-F50A: Complex bit manipulation on X position
        # LDA $CB,X / ROL $CB,X / ROR / DEX / BEQ +5 / ROL $CC,X / ROR / INX / ADC $D3,X / STA $D3,X
        # This appears to add half the X velocity to X position (fine-tuning landing spot)
        # For accuracy, let's implement this:
        x_vel = self.memory.read(self.x_vel_addr)
        # ROL then ROR effectively divides by 2 (with some carry magic)
        # Simplified: add half of velocity to position
        if x_vel >= 128:  # Negative velocity
            x_vel_signed = x_vel - 256
        else:
            x_vel_signed = x_vel
        x_adjustment = x_vel_signed // 2
        x_pos = (x_pos + x_adjustment) & 0xFF
        self.memory.write(self.x_pos_addr, x_pos)
        
        # F50C-F50E: LDA #$07 / STA $D7,X - Set Y position to 7 (top)
        self.memory.write(self.y_pos_addr, 0x07)
        
        # F510-F512: LDA #$00 / STA $CB,X - Clear X velocity
        self.memory.write(self.x_vel_addr, 0x00)
        
        # F514-F518: LDA $C3,X / AND #$FD / STA $C3,X - Clear tongue flag (bit 1)
        flags = self.memory.read(self.flags_addr)
        flags &= 0xFD
        self.memory.write(self.flags_addr, flags)
    
    def state_water(self):
        """State 6: Fell in water."""
        pass
    
    def check_landing(self):
        """
        Check if frog landed on lily pad or in water.
        
        Assembly F546 (Subroutine_F546):
        Checks if X position is within lily pad ranges:
        - 0x0D to 0x43 (13-67): Left lily pad
        - 0x52 to 0x88 (82-136): Right lily pad
        Returns carry set if on lily pad, carry clear if in water.
        """
        x_pos = self.memory.read(self.x_pos_addr)
        y_pos = self.memory.read(self.y_pos_addr)
        
        if y_pos >= 0x99:
            self.memory.write(self.y_pos_addr, 0x99)
            
            # Check if on lily pad (assembly F546)
            on_lily_pad = False
            if 0x0D <= x_pos < 0x44:  # Left lily pad range
                on_lily_pad = True
            elif 0x52 <= x_pos < 0x89:  # Right lily pad range
                on_lily_pad = True
            
            if on_lily_pad:
                # Land on lily pad (state 3)
                self.memory.write(self.state_addr, self.STATE_LANDING)
            else:
                # Fell in water - need to implement water state
                # For now, just clamp position and land
                if x_pos < 8:
                    self.memory.write(self.x_pos_addr, 8)
                elif x_pos > 147:
                    self.memory.write(self.x_pos_addr, 147)
                self.memory.write(self.state_addr, self.STATE_LANDING)
