#!/usr/bin/env python3
"""
Deploy Strahn PI System contracts to Algorand
"""

import os
import sys
from pathlib import Path
from algosdk import account, mnemonic
from algosdk.v2client import algod
from algosdk.transaction import ApplicationCreateTxn, wait_for_confirmation
from algosdk.logic import get_application_address
import base64

# Add the parent directory to the path
sys.path.append(str(Path(__file__).parent.parent))

class ContractDeployer:
    def __init__(self, algod_client, private_key):
        self.algod_client = algod_client
        self.private_key = private_key
        self.sender = account.address_from_private_key(private_key)
        
    def load_contract(self, contract_name):
        """Load compiled TEAL programs"""
        build_dir = Path(__file__).parent.parent / "build"
        
        approval_path = build_dir / f"{contract_name}_approval.teal"
        clear_path = build_dir / f"{contract_name}_clear.teal"
        
        with open(approval_path, "r") as f:
            approval_program = f.read()
            
        with open(clear_path, "r") as f:
            clear_program = f.read()
            
        return approval_program, clear_program
    
    def compile_program(self, source_code):
        """Compile TEAL source to bytecode"""
        compile_response = self.algod_client.compile(source_code)
        return base64.b64decode(compile_response['result'])
    
    def deploy_contract(self, contract_name, global_schema, local_schema, app_args=None):
        """Deploy a single contract"""
        print(f"Deploying {contract_name}...")
        
        # Load and compile programs
        approval_teal, clear_teal = self.load_contract(contract_name)
        approval_program = self.compile_program(approval_teal)
        clear_program = self.compile_program(clear_teal)
        
        # Get suggested parameters
        params = self.algod_client.suggested_params()
        
        # Create application transaction
        txn = ApplicationCreateTxn(
            sender=self.sender,
            sp=params,
            on_complete=0,  # NoOp
            approval_program=approval_program,
            clear_program=clear_program,
            global_schema=global_schema,
            local_schema=local_schema,
            app_args=app_args or []
        )
        
        # Sign and send transaction
        signed_txn = txn.sign(self.private_key)
        tx_id = self.algod_client.send_transaction(signed_txn)
        
        # Wait for confirmation
        result = wait_for_confirmation(self.algod_client, tx_id, 4)
        app_id = result['application-index']
        app_address = get_application_address(app_id)
        
        print(f"✓ {contract_name} deployed successfully!")
        print(f"  App ID: {app_id}")
        print(f"  Address: {app_address}")
        
        return app_id, app_address

def main():
    """Main deployment function"""
    # Configuration
    algod_address = os.getenv("ALGOD_ADDRESS", "https://testnet-api.algonode.cloud")
    algod_token = os.getenv("ALGOD_TOKEN", "")
    
    # Initialize Algod client
    algod_client = algod.AlgodClient(algod_token, algod_address)
    
    # Get private key from environment or generate new one
    private_key_mnemonic = os.getenv("DEPLOYER_MNEMONIC")
    if not private_key_mnemonic:
        print("Error: DEPLOYER_MNEMONIC environment variable not set")
        return 1
    
    try:
        private_key = mnemonic.to_private_key(private_key_mnemonic)
    except Exception as e:
        print(f"Error: Invalid mnemonic: {e}")
        return 1
    
    deployer = ContractDeployer(algod_client, private_key)
    
    try:
        # Deploy Strahn Core (factory contract)
        print("Deploying Strahn Core contract...")
        core_app_id, core_address = deployer.deploy_contract(
            "strahn_core",
            global_schema={"num_uints": 1, "num_byte_slices": 1},  # owner_addr
            local_schema={"num_uints": 0, "num_byte_slices": 0}
        )
        
        print(f"\nDeployment Summary:")
        print(f"Strahn Core App ID: {core_app_id}")
        print(f"Strahn Core Address: {core_address}")
        
        print(f"\nNext steps:")
        print(f"1. Fund the deployer account: {deployer.sender}")
        print(f"2. Update the Core contract with mandate bytecode")
        print(f"3. Deploy PI Base contracts for users")
        
        return 0
        
    except Exception as e:
        print(f"Error during deployment: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())