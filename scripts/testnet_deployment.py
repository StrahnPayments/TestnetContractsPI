import os
import json, base64
from algosdk.v2client import algod
from algosdk import account, mnemonic, transaction, encoding
from algosdk.logic import get_application_address

# =================================================================================
# 1. CONFIGURE YOUR ENVIRONMENT
# =================================================================================

# Use environment variables for your mnemonic to keep it secure
# In your terminal (before running the script):
# For Windows: set MNEMONIC="your 25 word phrase here"
# For MacOS/Linux: export MNEMONIC="your 25 word phrase here"

# Load mnemonic from environment variable
sender_mnemonic = os.environ.get("MNEMONIC")
if not sender_mnemonic:
    # raise ValueError("MNEMONIC environment variable not set. Please set your 25-word seed phrase.")
    sender_mnemonic = "general high slush peanut yellow exclude range giant sheriff reflect phone mistake crack athlete column mandate great square seminar cool dream ripple cherry able month"

    print("Fallback used!")

# Get account details from mnemonic
sender_private_key = mnemonic.to_private_key(sender_mnemonic)
sender_address = account.address_from_private_key(sender_private_key)

# Algod client configuration
algod_address = "https://testnet-api.algonode.cloud"
algod_token = ""  # No token needed for AlgoNode public nodes
algod_client = algod.AlgodClient(algod_token, algod_address)

# Official TestNet USDC Asset ID
USDC_ASSET_ID = 10458941

print(f"Using sender address: {sender_address}")
print(f"Using official TestNet USDC ID: {USDC_ASSET_ID}")
# exit()
# =================================================================================
# 2. HELPER FUNCTIONS (same as before)
# =================================================================================

def wait_for_confirmation(client, txid):
    """Waits for a transaction to be confirmed."""
    last_round = client.status().get('last-round')
    txinfo = client.pending_transaction_info(txid)
    while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
        print("Waiting for confirmation...")
        last_round += 1
        client.status_after_block(last_round)
        txinfo = client.pending_transaction_info(txid)
    print(f"Transaction {txid} confirmed in round {txinfo.get('confirmed-round')}")
    return txinfo

def compile_program(client, source_code):
    """Compiles TEAL source code."""
    compile_response = client.compile(source_code)
    return compile_response['result']

def read_teal_file(file_path):
    """Reads a TEAL file content."""
    with open(file_path, 'r') as f:
        return f.read()

def create_app(client, private_key, approval_program, clear_program, global_schema, local_schema, app_args=None):
    """Creates a new application."""
    sender = account.address_from_private_key(private_key)
    params = client.suggested_params()
    
    txn = transaction.ApplicationCreateTxn(
        sender,
        params,
        transaction.OnComplete.NoOpOC,
        approval_program,
        clear_program,
        global_schema,
        local_schema,
        app_args
    )
    
    signed_txn = txn.sign(private_key)
    tx_id = signed_txn.transaction.get_txid()
    client.send_transactions([signed_txn])
    
    tx_info = wait_for_confirmation(client, tx_id)
    app_id = tx_info['application-index']
    print(f"Created new application with App ID: {app_id}")
    return app_id

# =================================================================================
# 3. DEPLOYMENT LOGIC
# =================================================================================

