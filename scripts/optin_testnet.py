import os
import sys
import json
import base64
from algosdk.v2client import algod
from algosdk import account, transaction, encoding
from algosdk.logic import get_application_address
from test_mnemonic import *

# =================================================================================
# 1. CONFIGURATION
# =================================================================================

# Algod client configuration
algod_address = "https://testnet-api.algonode.cloud"
algod_token = ""  # No token needed for AlgoNode public nodes
algod_client = algod.AlgodClient(algod_token, algod_address)

# Official TestNet USDC Asset ID
USDC_ASSET_ID = 10458941

# Minimum balance needed for a contract to opt into an ASA (0.1 ALGO)
OPTIN_MIN_BALANCE_AMOUNT = 100_000 # microAlgos

# =================================================================================
# 2. HELPER FUNCTIONS
# =================================================================================

def wait_for_confirmation(client, txid_or_groupid):
    """Waits for a transaction or group to be confirmed."""
    last_round = client.status().get('last-round')
    txinfo = client.pending_transaction_info(txid_or_groupid)
    while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
        print("Waiting for confirmation...")
        last_round = client.status().get('last-round') # Update last_round in loop
        client.status_after_block(last_round)
        txinfo = client.pending_transaction_info(txid_or_groupid)
    print(f"Transaction {txid_or_groupid} confirmed in round {txinfo.get('confirmed-round')}")
    return txinfo

# =================================================================================
# 3. OPT-IN LOGIC
# =================================================================================

def opt_in_pi_base_to_usdc(creator_mnemonic, pi_base_app_id):
    print(f"Attempting to opt-in PI Base App ID {pi_base_app_id} to USDC (Asset ID: {USDC_ASSET_ID})...")

    creator_private_key, creator_address = get_account_details_from_mnemonic(creator_mnemonic)
    print(f"Creator address: {creator_address}")

    pi_base_app_address = get_application_address(pi_base_app_id)
    print(f"PI Base App address: {pi_base_app_address}")

    params = algod_client.suggested_params()
    params.flat_fee = True # Always use flat fee for predictability
    params.fee = 1000 # Set base fee, can adjust later if grouped

    # --- Step A: Check PI Base App's current ALGO balance ---
    try:
        pi_base_info = algod_client.account_info(pi_base_app_address)
        print(pi_base_info)
        current_algo_balance = pi_base_info.get('amount', 0)
    except Exception as e:
        print(f"Error fetching PI Base App info. Is the App ID {pi_base_app_id} correct and deployed? {e}")
        sys.exit(1)

    print(f"Current PI Base App ALGO balance: {current_algo_balance / 1_000_000} ALGO")

    # Define the core app call transaction (will be used in both scenarios)
    app_call_txn = transaction.ApplicationCallTxn(
        sender=creator_address, # Creator signs this transaction
        sp=params, # Use params, which now has flat_fee set
        index=pi_base_app_id,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"app_optin_usdc"],
        foreign_assets=[USDC_ASSET_ID] # Indicate ASA in foreign assets
    )
    
    # Calculate amount needed for minimum balance + 1.5x fee for the group of 2 transactions
    # This ensures it's more than just the min balance.
    # Each transaction needs a min fee, so a group of 2 needs 2*min_fee budget.
    amount_to_fund_calc = OPTIN_MIN_BALANCE_AMOUNT + 100_000 + (2 * 1000) - current_algo_balance
    
    # Only fund if a positive amount is needed
    if amount_to_fund_calc > 0:
        amount_to_fund = amount_to_fund_calc
        print(f"  Insufficient ALGO balance for opt-in. Funding with {amount_to_fund / 1_000_000} ALGO.")
        
        # Funding transaction
        funding_txn = transaction.PaymentTxn(
            sender=creator_address,
            sp=params, # Use params, which now has flat_fee set
            receiver=pi_base_app_address,
            amt=amount_to_fund
        )
        
        # --- Atomic Group Transaction Path ---
        # 1. Create a list of the UNSIGNED transactions that will be in the group
        txns_to_group = [funding_txn, app_call_txn]
        
        # 2. Calculate the group ID. This modifies the 'group_id' field on
        #    each transaction object *in the txns_to_group list* in-place.
        gid = transaction.calculate_group_id(txns_to_group)
        print(f"DEBUG (Before Sign): funding_txn.group_id is {funding_txn.group}")
        print(f"DEBUG (Before Sign): app_call_txn.group_id is {app_call_txn.group}")
        
        # For paranoia, explicitly set group_id again on the originals
        # This shouldn't be strictly necessary but aims to defeat any subtle issues.
        funding_txn.group = (gid)
        app_call_txn.group = gid
        
        print(f"  Sending funding and opt-in app call as an atomic group (Group ID: {gid.hex()})...")
        
        # 3. Sign the transactions. The signing process internally uses the group_id
        #    already set on each transaction object.
        signed_txns = []
        signed_txns.append(funding_txn.sign(creator_private_key))
        signed_txns.append(app_call_txn.sign(creator_private_key))
        
        # For final debug, verify group_id on the signed transaction objects themselves
        # print(f"DEBUG: Signed Funding Txn Group ID: {signed_txns[0].transaction.group_id.hex()}")
        # print(f"DEBUG: Signed App Call Txn Group ID: {signed_txns[1].transaction.group_id.hex()}")
        
        algod_client.send_transactions(signed_txns)
        wait_for_confirmation(algod_client, gid)

    else:
        # --- Single Transaction Path ---
        print("  Sufficient ALGO balance. Sending opt-in app call...")
        # No funding needed, just send the app call by itself
        # No group_id needed here, as it's a single transaction.
        signed_app_call_txn = app_call_txn.sign(creator_private_key)
        algod_client.send_transactions([signed_app_call_txn])
        wait_for_confirmation(algod_client, app_call_txn.get_txid())

    print("\nPI Base App successfully opted into USDC!")
    
    # Verify USDC balance (should be 0, but app is now opted in)
    pi_base_asset_holdings = algod_client.account_info(pi_base_app_address).get('assets', [])
    usdc_opted_in = False
    for asset in pi_base_asset_holdings:
        if asset['asset-id'] == USDC_ASSET_ID:
            print(f"Verified: PI Base App holds {asset['amount']} tUSDC.")
            usdc_opted_in = True
            break
    if not usdc_opted_in:
        print("Warning: USDC not found in PI Base App's asset holdings after opt-in attempt. Please check manually or if error occurred.")

# =================================================================================
# 4. SCRIPT EXECUTION (Main Block)
# =================================================================================

if __name__ == "__main__":
    # Get mnemonic from environment variable
    # creator_mnemonic = os.environ.get("MNEMONIC")
    # if not creator_mnemonic:
    #     print("Error: MNEMONIC environment variable not set. Please set your 24-word Pera Wallet seed phrase.")
    #     sys.exit(1)

    # Get PI Base App ID from command line argument or manual input
    pi_base_app_id_str = None
    if len(sys.argv) > 1:
        pi_base_app_id_str = sys.argv[1]
    
    if not pi_base_app_id_str:
        pi_base_app_id_str = input("Enter PI Base App ID: ").strip()

    try:
        pi_base_app_id = int(pi_base_app_id_str)
        if pi_base_app_id <= 0:
            raise ValueError
    except ValueError:
        print(f"Invalid PI Base App ID: {pi_base_app_id_str}. Must be a positive integer.")
        sys.exit(1)

    # Execute the opt-in
    opt_in_pi_base_to_usdc("", pi_base_app_id)