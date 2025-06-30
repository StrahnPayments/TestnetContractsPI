import os
import sys
import json
import base64
import hashlib # For SHA-256 hashing
import time    # To get a unique timestamp for no-op txns
import nacl.signing # New import for Ed25519 signing

from algosdk.v2client import algod
from algosdk import account, transaction, encoding, util
from algosdk.logic import get_application_address

# Assuming test_mnemonic.py is available and get_account_details_from_mnemonic is in it
from test_mnemonic import get_account_details_from_mnemonic 

# =================================================================================
# 1. CONFIGURATION
# =================================================================================

# Algod client configuration
algod_address = "https://testnet-api.algonode.cloud"
algod_token = ""  # No token needed for AlgoNode public nodes
algod_client = algod.AlgodClient(algod_token, algod_address)

# Official TestNet USDC Asset ID (obtained during initial setup)
DEFAULT_USDC_ASSET_ID = 10458941

# =================================================================================
# 2. HELPER FUNCTIONS
# =================================================================================

def wait_for_confirmation(client, txid_or_groupid):
    """Waits for a transaction or group to be confirmed."""
    last_round = client.status().get('last-round')
    txinfo = client.pending_transaction_info(txid_or_groupid)
    while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
        print("Waiting for confirmation...")
        last_round = client.status().get('last-round') 
        client.status_after_block(last_round)
        txinfo = client.pending_transaction_info(txid_or_groupid)
    print(f"Transaction {txid_or_groupid} confirmed in round {txinfo.get('confirmed-round')}")
    return txinfo

def get_app_global_state(client, app_id):
    """Fetches an application's global state."""
    app_info = client.application_info(app_id)
    global_state = app_info['params']['global-state']
    
    decoded_state = {}
    for item in global_state:
        key = base64.b64decode(item['key']).decode('utf-8')
        if item['value']['type'] == 1: # Bytes
            decoded_state[key] = base64.b64decode(item['value']['bytes'])
        else: # Uint
            decoded_state[key] = item['value']['uint']
    return decoded_state

# =================================================================================
# 3. ON-CHAIN <-> OFF-CHAIN CONVERSION HELPERS (EMULATING PYTEAL)
# =================================================================================

# IMPORTANT: This must precisely match PyTeal's Itob behavior
def emulate_pyteal_itob(val: int) -> bytes:
    """Emulates PyTeal's Itob (Integer to Big-endian Bytes) for off-chain message signing.
    
    Itob converts a uint64 to the minimum length big-endian byte array.
    """
    if val == 0:
        return b'\x00'
    
    num_bytes = (val.bit_length() + 7) // 8
    return val.to_bytes(num_bytes, 'big')

# =================================================================================
# 4. INTERACTION FUNCTIONS
# =================================================================================

def handle_deposit_usdc(creator_private_key, creator_address, pi_base_app_id, usdc_id):
    print("\n--- Deposit USDC ---")
    pi_base_app_address = get_application_address(pi_base_app_id)

    amount_str = input('Enter USDC amount to deposit (e.g., 100): ')
    if not amount_str.isdigit() or int(amount_str) <= 0:
        print('Invalid amount. Deposit cancelled.')
        return

    deposit_amount_usdc = int(amount_str) * 1_000_000 # Assuming 6 decimals for USDC

    print(f"Preparing to deposit {deposit_amount_usdc / 1_000_000} USDC to {pi_base_app_address}...")

    params = algod_client.suggested_params()
    params.flat_fee = True 
    params.fee = 2 * 1000 # Corrected to use 1000 for min_fee (2 transaction group)

    asset_xfer_txn = transaction.AssetTransferTxn(
        sender=creator_address,
        sp=params,
        receiver=pi_base_app_address,
        amt=deposit_amount_usdc,
        index=usdc_id
    )

    app_call_txn = transaction.ApplicationCallTxn(
        sender=creator_address,
        sp=params,
        index=pi_base_app_id,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"deposit_usdc"],
        foreign_assets=[usdc_id]
    )

    group_txns = [asset_xfer_txn, app_call_txn]
    gid = transaction.calculate_group_id(group_txns)
    # Corrected: Use .group instead of .group_id for assignment
    for txn in group_txns:
        txn.group = gid 
    
    signed_txns = []
    for txn in group_txns:
        signed_txns.append(txn.sign(creator_private_key))
    
    try:
        algod_client.send_transactions(signed_txns)
        tx_info = wait_for_confirmation(algod_client, gid)
        print(f"USDC deposit successful! Transaction Group ID: {gid.hex()}")
        
    except Exception as e:
        print(f"USDC deposit failed: {e}")


