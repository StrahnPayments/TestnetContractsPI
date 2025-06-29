# Deployment Issues

## Critical Deployment Issues

### 1. **Missing Environment Validation**
**File**: `scripts/deploy_contracts.py`
**Issue**: No validation of deployment environment

```python
# MISSING VALIDATION:
algod_address = os.getenv("ALGOD_ADDRESS", "https://testnet-api.algonode.cloud")
```

**Problem**: Could deploy to wrong network accidentally.

**Fix**: Add explicit network validation.

### 2. **Insufficient Error Handling**
**File**: `scripts/deploy_contracts.py`
**Issue**: Generic error handling for deployment failures

**Problem**: Difficult to diagnose deployment issues.

**Fix**: Add specific error handling for different failure modes.

### 3. **Missing Deployment Verification**
**File**: `scripts/deploy_contracts.py`
**Issue**: No post-deployment verification

**Problem**: Deployed contracts might not function correctly.

**Fix**: Add deployment verification steps.

## Medium Deployment Issues

### 4. **Hardcoded Constants**
**Files**: Multiple
**Issue**: USDC asset ID hardcoded for mainnet

**Problem**: Won't work on testnet without modification.

**Fix**: Make asset IDs configurable.

### 5. **Missing Dependency Checks**
**File**: `scripts/compile_contracts.py`
**Issue**: No validation of PyTEAL version compatibility

**Problem**: Could compile with incompatible versions.

**Fix**: Add version compatibility checks.