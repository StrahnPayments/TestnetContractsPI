# State Management Issues

## Critical State Issues

### 1. **PI Base - State Initialization Race Condition**
**File**: `contracts/strahn_pi_base.py`
**Line**: 175-180
**Issue**: Contract creation and method calls use same entry point

```python
# PROBLEMATIC STRUCTURE:
return Cond(
    [Txn.application_id() == Int(0), on_create],
    [Txn.on_completion() == OnComplete.NoOp, program],
    # ...
)
```

**Problem**: If `application_id() == 0` check fails, could execute methods on uninitialized state.

**Fix**: Add explicit state initialization checks in methods.

### 2. **Mandate Record - Missing State Validation**
**File**: `contracts/mandate_record.py`
**Line**: 78-85
**Issue**: No validation of creation arguments

```python
# MISSING VALIDATION:
App.globalPut(Bytes("dest_addr"), Txn.application_args[0])
App.globalPut(Bytes("amount"), Btoi(Txn.application_args[1]))
```

**Problem**: Invalid arguments could corrupt contract state.

**Fix**: Add validation for all creation arguments.

### 3. **Core Contract - Box Storage Corruption Risk**
**File**: `contracts/strahn_core.py`
**Line**: 15-18
**Issue**: No atomic updates for bytecode pairs

```python
# NON-ATOMIC UPDATES:
App.box_put(Bytes("approval"), approval_code)
App.box_put(Bytes("clear"), clear_code)
```

**Problem**: If first update succeeds but second fails, bytecode becomes inconsistent.

**Fix**: Use versioned storage or validation checks.

## Medium State Issues

### 4. **PI Base - Missing State Cleanup**
**File**: `contracts/strahn_pi_base.py`
**Issue**: No cleanup mechanism for failed operations

**Problem**: Failed operations could leave contract in inconsistent state.

**Fix**: Add rollback mechanisms or state validation.

### 5. **Mandate Record - Immutable State Assumptions**
**File**: `contracts/mandate_record.py`
**Issue**: Contract assumes state never needs updates

**Problem**: No mechanism to handle edge cases or corrections.

**Recommendation**: Consider adding emergency pause/update mechanisms.