def handle_process_intent(creator_private_key, creator_address, pi_base_app_id, usdc_id, current_nonce):
    print("\n--- Process One-Time Payment Intent ---")
    
    dest_addr_str = input('Enter recipient Algorand address (e.g., another Pera Wallet address): ')
    if not encoding.is_valid_address(dest_addr_str):
        print('Invalid address. Payment cancelled.')
        return

    amount_str = input('Enter USDC amount to send (e.g., 5.5): ')
    try:
        amount_float = float(amount_str)
        if amount_float <= 0: raise ValueError
    except ValueError:
        print('Invalid amount. Amount must be a positive number. Payment cancelled.')
        return

    relayer_fee_str = input('Enter Relayer Fee (in whole USDC, e.g., 0.01 for 1 cent): ')
    try:
        relayer_fee_float = float(relayer_fee_str)
        if relayer_fee_float < 0: raise ValueError
    except ValueError:
        print('Invalid fee. Fee must be a non-negative number. Payment cancelled.')
        return

    destination_raw_address = encoding.decode_address(dest_addr_str)
    send_amount_usdc = int(amount_float * 1_000_000) # Convert to microUSDC with decimals
    relayer_fee_usdc = int(relayer_fee_float * 1_000_000) # Convert to microUSDC with decimals
    
    # --- IMPORTANT: Off-chain message construction (must perfectly match contract) ---
    # Contract: Concat(Bytes("SPP_V1:"), Itob(Global.current_application_id()), Itob(nonce), destination, Itob(amount), Itob(relayer_fee))
    
    message_bytes_for_signing = b"".join([
        b"SPP_V1:",
        emulate_pyteal_itob(pi_base_app_id),
        emulate_pyteal_itob(current_nonce),
        destination_raw_address, # Already 32 bytes from decode_address
        emulate_pyteal_itob(send_amount_usdc),
        emulate_pyteal_itob(relayer_fee_usdc)
    ])
    
    # Hash the message (SHA-256)
    hashed_message = hashlib.sha256(message_bytes_for_signing).digest()
    
    # --- CRITICAL FIX: Use nacl.signing for raw Ed25519 signature ---
    # Create SigningKey from the private key bytes
    # Private key for nacl must be 32 bytes (which account.private_key_from_seed/derive gives)
    nacl_private_key = creator_private_key[:32] 
    
    # Create SigningKey from the correctly sized private key bytes
    signing_key = nacl.signing.SigningKey(nacl_private_key)
    # Sign the HASHED message. nacl produces a 64-byte raw signature.
    # The signature object contains both the message and the signature; we want just the signature.
    signed_offchain_nacl = signing_key.sign(hashed_message) # This creates a SignedMessage object
    signature_bytes = signed_offchain_nacl.signature # This is the raw 64-byte signature Ed25519Verify expects

    print(f"\nMessage for signing (hex): {message_bytes_for_signing.hex()}")
    print(f"Hashed message (hex): {hashed_message.hex()}")
    print(f"Generated signature (base64): {base64.b64encode(signature_bytes).decode('utf-8')}")
    
    params = algod_client.suggested_params()
    params.flat_fee = True
    
    # Increase dynamic cost budget using extra calls (Each provides 700 budget units)
    num_extra_noop_txns = 2 # 2 extra no-ops for a total of 3 txns (main + 2 noop) => 2100 budget
    params.fee = 1000 # Base fee for each txn in the group

    # 1. Primary app call for process_intent
    main_app_call_txn = transaction.ApplicationCallTxn(
        sender=creator_address, # Creator acts as relayer here
        sp=params,
        index=pi_base_app_id,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[
            b"process_intent",
            destination_raw_address,
            emulate_pyteal_itob(send_amount_usdc),
            emulate_pyteal_itob(relayer_fee_usdc),
            emulate_pyteal_itob(current_nonce),
            signature_bytes # Raw 64-byte signature
        ],
        foreign_assets=[usdc_id] # Indicate asset used in inner transfer
    )
    
    txns_in_group = [main_app_call_txn]
    for i in range(num_extra_noop_txns):
        noop_arg = b"noop_budget_" + str(i).encode() + b"_" + str(int(time.time())).encode()
        noop_txn = transaction.ApplicationCallTxn(
            sender=creator_address,
            sp=params, 
            index=pi_base_app_id,
            on_complete=transaction.OnComplete.NoOpOC,
            app_args=[noop_arg],
        )
        txns_in_group.append(noop_txn)

    # Group and sign all transactions
    gid = transaction.calculate_group_id(txns_in_group)
    for txn in txns_in_group:
        txn.group = gid # Corrected assignment to .group
    
    signed_txns = []
    for txn in txns_in_group:
        signed_txns.append(txn.sign(creator_private_key))
    
    try:
        algod_client.send_transactions(signed_txns)
        tx_info = wait_for_confirmation(algod_client, gid) 
        print(f"Payment intent processed successfully! Transaction Group ID: {gid.hex()}")
        
    except Exception as e:
        print(f"Processing intent failed: {e}")

