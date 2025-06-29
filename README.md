# Strahn PI System - PyTEAL Implementation

A comprehensive, non-custodial payment system built on Algorand blockchain using PyTEAL. The system provides a Stripe-like developer experience for Web3 payments with support for both single-shot and recurring payments.

## Architecture Overview

The Strahn PI System consists of three interconnected smart contracts:

### 1. **Strahn Core** (Factory Contract)
- **Purpose**: Trusted factory for deploying mandate contracts
- **Features**: 
  - Stores official mandate contract bytecode
  - Deploys new mandate contracts with integrity verification
  - Supports legacy contract deployment
- **Security**: Owner-controlled bytecode updates

### 2. **Strahn PI Base** (User Wallet)
- **Purpose**: Personal smart contract wallet and payment processor
- **Features**:
  - Non-custodial USDC storage and management
  - Signature-based payment authorization
  - Single-shot and recurring payment processing
  - Direct merchant settlement
- **Security**: Ed25519 signature verification, nonce-based replay protection

### 3. **Mandate Record** (Recurring Payment)
- **Purpose**: Autonomous state machine for subscription payments
- **Features**:
  - Time-locked payment processing
  - Automatic payment scheduling
  - Immutable payment terms
- **Security**: Can only be called by authorized PI Base contracts

## Key Features

- **🔐 Non-Custodial**: Users maintain full control of their funds
- **💰 Direct Settlement**: Payments go directly from user to merchant
- **⛽ Gas Abstraction**: Relayer network handles transaction fees
- **🔄 Recurring Payments**: Automated subscription management
- **✅ Signature-Based Auth**: Cryptographic authorization for all payments
- **🛡️ Security First**: Multiple layers of on-chain security checks

## Project Structure

```
strahn-pi-system-pyteal/
├── contracts/
│   ├── __init__.py
│   ├── strahn_core.py          # Factory contract
│   ├── strahn_pi_base.py       # User wallet contract
│   ├── mandate_record.py       # Recurring payment contract
│   └── utils/
│       └── common.py           # Shared utilities
├── scripts/
│   ├── compile_contracts.py    # Contract compilation
│   └── deploy_contracts.py     # Deployment scripts
├── tests/
│   └── test_contracts.py       # Test suite
├── build/                      # Compiled TEAL output
├── requirements.txt
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.8+
- PyTEAL 0.25.0+
- Algorand Python SDK

### Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Compile Contracts**:
   ```bash
   python scripts/compile_contracts.py
   ```

3. **Run Tests**:
   ```bash
   python -m pytest tests/ -v
   ```

### Deployment

1. **Set Environment Variables**:
   ```bash
   export DEPLOYER_MNEMONIC="your 25-word mnemonic phrase"
   export ALGOD_ADDRESS="https://testnet-api.algonode.cloud"
   ```

2. **Deploy Contracts**:
   ```bash
   python scripts/deploy_contracts.py
   ```

## Contract Specifications

### Strahn Core Contract

**Global State**:
- `owner_addr`: Admin address for bytecode updates
- Box Storage: `"approval"` and `"clear"` bytecode

**Methods**:
- `update_bytecode(approval_code, clear_code)`: Update mandate bytecode
- `deploy_mandate(...)`: Deploy new mandate with verification
- `deploy_legacy_mandate(...)`: Deploy legacy mandate

### Strahn PI Base Contract

**Global State**:
- `creator_addr`: User's authorized address
- `usdc_id`: USDC asset ID
- `strahn_core_app_id`: Core contract reference
- `creator_nonce`: Replay protection counter

**Methods**:
- `app_optin_usdc()`: Opt into USDC asset
- `deposit_usdc()`: Handle USDC deposits
- `process_intent(...)`: Process single payments
- `setup_mandate_standard(...)`: Create recurring payments
- `release_mandate_funds(...)`: Release funds for mandates

### Mandate Record Contract

**Global State**:
- `dest_addr`: Merchant address
- `amount`: Payment amount
- `interval_sec`: Payment frequency
- `next_pay_ts`: Next payment timestamp
- `relayer_fee`: Relayer compensation
- `usdc_asa_id`: USDC asset reference
- `pi_base_id`: Associated PI Base contract

**Methods**:
- `process_payment()`: Execute recurring payment

## Security Considerations

1. **Signature Verification**: All payments require valid Ed25519 signatures
2. **Nonce Protection**: Sequential nonces prevent replay attacks
3. **Authorization Checks**: Critical functions verify caller permissions
4. **Bytecode Integrity**: Mandate deployment verifies code hashes
5. **Time Locks**: Recurring payments respect timing constraints

## Payment Flow

### Single-Shot Payment
1. User signs payment intent off-chain
2. Relayer submits transaction to PI Base contract
3. Contract verifies signature and nonce
4. Funds transferred directly to merchant
5. Relayer receives fee compensation

### Recurring Payment Setup
1. User signs mandate terms off-chain
2. Relayer calls `setup_mandate_standard`
3. PI Base verifies signature and deploys Mandate Record
4. Initial payment executed immediately
5. Future payments processed by Mandate Record

### Recurring Payment Processing
1. Anyone can call `process_payment` on Mandate Record
2. Contract checks if payment is due (time-locked)
3. Calls back to PI Base to release funds
4. PI Base verifies caller is authorized mandate
5. Payment executed and next payment scheduled

## Development

### Testing

Run the comprehensive test suite:

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test categories
python -m pytest tests/test_contracts.py::TestContractCompilation -v
python -m pytest tests/test_contracts.py::TestContractLogic -v
```

### Compilation

Compile all contracts to TEAL:

```bash
python scripts/compile_contracts.py
```

Output files are generated in the `build/` directory:
- `strahn_core_approval.teal`
- `strahn_core_clear.teal`
- `strahn_pi_base_approval.teal`
- `strahn_pi_base_clear.teal`
- `mandate_record_approval.teal`
- `mandate_record_clear.teal`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Support

For questions and support, please open an issue in the GitHub repository.