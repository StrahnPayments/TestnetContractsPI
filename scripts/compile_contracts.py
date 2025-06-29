#!/usr/bin/env python3
"""
Compile all Strahn PI System contracts to TEAL
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path to import contracts
sys.path.append(str(Path(__file__).parent.parent))

from pyteal import *
from contracts import (
    strahn_core_approval, strahn_core_clear,
    strahn_pi_base_approval, strahn_pi_base_clear,
    mandate_record_approval, mandate_record_clear
)

def ensure_build_directory():
    """Ensure the build directory exists"""
    build_dir = Path(__file__).parent.parent / "build"
    build_dir.mkdir(exist_ok=True)
    return build_dir

def compile_contract(approval_func, clear_func, contract_name):
    """Compile a single contract to TEAL"""
    print(f"Compiling {contract_name}...")
    
    # Compile approval program
    approval_teal = compileTeal(
        approval_func(),
        Mode.Application,
        version=8
    )
    
    # Compile clear program
    clear_teal = compileTeal(
        clear_func(),
        Mode.Application,
        version=8
    )
    
    return approval_teal, clear_teal

def main():
    """Main compilation function"""
    build_dir = ensure_build_directory()
    
    contracts = [
        (strahn_core_approval, strahn_core_clear, "strahn_core"),
        (strahn_pi_base_approval, strahn_pi_base_clear, "strahn_pi_base"),
        (mandate_record_approval, mandate_record_clear, "mandate_record"),
    ]
    
    print("Starting contract compilation...")
    
    for approval_func, clear_func, contract_name in contracts:
        try:
            approval_teal, clear_teal = compile_contract(
                approval_func, clear_func, contract_name
            )
            
            # Write approval program
            approval_path = build_dir / f"{contract_name}_approval.teal"
            with open(approval_path, "w") as f:
                f.write(approval_teal)
            
            # Write clear program
            clear_path = build_dir / f"{contract_name}_clear.teal"
            with open(clear_path, "w") as f:
                f.write(clear_teal)
            
            print(f"✓ {contract_name} compiled successfully")
            
        except Exception as e:
            print(f"✗ Error compiling {contract_name}: {e}")
            return 1
    
    print(f"\nAll contracts compiled successfully!")
    print(f"Output directory: {build_dir}")
    return 0

if __name__ == "__main__":
    sys.exit(main())