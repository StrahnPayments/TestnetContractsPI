# Gas Optimization Issues

## High Impact Optimizations

### 1. **Redundant Global State Reads**
**Files**: All contracts
**Issue**: Multiple reads of same global state values

```python
# INEFFICIENT:
App.globalGet(Bytes("usdc_id"))  # Called multiple times
```

**Fix**: Cache frequently accessed values in local variables.

### 2. **Unnecessary String Operations**
**File**: `contracts/strahn_pi_base.py`
**Issue**: Repeated string concatenations

```python
# INEFFICIENT:
Concat(Bytes("SPP_V1:"), Itob(nonce), destination, ...)
```

**Fix**: Pre-compute static parts of messages.

### 3. **Box Storage Access Patterns**
**File**: `contracts/strahn_core.py`
**Issue**: Multiple box reads for same data

**Fix**: Batch box operations where possible.

## Medium Impact Optimizations

### 4. **Subroutine Call Overhead**
**Files**: All contracts
**Issue**: Some subroutines called only once

**Fix**: Inline simple subroutines to reduce call overhead.

### 5. **Conditional Logic Optimization**
**Files**: All contracts
**Issue**: Complex conditional chains

**Fix**: Reorder conditions by likelihood for early exit.