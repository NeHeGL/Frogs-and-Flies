"""
Collision Detection System - Frog catches fly

Based on assembly routine LF6BE (TIA hardware collision detection)
Uses TIA collision registers: CXM0FB, CXM1FB (missiles vs ball/playfield)
"""

from sound_system import get_sound_system

class CollisionDetector:
    """
    Handles collision detection between frog tongues (ball) and flies (missiles).
    
    CRITICAL: Uses TIA hardware collision registers, NOT position checking!
    Assembly F6BE reads:
    - CXM0FB ($02): Missile 0 (fly 0) collision with ball (tongue) or playfield
    - CXM1FB ($03): Missile 1 (fly 1) collision with ball (tongue) or playfield
    
    The TIA hardware automatically sets bit 7 when missile collides with ball.
    The display kernel simulates this by checking sprite overlap during rendering.
    """
    
    def __init__(self, memory):
        self.memory = memory
    
    def check_collisions(self):
        """
        Check TIA collision registers for fly catches.
        
        Assembly F6BE:
        - LDY #$00 (assume no collision)
        - LDA CXM0FB / ASL / BMI → collision on fly 0
        - LDA CXM1FB / ASL / BPL → no collision on fly 1
        - INY (Y=1 for fly 1 collision)
        
        ASL shifts bit 7 into carry, BMI checks if bit 7 was set (negative).
        """
        # Read collision registers (set by display kernel)
        cxm0fb = self.memory.read(0x02)  # Missile 0 collision
        cxm1fb = self.memory.read(0x03)  # Missile 1 collision
        
        # Check fly 0 collision (bit 7 of CXM0FB)
        if cxm0fb & 0x80:
            self.handle_fly_catch(0)
        
        # Check fly 1 collision independently — both can be caught in same frame
        if cxm1fb & 0x80:
            self.handle_fly_catch(1)
    
    def handle_fly_catch(self, fly_num):
        """
        Handle a fly being caught.
        
        Awards 2 points in BCD to the frog whose tongue pixel-perfectly touched the fly.
        
        The renderer tracks which player's tongue pixels overlapped with each fly's
        pixels during rendering, storing the result in $F0 (fly 0 catcher) and
        $F1 (fly 1 catcher). 0=P0 caught it, 1=P1 caught it, 0xFF=no pixel hit.
        
        This means both frogs can simultaneously catch different flies and each
        gets their own score — there's no ambiguity.
        
        Args:
            fly_num: 0 or 1 (which fly was caught)
        """
        # Read pixel-perfect collision attribution set by the renderer
        # $F0 = which player caught fly 0 (0=P0, 1=P1, 0xFF=unknown)
        # $F1 = which player caught fly 1 (0=P0, 1=P1, 0xFF=unknown)
        catcher_addr = 0xF0 + fly_num
        catcher = self.memory.read(catcher_addr)
        
        if catcher == 0:
            player_num = 0
        elif catcher == 1:
            player_num = 1
        else:
            # No pixel-level hit recorded — fall back to closest frog with active tongue
            fly_x = self.memory.read(0xD5 + fly_num)
            p0_tongue = bool(self.memory.read(0xC3) & 0x02)
            p1_tongue = bool(self.memory.read(0xC4) & 0x02)
            p0_x = self.memory.read(0xD3)
            p1_x = self.memory.read(0xD4)
            if p0_tongue and not p1_tongue:
                player_num = 0
            elif p1_tongue and not p0_tongue:
                player_num = 1
            else:
                player_num = 0 if abs(fly_x - p0_x) <= abs(fly_x - p1_x) else 1
        
        # Play catch sound
        sound = get_sound_system()
        sound.play_catch_fly()
        
        # Award 2 points in BCD (assembly F6E0-F6E9)
        score_addr = 0xBB + player_num
        score = self.memory.read(score_addr)
        
        # BCD addition: ADC #$02 with SED (decimal mode)
        ones = score & 0x0F
        tens = (score >> 4) & 0x0F
        
        ones += 2
        if ones > 9:
            ones -= 10
            tens += 1
            if tens > 9:
                tens = 9
                ones = 9  # Max score = 99
        
        new_score = (tens << 4) | ones
        self.memory.write(score_addr, new_score)
        
        # Reset fly (assembly F6EA-F6F3)
        # Set Y position to 0 (off-screen marker for respawn)
        self.memory.write(0xD9 + fly_num, 0x00)
        # Clear velocities
        self.memory.write(0xCD + fly_num, 0x00)  # X velocity
        self.memory.write(0xD1 + fly_num, 0x00)  # Y velocity