def main():
    print("\n--- Starting Deployment to TestNet ---")

    # --- Step 1: Compile and Deploy `strahn_core_app` ---
    print("\nStep 1: Deploying Strahn Core App...")
    core_approval_teal = read_teal_file("../build/strahn_core_approval.teal")
    core_clear_teal = read_teal_file("../build/strahn_core_clear.teal")
    
    # THE FIX IS HERE: Use base64.b64decode instead of bytes.fromhex
    core_approval_code = base64.b64decode(compile_program(algod_client, core_approval_teal))
    core_clear_code = base64.b64decode(compile_program(algod_client, core_clear_teal))
    
    core_app_id = create_app(
        client=algod_client,
        private_key=sender_private_key,
        approval_program=core_approval_code,
        clear_program=core_clear_code,
        global_schema=transaction.StateSchema(num_uints=2, num_byte_slices=1),
        local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        app_args=[encoding.decode_address(sender_address)]
    )

    # --- Step 2: Compile and Deploy `strahn_pi_base` ---
    print("\nStep 2: Deploying Strahn PI Base App...")
    pi_base_approval_teal = read_teal_file("../build/strahn_pi_base_approval.teal")
    pi_base_clear_teal = read_teal_file("../build/strahn_pi_base_clear.teal")

    # THE FIX IS HERE: Use base64.b64decode instead of bytes.fromhex
    pi_base_approval_code = base64.b64decode(compile_program(algod_client, pi_base_approval_teal))
    pi_base_clear_code = base64.b64decode(compile_program(algod_client, pi_base_clear_teal))

    # Creation args: creator_addr, usdc_id, strahn_core_app_id
    pi_base_app_args = [
        encoding.decode_address(sender_address),
        USDC_ASSET_ID.to_bytes(8, 'big'),
        core_app_id.to_bytes(8, 'big')
    ]

    pi_base_app_id = create_app(
        client=algod_client,
        private_key=sender_private_key,
        approval_program=pi_base_approval_code,
        clear_program=pi_base_clear_code,
        global_schema=transaction.StateSchema(num_uints=3, num_byte_slices=1),
        local_schema=transaction.StateSchema(num_uints=0, num_byte_slices=0),
        app_args=pi_base_app_args
    )
    
    # --- Step 3: Configure `strahn_core_app` with Mandate Bytecode ---
    # This part was already correct, as it was using .encode() on the raw TEAL
    # and not using the compile_program function.
    print("\nStep 3: Configuring Strahn Core App with Mandate bytecode...")
    mandate_approval_teal = read_teal_file("../build/mandate_record_approval.teal")
    mandate_clear_teal = read_teal_file("../build/mandate_record_clear.teal")
    
    mandate_approval_bytecode = mandate_approval_teal.encode()
    mandate_clear_bytecode = mandate_clear_teal.encode()

    # Constants for chunking
    NOTE_MAX_LEN = 1024 # Max bytes for a transaction note
    total_approval_size = len(mandate_approval_bytecode)
    total_clear_size = len(mandate_clear_bytecode)
    # We need to reference the app ID in the transaction
    # And pay for the boxes we are creating
    # Box reference format: (app_id, box_name_bytes)
    approval_box_ref = (core_app_id, b"approval")
    clear_box_ref = (core_app_id, b"clear")
    v1_approval_box_ref = (core_app_id, b"approval_v1") # For set_version
    v1_clear_box_ref = (core_app_id, b"clear_v1")       # For set_version
    
    # Calculate box storage fees: 2500 + 400 * (key_len + value_len)
    # This is a one-time fee paid by the deployer
    # We need fees for the main boxes AND the versioned copies
    min_bal_increase = (2500 + 400 * (len(b"approval") + len(mandate_approval_bytecode)))
    min_bal_increase += (2500 + 400 * (len(b"clear") + len(mandate_clear_bytecode)))
    min_bal_increase += (2500 + 400 * (len(b"approval_v1") + len(mandate_approval_bytecode)))
    min_bal_increase += (2500 + 400 * (len(b"clear_v1") + len(mandate_clear_bytecode)))


    # Fund the core app so it can pay for its boxes
    print(f"Funding core app with {min_bal_increase / 1_000_000} ALGO for box storage...")
    params = algod_client.suggested_params()
    funding_txn = transaction.PaymentTxn(
        sender=sender_address,
        sp=params,
        receiver=get_application_address(core_app_id),
        amt=min_bal_increase
    )
    signed_funding_txn = funding_txn.sign(sender_private_key)
    tx_id = algod_client.send_transaction(signed_funding_txn)
    wait_for_confirmation(algod_client, tx_id)

    # --- Helper to upload bytecode in chunks ---
    def upload_bytecode_in_chunks(box_name, bytecode, total_box_size):
        print(f"  Uploading {box_name} in chunks...")
        current_offset = 0 # Keep track of where we are in the box

        # Calculate the number of 1KB budget units needed for the entire box size
        # (Total size + 1023) // 1024 effectively rounds up to the nearest KB
        # Max budget for a single txn is 8KB (8 references)
        needed_budget_kb = (total_box_size + 1023) // 1024
        
        # Ensure at least 1KB budget if the box exists or is small
        needed_budget_kb = 8
        
        # Ensure we don't exceed the 8 box reference limit per transaction for now
        # If your bytecode is > 8KB, you'd need multiple transactions or atomic groups
        if needed_budget_kb > 8:
            raise ValueError(f"Bytecode size {total_box_size} bytes exceeds single transaction box reference limit (8KB). Consider splitting into multiple txns.")


        for i in range(0, len(bytecode), NOTE_MAX_LEN):
            chunk = bytecode[i:i + NOTE_MAX_LEN]
            params = algod_client.suggested_params()
            
            method_name = b"set_bytecode" if i == 0 else b"append_bytecode"
            
            app_args_list = [method_name, box_name]
            if i == 0:
                # Only pass the total_box_size for the initial 'set_bytecode' call
                app_args_list.append(total_box_size.to_bytes(8, 'big')) 
                
                # We don't need to increase the fee for write budget here,
                # as it's tied to box references.
                params.fee = 3000 # Ensure it's default
                params.flat_fee = True 
            
            # Construct the list of box references for the transaction
            box_ref_list = []
            # Always add the primary box reference
            box_ref_list.append((core_app_id, box_name))

            # Add dummy box references to increase the write budget
            # This is the key change to solve the "write budget exceeded" error.
            # We need `needed_budget_kb` total references.
            for k in range(needed_budget_kb - 1): # -1 because we already added the main box_name
                # Use unique dummy names for each reference to ensure they are counted distinctly
                dummy_box_name = box_name + b"_dummy_box_" + str(k).encode()
                box_ref_list.append((core_app_id, dummy_box_name))

            upload_txn = transaction.ApplicationCallTxn(
                sender=sender_address,
                sp=params,
                index=core_app_id,
                on_complete=transaction.OnComplete.NoOpOC,
                app_args=app_args_list,
                note=chunk,
                boxes=box_ref_list # Pass the list of box references
            )
            
            signed_upload_txn = upload_txn.sign(sender_private_key)
            tx_id = algod_client.send_transaction(signed_upload_txn)
            wait_for_confirmation(algod_client, tx_id)
            print(f"    Chunk {i // NOTE_MAX_LEN + 1} uploaded for {box_name}.")
            current_offset += len(chunk) # Update offset for next chunk if needed
    # --- Upload Approval Program ---
    upload_bytecode_in_chunks(b"approval", mandate_approval_bytecode, total_approval_size)
    
    # --- Upload Clear Program ---
    upload_bytecode_in_chunks(b"clear", mandate_clear_bytecode, total_clear_size)

    # --- Finalize by setting the version ---
    print("Finalizing bytecode by setting version to 1...")
    params = algod_client.suggested_params()
    # This call still creates versioned boxes, so it's good to have a slightly higher fee.
    params.fee = 6000
    params.flat_fee = True

    box_ref_list = [approval_box_ref, clear_box_ref, v1_approval_box_ref, v1_clear_box_ref]

    for k in range(4): # -1 because we already added the main box_name
        # Use unique dummy names for each reference to ensure they are counted distinctly
        dummy_box_name = b"_dummy_box_" + str(k).encode()
        box_ref_list.append((core_app_id, dummy_box_name))

    set_version_txn = transaction.ApplicationCallTxn(
        sender=sender_address,
        sp=params,
        index=core_app_id,
        on_complete=transaction.OnComplete.NoOpOC,
        app_args=[b"set_version", (1).to_bytes(8, 'big')],
        boxes=box_ref_list
    )
    signed_set_version_txn = set_version_txn.sign(sender_private_key)
    tx_id = algod_client.send_transaction(signed_set_version_txn)
    wait_for_confirmation(algod_client, tx_id)

    print("Strahn Core App has been configured with mandate bytecode using boxes.")

    print("\n--- Deployment Complete! ---")
    print(f"Official TestNet USDC ID: {USDC_ASSET_ID}")
    print(f"Strahn Core App ID: {core_app_id}")
    print(f"Strahn PI Base App ID: {pi_base_app_id}")
    
    deployment_info = {
        "usdc_id": USDC_ASSET_ID,
        "core_app_id": core_app_id,
        "pi_base_app_id": pi_base_app_id,
        "pi_base_address": get_application_address(pi_base_app_id),
        "deployer_address": sender_address
    }
    with open("deployment_info.json", "w") as f:
        json.dump(deployment_info, f, indent=4)
    print("\nDeployment info saved to deployment_info.json")

if __name__ == "__main__":
    main()