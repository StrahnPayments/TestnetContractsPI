from pyteal import *

# Common constants
USDC_ASSET_ID = Int(31566704)  # Mainnet USDC asset ID
SIGNATURE_LENGTH = Int(64)
ADDRESS_LENGTH = Int(32)

# Timing constants
MIN_INTERVAL_SEC = Int(3600)    # 1 hour minimum
MAX_INTERVAL_SEC = Int(31536000)  # 1 year maximum
TIMESTAMP_TOLERANCE = Int(300)   # 5 minutes tolerance for mandate payments
MAX_TIMESTAMP = Int(4102444800)  # Year 2100 (reasonable max)

# Size limits
MAX_BYTECODE_SIZE = Int(8192)   # 8KB max for approval program
MAX_CLEAR_SIZE = Int(1024)      # 1KB max for clear program

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

@Subroutine(TealType.uint64)
def validate_non_negative_amount(amount: Expr):
    """Validate amount is non-negative"""
    return amount >= Int(0)

@Subroutine(TealType.uint64)
def validate_timestamp_range(timestamp: Expr):
    """Validate timestamp is in reasonable range"""
    return And(
        timestamp > Global.latest_timestamp(),
        timestamp < MAX_TIMESTAMP
    )

@Subroutine(TealType.uint64)
def validate_interval_range(interval: Expr):
    """Validate interval is in acceptable range"""
    return And(
        interval >= MIN_INTERVAL_SEC,
        interval <= MAX_INTERVAL_SEC
    )

@Subroutine(TealType.uint64)
def validate_asset_id(asset_id: Expr):
    """Validate asset ID is reasonable"""
    return And(
        asset_id > Int(0),
        asset_id < Int(4294967295)  # Max uint32
    )

@Subroutine(TealType.uint64)
def check_overflow_add(a: Expr, b: Expr):
    """Check if addition would overflow"""
    return a + b > a

# Error handling constants
ERROR_INVALID_SIGNATURE = Bytes("INVALID_SIGNATURE")
ERROR_INVALID_NONCE = Bytes("INVALID_NONCE")
ERROR_INSUFFICIENT_FUNDS = Bytes("INSUFFICIENT_FUNDS")
ERROR_UNAUTHORIZED = Bytes("UNAUTHORIZED")
ERROR_INVALID_AMOUNT = Bytes("INVALID_AMOUNT")
ERROR_INVALID_ADDRESS = Bytes("INVALID_ADDRESS")
ERROR_INVALID_TIMESTAMP = Bytes("INVALID_TIMESTAMP")
ERROR_INVALID_INTERVAL = Bytes("INVALID_INTERVAL")
ERROR_OVERFLOW = Bytes("OVERFLOW")

# Logging helpers
@Subroutine(TealType.none)
def log_error(error_code: Expr):
    """Log an error with consistent format"""
    return Log(Concat(Bytes("ERROR:"), error_code))

@Subroutine(TealType.none)
def log_success(operation: Expr, details: Expr):
    """Log a successful operation"""
    return Log(Concat(Bytes("SUCCESS:"), operation, Bytes(":"), details))

@Subroutine(TealType.none)
def log_validation_failure(field: Expr, value: Expr):
    """Log validation failure with field and value"""
    return Log(Concat(Bytes("VALIDATION_FAILED:"), field, Bytes(":"), value))