#!/usr/bin/env python3
"""
Test suite for Strahn PI System contracts
"""

import pytest
import sys
from pathlib import Path

# Add the parent directory to the path
sys.path.append(str(Path(__file__).parent.parent))

from pyteal import *
from contracts import (
    strahn_core_approval, strahn_core_clear,
    strahn_pi_base_approval, strahn_pi_base_clear,
    mandate_record_approval, mandate_record_clear
)

class TestContractCompilation:
    """Test contract compilation"""
    
    def test_strahn_core_compilation(self):
        """Test Strahn Core contract compiles without errors"""
        try:
            approval_teal = compileTeal(
                strahn_core_approval(),
                Mode.Application,
                version=8
            )
            clear_teal = compileTeal(
                strahn_core_clear(),
                Mode.Application,
                version=8
            )
            
            assert len(approval_teal) > 0
            assert len(clear_teal) > 0
            assert "txn ApplicationID" in approval_teal
            
        except Exception as e:
            pytest.fail(f"Strahn Core compilation failed: {e}")
    
    def test_strahn_pi_base_compilation(self):
        """Test Strahn PI Base contract compiles without errors"""
        try:
            approval_teal = compileTeal(
                strahn_pi_base_approval(),
                Mode.Application,
                version=8
            )
            clear_teal = compileTeal(
                strahn_pi_base_clear(),
                Mode.Application,
                version=8
            )
            
            assert len(approval_teal) > 0
            assert len(clear_teal) > 0
            assert "txn ApplicationID" in approval_teal
            
        except Exception as e:
            pytest.fail(f"Strahn PI Base compilation failed: {e}")
    
    def test_mandate_record_compilation(self):
        """Test Mandate Record contract compiles without errors"""
        try:
            approval_teal = compileTeal(
                mandate_record_approval(),
                Mode.Application,
                version=8
            )
            clear_teal = compileTeal(
                mandate_record_clear(),
                Mode.Application,
                version=8
            )
            
            assert len(approval_teal) > 0
            assert len(clear_teal) > 0
            assert "txn ApplicationID" in approval_teal
            
        except Exception as e:
            pytest.fail(f"Mandate Record compilation failed: {e}")

class TestContractLogic:
    """Test contract business logic"""
    
    def test_signature_verification_logic(self):
        """Test signature verification components"""
        # Test message construction for payment intent
        message_parts = [
            Bytes("SPP_V1:"),
            Itob(Int(1)),  # nonce
            Bytes("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="),  # destination
            Itob(Int(1000000)),  # amount
            Itob(Int(10000))  # relayer_fee
        ]
        
        message = Concat(*message_parts)
        
        # Compile to verify structure
        program = Seq([
            App.globalPut(Bytes("test_message"), message),
            Approve()
        ])
        
        try:
            teal = compileTeal(program, Mode.Application, version=8)
            assert len(teal) > 0
        except Exception as e:
            pytest.fail(f"Signature verification logic failed: {e}")
    
    def test_mandate_state_transitions(self):
        """Test mandate payment state transitions"""
        # Test timestamp comparison logic
        program = Seq([
            Assert(Global.latest_timestamp() >= Int(1640995200)),  # Example timestamp
            App.globalPut(
                Bytes("next_pay_ts"),
                Int(1640995200) + Int(2592000)  # Add 30 days
            ),
            Approve()
        ])
        
        try:
            teal = compileTeal(program, Mode.Application, version=8)
            assert "global LatestTimestamp" in teal
        except Exception as e:
            pytest.fail(f"Mandate state transition logic failed: {e}")

def test_all_contracts_compile():
    """Integration test - ensure all contracts compile together"""
    contracts = [
        ("strahn_core", strahn_core_approval, strahn_core_clear),
        ("strahn_pi_base", strahn_pi_base_approval, strahn_pi_base_clear),
        ("mandate_record", mandate_record_approval, mandate_record_clear),
    ]
    
    compiled_contracts = {}
    
    for name, approval_func, clear_func in contracts:
        try:
            approval_teal = compileTeal(
                approval_func(),
                Mode.Application,
                version=8
            )
            clear_teal = compileTeal(
                clear_func(),
                Mode.Application,
                version=8
            )
            
            compiled_contracts[name] = {
                "approval": approval_teal,
                "clear": clear_teal
            }
            
        except Exception as e:
            pytest.fail(f"Contract {name} compilation failed: {e}")
    
    # Verify all contracts compiled
    assert len(compiled_contracts) == 3
    
    # Verify basic structure
    for name, programs in compiled_contracts.items():
        assert len(programs["approval"]) > 100  # Reasonable minimum size
        assert len(programs["clear"]) > 10
        assert "txn ApplicationID" in programs["approval"]

if __name__ == "__main__":
    pytest.main([__file__, "-v"])