# Strahn PI Base Usage Documentation

## Overview

The **Strahn PI Base** contract is the core user wallet and payment processor in the Strahn PI System. It serves as a non-custodial smart contract wallet that holds USDC and processes both single-shot and recurring payments on behalf of the user.

## Table of Contents

1. [Contract Deployment](#contract-deployment)
2. [Initial Setup](#initial-setup)
3. [Single-Shot Payments](#single-shot-payments)
4. [Recurring Payments (Mandates)](#recurring-payments-mandates)
5. [Security Model](#security-model)
6. [Error Handling](#error-handling)
7. [Integration Examples](#integration-examples)

## Contract Deployment

### Prerequisites

- Algorand account with sufficient ALGO for deployment
- USDC Asset ID (31566704 for mainnet)
- Deployed Strahn Core contract App ID

### Deployment Parameters

```python
# Creation arguments for PI Base contract
creation_args = [
    creator_addr,        # User's authorized address (bytes)
    usdc_asset_id,       # USDC Asset ID (uint64)
    strahn_core_app_id   # Strahn Core contract App ID (uint64)
]

# State schema requirements
global_schema = {
    "num_uints": 3,      # usdc_id, strahn_core_app_id, creator_nonce
    "num_byte_slices": 1  # creator_addr
}

local_schema = {
    "num_uints": 0,
    "num_byte_slices": 0
}
```

### Example Deployment

```python
from algosdk.transaction import ApplicationCreateTxn
from algosdk.encoding import decode_address

# Load compiled bytecode
with open("build/strahn_pi_base_approval.teal", "r") as f:
    approval_program = algod_client.compile(f.read())["result"]

with open("build/strahn_pi_base_clear.teal", "r") as f:
    clear_program = algod_client.compile(f.read())["result"]

# Create deployment transaction
txn = ApplicationCreateTxn(
    sender=user_address,
    sp=algod_client.suggested_params(),
    on_complete=0,  # NoOp
    approval_program=base64.b64decode(approval_program),
    clear_program=base64.b64decode(clear_program),
    global_schema=StateSchema(3, 1),
    local_schema=StateSchema(0, 0),
    app_args=[
        decode_address(user_address),
        usdc_asset_id,
        strahn_core_app_id
    ]
)
```

## Initial Setup

### 1. USDC Opt-In

After deployment, the contract must opt into the USDC asset before it can receive deposits.

```python
# Method: app_optin_usdc()
# Authorization: Must be called by Global.creator_address()

app_call_txn = ApplicationCallTxn(
    sender=creator_address,  # Must be the original deployer
    sp=algod_client.suggested_params(),
    index=pi_base_app_id,
    on_complete=0,
    app_args=["app_optin_usdc"]
)
```

**Important**: This method can only be called by the account that originally deployed the contract (`Global.creator_address()`), not the `creator_addr` stored in state.

### 2. Fund the Contract

Deposit USDC into the contract using a grouped transaction:

```python
# Step 1: USDC transfer to contract
usdc_transfer = AssetTransferTxn(
    sender=user_address,
    sp=algod_client.suggested_params(),
    receiver=get_application_address(pi_base_app_id),
    amt=1000000,  # 1 USDC (6 decimals)
    index=usdc_asset_id
)

# Step 2: Contract call to acknowledge deposit
deposit_call = ApplicationCallTxn(
    sender=user_address,
    sp=algod_client.suggested_params(),
    index=pi_base_app_id,
    on_complete=0,
    app_args=["deposit_usdc"]
)

# Group and submit
group_txns = [usdc_transfer, deposit_call]
assign_group_id(group_txns)
```

## Single-Shot Payments

Single-shot payments are authorized by the user's cryptographic signature and processed immediately.

### Payment Flow

1. **Off-chain**: User signs payment intent
2. **On-chain**: Relayer submits signed intent to contract
3. **Execution**: Contract verifies signature and processes payment

### Signature Generation

```python
import hashlib
from algosdk.encoding import encode_address
from algosdk.util import sign_bytes

def create_payment_signature(private_key, nonce, destination, amount, relayer_fee):
    """Create signature for single-shot payment"""
    
    # Construct message matching contract logic
    message_parts = [
        b"SPP_V1:",
        nonce.to_bytes(8, 'big'),
        decode_address(destination),
        amount.to_bytes(8, 'big'),
        relayer_fee.to_bytes(8, 'big')
    ]
    
    message = b"".join(message_parts)
    message_hash = hashlib.sha256(message).digest()
    
    # Sign the hash
    signature = sign_bytes(message_hash, private_key)
    return signature
```

### Processing Payment

```python
def process_single_payment(pi_base_app_id, destination, amount, relayer_fee, nonce, signature):
    """Submit single-shot payment to contract"""
    
    app_call_txn = ApplicationCallTxn(
        sender=relayer_address,
        sp=algod_client.suggested_params(),
        index=pi_base_app_id,
        on_complete=0,
        app_args=[
            "process_intent",
            decode_address(destination),
            amount,
            relayer_fee,
            nonce,
            signature
        ],
        assets=[usdc_asset_id]  # Required for inner transactions
    )
    
    return app_call_txn
```

### Nonce Management

The contract maintains a sequential nonce (`creator_nonce`) to prevent replay attacks:

- **Initial value**: 0
- **Increment**: +1 after each successful payment
- **Verification**: Payment nonce must exactly match current contract nonce

```python
# Query current nonce
app_info = algod_client.application_info(pi_base_app_id)
current_nonce = None

for global_state in app_info["params"]["global-state"]:
    key = base64.b64decode(global_state["key"]).decode()
    if key == "creator_nonce":
        current_nonce = global_state["value"]["uint"]
        break
```

## Recurring Payments (Mandates)

Mandates enable automated recurring payments without requiring user signatures for each transaction.

### Mandate Setup Flow

1. **Off-chain**: User signs mandate terms
2. **On-chain**: Relayer calls `setup_mandate_standard`
3. **Deployment**: Contract deploys new Mandate Record via Strahn Core
4. **Initial Payment**: First payment executed immediately

### Mandate Signature Generation

```python
def create_mandate_signature(private_key, dest_addr, amount, interval_sec, start_ts, relayer_fee):
    """Create signature for mandate setup"""
    
    message_parts = [
        b"MANDATE_V1:",
        decode_address(dest_addr),
        amount.to_bytes(8, 'big'),
        interval_sec.to_bytes(8, 'big'),
        start_ts.to_bytes(8, 'big'),
        relayer_fee.to_bytes(8, 'big')
    ]
    
    message = b"".join(message_parts)
    message_hash = hashlib.sha256(message).digest()
    
    return sign_bytes(message_hash, private_key)
```

### Standard Mandate Setup

```python
def setup_standard_mandate(pi_base_app_id, dest_addr, amount, interval_sec, start_ts, 
                          relayer_fee, expected_approval_hash, expected_clear_hash, signature):
    """Setup a standard mandate with bytecode verification"""
    
    app_call_txn = ApplicationCallTxn(
        sender=relayer_address,
        sp=algod_client.suggested_params(),
        index=pi_base_app_id,
        on_complete=0,
        app_args=[
            "setup_mandate_standard",
            decode_address(dest_addr),
            amount,
            interval_sec,
            start_ts,
            relayer_fee,
            expected_approval_hash,
            expected_clear_hash,
            signature
        ],
        assets=[usdc_asset_id],
        applications=[strahn_core_app_id]
    )
    
    return app_call_txn
```

### Bytecode Hash Verification

For standard mandates, users must provide expected bytecode hashes to ensure they consent to the specific mandate contract code:

```python
def get_current_bytecode_hashes(strahn_core_app_id):
    """Query current official mandate bytecode hashes"""
    
    app_call_txn = ApplicationCallTxn(
        sender=query_address,
        sp=algod_client.suggested_params(),
        index=strahn_core_app_id,
        on_complete=0,
        app_args=["get_current_bytecode_hashes"]
    )
    
    # Submit and parse logs for hash values
    result = algod_client.send_transaction(app_call_txn.sign(private_key))
    # Parse logs: "approval_hash:<hash>:clear_hash:<hash>"
```

## Security Model

### Authorization Mechanisms

1. **Signature Verification**: All critical operations require valid Ed25519 signatures from `creator_addr`
2. **Nonce Protection**: Sequential nonces prevent replay attacks for single payments
3. **Caller Verification**: `release_mandate_funds` can only be called by authorized mandate contracts
4. **Bytecode Integrity**: Standard mandates verify official bytecode hashes

### Key Security Considerations

- **Private Key Security**: The `creator_addr` private key must be kept secure as it authorizes all payments
- **Nonce Synchronization**: Off-chain systems must track nonce state accurately
- **Signature Validation**: Always verify signatures match expected message format
- **Mandate Authorization**: Only deploy mandates with verified bytecode hashes

### Access Control Matrix

| Method | Authorization | Notes |
|--------|---------------|-------|
| `app_optin_usdc` | `Global.creator_address()` | One-time setup only |
| `deposit_usdc` | Permissionless | Requires grouped USDC transfer |
| `process_intent` | Valid signature from `creator_addr` | Nonce-protected |
| `setup_mandate_standard` | Valid signature from `creator_addr` | Bytecode verification |
| `release_mandate_funds` | Authorized mandate contracts only | Critical security check |

## Error Handling

### Common Error Scenarios

1. **Invalid Signature**: `Ed25519Verify` fails
   - **Cause**: Incorrect signature or message construction
   - **Resolution**: Verify signature generation logic

2. **Nonce Mismatch**: Current nonce ≠ provided nonce
   - **Cause**: Out-of-sync nonce tracking
   - **Resolution**: Query current nonce from contract state

3. **Insufficient Funds**: Contract lacks USDC for payment
   - **Cause**: Inadequate contract balance
   - **Resolution**: Deposit more USDC before retry

4. **Unauthorized Mandate Call**: `release_mandate_funds` called by non-mandate
   - **Cause**: Invalid caller or compromised contract
   - **Resolution**: Verify mandate contract legitimacy

### Error Logging

The contract logs successful operations for monitoring:

```python
# Successful operations generate logs:
# - "usdc_optin_complete"
# - "usdc_deposited:<amount>"
# - "payment_processed:<amount>"
# - "mandate_setup_complete"
# - "mandate_payment_released:<amount>"
```

## Integration Examples

### Complete Single Payment Example

```python
async def execute_single_payment():
    """Complete example of single-shot payment"""
    
    # 1. Query current nonce
    app_info = algod_client.application_info(pi_base_app_id)
    current_nonce = get_global_state_value(app_info, "creator_nonce")
    
    # 2. Generate signature
    signature = create_payment_signature(
        user_private_key,
        current_nonce,
        merchant_address,
        1000000,  # 1 USDC
        10000     # 0.01 USDC relayer fee
    )
    
    # 3. Submit payment
    txn = process_single_payment(
        pi_base_app_id,
        merchant_address,
        1000000,
        10000,
        current_nonce,
        signature
    )
    
    # 4. Sign and submit
    signed_txn = txn.sign(relayer_private_key)
    tx_id = algod_client.send_transaction(signed_txn)
    
    # 5. Wait for confirmation
    result = wait_for_confirmation(algod_client, tx_id)
    return result
```

### Complete Mandate Setup Example

```python
async def setup_recurring_subscription():
    """Complete example of mandate setup"""
    
    # 1. Get current official bytecode hashes
    approval_hash, clear_hash = get_current_bytecode_hashes(strahn_core_app_id)
    
    # 2. Define mandate parameters
    dest_addr = merchant_address
    amount = 5000000  # 5 USDC monthly
    interval_sec = 2592000  # 30 days
    start_ts = int(time.time()) + 86400  # Start tomorrow
    relayer_fee = 50000  # 0.05 USDC
    
    # 3. Generate mandate signature
    signature = create_mandate_signature(
        user_private_key,
        dest_addr,
        amount,
        interval_sec,
        start_ts,
        relayer_fee
    )
    
    # 4. Setup mandate
    txn = setup_standard_mandate(
        pi_base_app_id,
        dest_addr,
        amount,
        interval_sec,
        start_ts,
        relayer_fee,
        approval_hash,
        clear_hash,
        signature
    )
    
    # 5. Submit transaction
    signed_txn = txn.sign(relayer_private_key)
    tx_id = algod_client.send_transaction(signed_txn)
    
    # 6. Extract mandate contract ID from logs
    result = wait_for_confirmation(algod_client, tx_id)
    mandate_app_id = extract_created_app_id_from_logs(result)
    
    return mandate_app_id
```

### Balance Monitoring

```python
def get_contract_usdc_balance(pi_base_app_id):
    """Get current USDC balance of PI Base contract"""
    
    contract_address = get_application_address(pi_base_app_id)
    account_info = algod_client.account_info(contract_address)
    
    for asset in account_info.get("assets", []):
        if asset["asset-id"] == usdc_asset_id:
            return asset["amount"]
    
    return 0  # Not opted in or zero balance
```

## Best Practices

1. **Nonce Management**: Always query current nonce before creating payment signatures
2. **Error Handling**: Implement robust retry logic for failed transactions
3. **Balance Monitoring**: Monitor contract USDC balance to ensure sufficient funds
4. **Signature Security**: Never expose private keys; use secure signing environments
5. **Bytecode Verification**: Always verify mandate bytecode hashes for standard deployments
6. **Transaction Grouping**: Properly group transactions for deposit operations
7. **Fee Estimation**: Account for relayer fees in payment calculations

## Troubleshooting

### Common Issues

1. **"Transaction rejected"**: Check signature validity and nonce synchronization
2. **"Insufficient funds"**: Verify contract USDC balance
3. **"Asset not opted in"**: Ensure `app_optin_usdc` was called successfully
4. **"Invalid group"**: Verify transaction grouping for deposits
5. **"Unauthorized"**: Check caller permissions for restricted methods

### Debug Tools

- Use Algorand's transaction simulation for testing
- Monitor contract logs for operation success/failure
- Query global state to verify contract configuration
- Test with small amounts before production deployment