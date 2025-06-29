# Logic Bugs Analysis

## Critical Logic Issues

### 1. **Mandate Record - Global State Schema Mismatch**
**File**: `contracts/strahn_core.py`
**Line**: 47-48
**Issue**: Schema definition doesn't match actual usage

```python
# INCORRECT SCHEMA:
TxnField.global_num_uints: Int(5),  # amount, interval_sec, next_pay_ts, relayer_fee, usdc_asa_id, pi_base_id
TxnField.global_num_byte_slices: Int(1),  # dest_addr
```

**Problem**: Comments indicate 6 uints but schema specifies 5.

**Actual State Variables**:
- `amount` (uint)
- `interval_sec` (uint) 
- `next_pay_ts` (uint)
- `relayer_fee` (uint)
- `usdc_asa_id` (uint)
- `pi_base_id` (uint)
- `dest_addr` (bytes)

**Fix**: Change to `Int(6)` for global_num_uints.

### 2. **PI Base - Incorrect Sender Check in app_optin_usdc**
**File**: `contracts/strahn_pi_base.py`
**Line**: 12
**Issue**: Uses `Global.creator_address()` instead of stored creator

```python
# INCONSISTENT CHECK:
Assert(Txn.sender() == Global.creator_address())
```

**Problem**: This checks against the account that deployed the contract, not the user who owns it.

**Fix**: Use `App.globalGet(Bytes("creator_addr"))` for consistency.

### 3. **Mandate Record - Asset Opt-in Timing Issue**
**File**: `contracts/mandate_record.py`
**Line**: 65-72
**Issue**: Asset opt-in during creation might fail if asset doesn't exist

```python
# POTENTIAL FAILURE:
InnerTxnBuilder.SetFields({
    TxnField.type_enum: TxnType.AssetTransfer,
    TxnField.xfer_asset: Btoi(Txn.application_args[5]),  # usdc_asa_id
    TxnField.asset_receiver: Global.current_application_address(),
    TxnField.asset_amount: Int(0),
})
```

**Problem**: No validation that asset ID is valid before opt-in.

**Fix**: Add asset existence validation.

## Medium Logic Issues

### 4. **PI Base - Nonce Increment Timing**
**File**: `contracts/strahn_pi_base.py`
**Line**: 54
**Issue**: Nonce incremented before payment execution

```python
# RISKY ORDER:
App.globalPut(Bytes("creator_nonce"), current_nonce + Int(1))
# ... then payment execution
```

**Problem**: If payment fails, nonce is still incremented, causing desync.

**Fix**: Increment nonce after successful payment execution.

### 5. **Core Contract - Missing Application ID Validation**
**File**: `contracts/strahn_core.py`
**Line**: 35
**Issue**: No validation of calling application

```python
# MISSING VALIDATION:
pi_base_id = Txn.sender()  # Assumes sender is valid app
```

**Problem**: Any application can call deploy functions.

**Fix**: Add validation that sender is a legitimate PI Base contract.

### 6. **Mandate Record - Integer Overflow Risk**
**File**: `contracts/mandate_record.py`
**Line**: 25
**Issue**: Timestamp addition could overflow

```python
# POTENTIAL OVERFLOW:
next_payment_time + App.globalGet(Bytes("interval_sec"))
```

**Problem**: Large intervals could cause timestamp overflow.

**Fix**: Add overflow checks or reasonable interval limits.