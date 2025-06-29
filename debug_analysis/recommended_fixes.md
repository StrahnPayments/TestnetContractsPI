# Recommended Fixes Priority List

## Immediate Critical Fixes (Security)

### 1. **Fix Mandate Authorization Vulnerability**
```python
# In strahn_pi_base.py - release_mandate_funds()
# REPLACE:
caller_creator = AppParam.creator(Txn.sender())
Assert(caller_creator.value() == Global.current_application_address())

# WITH:
# Maintain whitelist of authorized mandates
mandate_exists = App.box_get(Concat(Bytes("mandate_"), Itob(Txn.sender())))
Assert(mandate_exists.hasValue())
```

### 2. **Fix Signature Replay Vulnerability**
```python
# In strahn_pi_base.py - process_intent()
# ADD contract address to message:
message = Concat(
    Bytes("SPP_V1:"),
    Itob(Global.current_application_id()),  # ADD THIS
    Itob(nonce),
    destination,
    Itob(amount),
    Itob(relayer_fee)
)
```

### 3. **Fix Schema Mismatch**
```python
# In strahn_core.py - deploy_internal()
# CHANGE:
TxnField.global_num_uints: Int(5)
# TO:
TxnField.global_num_uints: Int(6)
```

## High Priority Fixes (Logic)

### 4. **Fix Nonce Increment Timing**
```python
# In strahn_pi_base.py - process_intent()
# MOVE nonce increment AFTER successful payment
# Current order is incorrect
```

### 5. **Add Balance Validation**
```python
# In strahn_pi_base.py - before payments
# ADD:
contract_balance = AssetHolding.balance(
    Global.current_application_address(),
    App.globalGet(Bytes("usdc_id"))
)
Assert(contract_balance.hasValue())
Assert(contract_balance.value() >= amount + relayer_fee)
```

### 6. **Fix Creator Address Check**
```python
# In strahn_pi_base.py - app_optin_usdc()
# CHANGE:
Assert(Txn.sender() == Global.creator_address())
# TO:
Assert(Txn.sender() == App.globalGet(Bytes("creator_addr")))
```

## Medium Priority Fixes (Robustness)

### 7. **Add Input Validation**
```python
# In mandate_record.py - on_create
# ADD validation for all creation arguments:
Assert(Len(Txn.application_args[0]) == Int(32))  # Valid address
Assert(Btoi(Txn.application_args[1]) > Int(0))   # Positive amount
Assert(Btoi(Txn.application_args[2]) >= Int(3600))  # Minimum 1 hour interval
```

### 8. **Add Overflow Protection**
```python
# In mandate_record.py - process_payment()
# ADD overflow check:
new_timestamp = next_payment_time + App.globalGet(Bytes("interval_sec"))
Assert(new_timestamp > next_payment_time)  # Overflow check
```

### 9. **Improve Error Handling**
```python
# Add specific error codes and logging throughout all contracts
# Use the error handling utilities from common.py more extensively
```

## Low Priority Optimizations

### 10. **Cache Global State Reads**
### 11. **Optimize String Operations**
### 12. **Improve Conditional Logic**

## Testing Recommendations

### 13. **Add Comprehensive Test Suite**
- Edge case testing
- Security testing
- Integration testing
- Stress testing

### 14. **Add Deployment Verification**
- Post-deployment contract validation
- Network environment checks
- Configuration verification