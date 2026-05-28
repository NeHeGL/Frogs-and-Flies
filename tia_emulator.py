"""
TIA (Television Interface Adapter) Emulation
Handles the graphics rendering logic for the Atari 2600
"""

# Import the authentic NTSC palette extracted from reference image
from atari_ntsc_palette import COLORS


def decode_playfield_scanline(pf0, pf1, pf2, reflect=False):
    """
    Decode a playfield scanline from PF0, PF1, PF2 registers.
    Returns a list of 40 pixels (0 or 1).
    
    This implements the exact bit ordering from Andrew Davie's tutorials:
    - PF0: bits 7,6,5,4 -> pixels 0,1,2,3 (REVERSED)
    - PF1: bits 7,6,5,4,3,2,1,0 -> pixels 4-11 (NORMAL)
    - PF2: bits 7,6,5,4,3,2,1,0 -> pixels 19,18,17,16,15,14,13,12 (REVERSED)
    
    IMPORTANT: PF0 only uses bits 7-4 (D7-D4). Bits 3-0 are ignored by TIA hardware.
    """
    pixels = [0] * 40
    
    # PF0 - only bits 7-4 are used (mask with 0xF0), reversed order
    # Bits 7,6,5,4 map to pixels 0,1,2,3
    pf0 = pf0 & 0xF0  # Mask to only use upper 4 bits
    for i in range(4):
        bit = (pf0 >> (4 + i)) & 1  # Read bits 4,5,6,7 for pixels 0,1,2,3
        pixels[i] = bit
    
    # PF1 - 8 bits, normal order
    for i in range(8):
        bit = (pf1 >> (7 - i)) & 1
        pixels[4 + i] = bit
    
    # PF2 - 8 bits, reversed order
    for i in range(8):
        bit = (pf2 >> (7 - i)) & 1
        pixels[19 - i] = bit
    
    # Right half: mirror or duplicate
    if reflect:
        # TIA reflect mode: right half shows PF2-PF1-PF0 (reverse order of left half)
        # Left half: PF0(0-3), PF1(4-11), PF2(12-19)
        # Right half: PF2(20-27), PF1(28-35), PF0(36-39)
        # This means: pixel 20 = pixel 19, pixel 21 = pixel 18, ..., pixel 39 = pixel 0
        for i in range(20):
            pixels[20 + i] = pixels[19 - i]
    else:
        # Duplicate mode: right half is exact copy of left half
        for i in range(20):
            pixels[20 + i] = pixels[i]
    
    return pixels


def decode_sprite_line(grp_data, reflect=False):
    """
    Decode an 8-bit sprite graphics line.
    Returns a list of 8 pixels (0 or 1).
    """
    pixels = [0] * 8
    for i in range(8):
        bit = (grp_data >> (7 - i)) & 1
        pixels[i] = bit
    
    if reflect:
        pixels.reverse()
    
    return pixels


class Memory:
    """Emulates the Atari 2600 memory system."""
    def __init__(self):
        # Zero page RAM ($80-$FF = 128 bytes)
        self.ram = [0] * 256
        
        # TIA registers (write-only in real hardware, but we track them)
        self.tia = [0] * 64
        
        # RIOT (PIA) registers at $0280-$029F
        self.riot = [0] * 32
        
        # Game-specific RAM locations (from the disassembly)
        self.ram[0x80] = 0x00  # $80 - XOR mask for playfield (player turn)
        self.ram[0xB3] = 0x00  # $B3 - Frame counter
        self.ram[0xB4] = 0x00  # $B4 - Game over flag
        self.ram[0xB7] = 0x07  # $B7 - Timer level
        self.ram[0xB8] = 0x1A  # $B8 - Timer countdown
        self.ram[0xBB] = 0x00  # $BB - Player 1 score (BCD)
        self.ram[0xBC] = 0x00  # $BC - Player 2 score (BCD)
        
    def read(self, addr):
        """Read from memory address."""
        if addr < 0x80:
            # TIA registers (0x00-0x7F)
            return self.tia[addr & 0x3F]  # TIA mirrors every 64 bytes
        elif 0x0280 <= addr <= 0x029F:
            # RIOT registers (0x0280-0x029F)
            return self.riot[addr & 0x1F]
        else:
            # RAM (0x80-0xFF, mirrored)
            return self.ram[addr & 0xFF]
    
    def write(self, addr, value):
        """Write to memory address."""
        if addr < 0x80:
            # TIA registers (0x00-0x7F)
            self.tia[addr & 0x3F] = value & 0xFF
        elif 0x0280 <= addr <= 0x029F:
            # RIOT registers (0x0280-0x029F) - includes SWCHA at 0x0280
            self.riot[addr & 0x1F] = value & 0xFF
        else:
            # RAM (0x80-0xFF, mirrored)
            self.ram[addr & 0xFF] = value & 0xFF
