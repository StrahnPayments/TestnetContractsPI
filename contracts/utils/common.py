from pyteal import *

# Common constants
USDC_ASSET_ID = Int(31566704)  # Mainnet USDC asset ID
SIGNATURE_LENGTH = Int(64)
ADDRESS_LENGTH = Int(32)

# Common validation functions
@Subroutine(TealType.uint64)
def validate_signature_length(signature: Expr):
    """Validate signature is proper length"""
    return Len(signature) == SIGNATURE_LENGTH

@Subroutine(TealType.uint64)
def validate_address_length(address: Expr):
    """Validate address is proper length"""
    return Len(address) == ADDRESS_LENGTH

@Subroutine(TealType.uint64)
def validate_positive_amount(amount: Expr):
    """Validate amount is positive"""
    return amount > Int(0)

# Error handling constants
ERROR_INVALID_SIGNATURE = Bytes("INVALID_SIGNATURE")
ERROR_INVALID_NONCE = Bytes("INVALID_NONCE")
ERROR_INSUFFICIENT_FUNDS = Bytes("INSUFFICIENT_FUNDS")
ERROR_UNAUTHORIZED = Bytes("UNAUTHORIZED")
ERROR_INVALID_AMOUNT = Bytes("INVALID_AMOUNT")

# Logging helpers
@Subroutine(TealType.none)
def log_error(error_code: Expr):
    """Log an error with consistent format"""
    return Log(Concat(Bytes("ERROR:"), error_code))

@Subroutine(TealType.none)
def log_success(operation: Expr, details: Expr):
    """Log a successful operation"""
    return Log(Concat(Bytes("SUCCESS:"), operation, Bytes(":"), details))