# =================================================================================
# 5. MAIN SCRIPT LOGIC
# =================================================================================

def main():
    try:
        creator_private_key, creator_address = get_account_details_from_mnemonic()
        creator_private_key = creator_private_key.encode()
        
        # --- DEBUGGING PRINTS ---
        print(f"DEBUG: Type of creator_private_key: {type(creator_private_key)}")
        print(f"DEBUG: Length of creator_private_key: {len(creator_private_key) if isinstance(creator_private_key, bytes) else 'N/A'}")
        print(f"DEBUG: Hex of creator_private_key (first 10 bytes): {creator_private_key[:10].hex()}")
        # --- END DEBUGGING PRINTS ---

    except ValueError as e:
        print(f"Error: {e}")
        print("Please ensure your 'test_mnemonic.py' file is correctly configured to return (private_key_bytes, address_str).")
        sys.exit(1)

    # Load deployment info
    deployment_info = {}
    try:
        with open("deployment_info.json", "r") as f:
            deployment_info = json.load(f)
    except FileNotFoundError:
        print("Error: deployment_info.json not found. Please run deploy.py first.")
        sys.exit(1)

    pi_base_app_id = deployment_info.get("pi_base_app_id")
    usdc_id = deployment_info.get("usdc_id", DEFAULT_USDC_ASSET_ID) 
    
    if not pi_base_app_id:
        print("Error: pi_base_app_id missing in deployment_info.json. Please re-run deploy.py.")
        sys.exit(1)

    try:
        pi_base_global_state = get_app_global_state(algod_client, pi_base_app_id)
        current_nonce = pi_base_global_state.get('creator_nonce', 0)
        
        pi_base_account_info = algod_client.account_info(get_application_address(pi_base_app_id))
        pi_base_usdc_balance = 0
        for asset in pi_base_account_info.get('assets', []):
            if asset['asset-id'] == usdc_id:
                pi_base_usdc_balance = asset['amount'] / 1_000_000
                break
        
        print(f"\n--- Current PI Base App State (ID: {pi_base_app_id}) ---")
        print(f"PI Base Address: {get_application_address(pi_base_app_id)}")
        print(f"Creator Address: {encoding.encode_address(pi_base_global_state.get('creator_addr', b''))}")
        # Not showing strahn_core_app_id or usdc_id from PI Base global state directly here, to avoid `None` print if not present
        if 'strahn_core_app_id' in pi_base_global_state:
            print(f"Strahn Core App ID (configured): {pi_base_global_state['strahn_core_app_id']}")
        if 'usdc_id' in pi_base_global_state:
            print(f"Configured USDC ID: {pi_base_global_state['usdc_id']}")

        print(f"Current Nonce: {current_nonce}")
        print(f"USDC Balance: {pi_base_usdc_balance} tUSDC")
        print("------------------------------------------")

    except Exception as e:
        print(f"Error fetching PI Base App state: {e}. Is it deployed correctly and funded for state storage?")
        sys.exit(1)
        
    while True:
        print("\nWhat would you like to do?")
        print("1. Deposit tUSDC to PI Base")
        print("2. Process One-Time Payment Intent from PI Base")
        print("3. Exit")
        
        choice = input("Enter your choice (1, 2, or 3): ").strip()
        
        if choice == '1':
            handle_deposit_usdc(creator_private_key, creator_address, pi_base_app_id, usdc_id)
        elif choice == '2':
            # Pass the current nonce, which will be verified by the contract
            handle_process_intent(creator_private_key, creator_address, pi_base_app_id, usdc_id, current_nonce)
            # After an intent, refresh nonce for subsequent actions in the same session
            try:
                refreshed_state = get_app_global_state(algod_client, pi_base_app_id)
                current_nonce = refreshed_state.get('creator_nonce', current_nonce)
                print(f"Nonce refreshed: Current on-chain nonce is now {current_nonce}")
            except Exception as e:
                print(f"Could not refresh nonce for next action: {e}")
        elif choice == '3':
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

    print("Exiting interactive script.")

if __name__ == "__main__":
    main()