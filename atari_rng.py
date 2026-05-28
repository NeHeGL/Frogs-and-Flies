"""
Atari 2600 Random Number Generator
Exact implementation of the LCG from assembly code at $F781

Formula: seed = (seed × 137 + 149) & 0xFF
"""

class AtariRNG:
    """
    Linear Congruential Generator matching the Atari 2600 assembly code.
    
    Assembly code at $F781:
        LDA $E4       ; Load seed
        ASL           ; Multiply by 16
        ASL
        ASL
        ASL
        CLC
        ADC $E4       ; Add original (×17)
        ASL           ; Multiply by 8
        ASL
        ASL
        CLC
        ADC $E4       ; Add original (×137)
        CLC
        ADC #$95      ; Add constant (149)
        STA $E4       ; Store new seed
        RTS
    
    This implements: seed = (seed × 137 + 149) mod 256
    """
    
    def __init__(self, seed=0):
        """
        Initialize the RNG with a seed value.
        
        Args:
            seed: Initial seed value (0-255). The original game uses
                  the INTIM timer value at startup for randomness.
        """
        self.seed = seed & 0xFF
    
    def next(self):
        """
        Generate the next random number.
        
        Returns:
            Random number (0-255)
        """
        # Step 1: seed × 16
        result = (self.seed << 4) & 0xFF
        
        # Step 2: Add original seed (now seed × 17)
        result = (result + self.seed) & 0xFF
        
        # Step 3: Multiply by 8 (now seed × 136)
        result = (result << 3) & 0xFF
        
        # Step 4: Add original seed (now seed × 137)
        result = (result + self.seed) & 0xFF
        
        # Step 5: Add constant 149 ($95)
        result = (result + 0x95) & 0xFF
        
        # Update seed
        self.seed = result
        return result
    
    def get_seed(self):
        """Get the current seed value."""
        return self.seed
    
    def set_seed(self, seed):
        """Set the seed value."""
        self.seed = seed & 0xFF
    
    def next_range(self, min_val, max_val):
        """
        Generate a random number in a specific range.
        
        Args:
            min_val: Minimum value (inclusive)
            max_val: Maximum value (inclusive)
        
        Returns:
            Random number in range [min_val, max_val]
        """
        range_size = max_val - min_val + 1
        return min_val + (self.next() % range_size)
    
    def next_bool(self):
        """
        Generate a random boolean.
        
        Returns:
            True or False
        """
        return bool(self.next() & 0x80)  # Check bit 7


# Global RNG instance (matches $E4 in assembly)
_global_rng = None

def get_rng():
    """Get the global RNG instance."""
    global _global_rng
    if _global_rng is None:
        # Initialize with a semi-random seed
        # In the original game, this would be INTIM at startup
        import time
        seed = int(time.time() * 1000) & 0xFF
        _global_rng = AtariRNG(seed)
    return _global_rng

def set_rng_seed(seed):
    """Set the global RNG seed."""
    global _global_rng
    if _global_rng is None:
        _global_rng = AtariRNG(seed)
    else:
        _global_rng.set_seed(seed)
