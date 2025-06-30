from pyteal import * # type: ignore
from utils.common import *

@Subroutine(TealType.uint64)
def is_creator():
    """Check if sender is the contract creator"""
    return Txn.sender() == App.globalGet(Bytes("creator_addr"))

@Subroutine(TealType.none)
def app_optin_usdc():
    """Opt the contract into USDC asset"""
    return Seq([
        # FIXED: Use stored creator_addr instead of Global.creator_address()
        Assert(Txn.sender() == App.globalGet(Bytes("creator_addr"))),
        
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
        }),
        InnerTxnBuilder.Submit(),
        
        Log(Bytes("usdc_optin_complete")),
    ])

@Subroutine(TealType.none)
def deposit_usdc():
    """Handle USDC deposit to the contract"""
    payment_txn_index = Txn.group_index() - Int(1)
    
    return Seq([
        # Enhanced group validation
        Assert(Global.group_size() == Int(2)),
        Assert(Txn.group_index() == Int(1)),  # This call must be second
        Assert(payment_txn_index == Int(0)),  # Payment must be first
        
        # Validate payment transaction
        Assert(Gtxn[payment_txn_index].type_enum() == TxnType.AssetTransfer),
        Assert(Gtxn[payment_txn_index].xfer_asset() == App.globalGet(Bytes("usdc_id"))),
        Assert(Gtxn[payment_txn_index].asset_receiver() == Global.current_application_address()),
        Assert(Gtxn[payment_txn_index].asset_amount() > Int(0)),
        
        # Validate sender consistency
        Assert(Gtxn[payment_txn_index].sender() == Txn.sender()),
        
        Log(Concat(Bytes("usdc_deposited:"), Itob(Gtxn[payment_txn_index].asset_amount()))),
    ])

@Subroutine(TealType.none)
def validate_balance(required_amount: Expr):
    """Validate contract has sufficient USDC balance"""
    contract_balance = AssetHolding.balance(
        Global.current_application_address(),
        App.globalGet(Bytes("usdc_id"))
    )
    
    return Seq([
        contract_balance,
        Assert(contract_balance.hasValue()),
        Assert(contract_balance.value() >= required_amount),
    ])

@Subroutine(TealType.none)
def process_intent():
    """Process a single payment intent"""
    destination = Txn.application_args[1]
    amount = Btoi(Txn.application_args[2])
    relayer_fee = Btoi(Txn.application_args[3])
    nonce = Btoi(Txn.application_args[4])
    signature = Txn.application_args[5]
    
    # FIXED: Add domain separation with contract address to prevent replay
    message = Concat(
        Bytes("SPP_V1:"),
        Itob(Global.current_application_id()),  # Domain separation
        Itob(nonce),
        destination,
        Itob(amount),
        Itob(relayer_fee)
    )
    
    current_nonce = App.globalGet(Bytes("creator_nonce"))
    total_amount = amount + relayer_fee
    
    return Seq([
        # Input validation
        Assert(Len(destination) == Int(32)),  # Valid address
        Assert(amount > Int(0)),  # Positive amount
        Assert(relayer_fee >= Int(0)),  # Non-negative fee
        Assert(total_amount > amount),  # Overflow check
        
        # Verify nonce
        Assert(nonce == current_nonce),
        
        # Verify signature
        Assert(Ed25519Verify(
            Sha256(message),
            signature,
            App.globalGet(Bytes("creator_addr"))
        )),
        
        # Validate sufficient balance
        validate_balance(total_amount),
        
        # Execute payments (merchant first, then relayer)
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: destination,
            TxnField.asset_amount: amount,
        }),
        InnerTxnBuilder.Next(),
        
        # Send fee to relayer
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: relayer_fee,
        }),
        InnerTxnBuilder.Submit(),
        
        # FIXED: Increment nonce AFTER successful payment execution
        App.globalPut(Bytes("creator_nonce"), current_nonce + Int(1)),
        
        Log(Concat(
            Bytes("payment_processed:"),
            Itob(amount),
            Bytes(":nonce:"),
            Itob(current_nonce + Int(1))
        )),
    ])

@Subroutine(TealType.none)
def setup_mandate_standard():
    """Setup a standard mandate with bytecode verification"""
    # Mandate parameters
    dest_addr = Txn.application_args[1]
    amount = Btoi(Txn.application_args[2])
    interval_sec = Btoi(Txn.application_args[3])
    start_ts = Btoi(Txn.application_args[4])
    relayer_fee = Btoi(Txn.application_args[5])
    expected_approval_hash = Txn.application_args[6]
    expected_clear_hash = Txn.application_args[7]
    signature = Txn.application_args[8]
    
    # FIXED: Add domain separation with contract address
    message = Concat(
        Bytes("MANDATE_V1:"),
        Itob(Global.current_application_id()),  # Domain separation
        dest_addr,
        Itob(amount),
        Itob(interval_sec),
        Itob(start_ts),
        Itob(relayer_fee)
    )
    
    total_amount = amount + relayer_fee
    
    return Seq([
        # Input validation
        Assert(Len(dest_addr) == Int(32)),  # Valid address
        Assert(amount > Int(0)),  # Positive amount
        Assert(interval_sec >= Int(3600)),  # Minimum 1 hour interval
        Assert(start_ts > Global.latest_timestamp()),  # Future start
        Assert(relayer_fee >= Int(0)),  # Non-negative fee
        Assert(total_amount > amount),  # Overflow check
        
        # Verify creator signature
        Assert(Ed25519Verify(
            Sha256(message),
            signature,
            App.globalGet(Bytes("creator_addr"))
        )),
        
        # Validate sufficient balance for initial payment
        validate_balance(total_amount),
        
        # Call Strahn Core to deploy mandate
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.application_id: App.globalGet(Bytes("strahn_core_app_id")),
            TxnField.application_args: [
                Bytes("deploy_mandate"),
                expected_approval_hash,
                expected_clear_hash,
                dest_addr,
                Itob(amount),
                Itob(interval_sec),
                Itob(start_ts),
                Itob(relayer_fee),
            ],
        }),
        InnerTxnBuilder.Submit(),
        
        # Execute initial payment
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: dest_addr,
            TxnField.asset_amount: amount,
        }),
        InnerTxnBuilder.Next(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: relayer_fee,
        }),
        InnerTxnBuilder.Submit(),
        
        Log(Bytes("mandate_setup_complete")),
    ])

@Subroutine(TealType.none)
def release_mandate_funds():
    """Release funds for mandate payment - can only be called by created mandate contracts"""
    destination = Txn.application_args[1]
    amount = Btoi(Txn.application_args[2])
    relayer_fee = Btoi(Txn.application_args[3])
    
    caller_creator = AppParam.creator(Txn.sender())
    total_amount = amount + relayer_fee
    
    return Seq([
        # Input validation
        Assert(Len(destination) == Int(32)),  # Valid address
        Assert(amount > Int(0)),  # Positive amount
        Assert(relayer_fee >= Int(0)),  # Non-negative fee
        Assert(total_amount > amount),  # Overflow check
        
        # Critical security check: only mandate contracts created by this PI Base can call this
        caller_creator,
        Assert(caller_creator.hasValue()),
        Assert(caller_creator.value() == Global.current_application_address()),
        
        # Validate sufficient balance
        validate_balance(total_amount),
        
        # Execute payment to merchant
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: destination,
            TxnField.asset_amount: amount,
        }),
        InnerTxnBuilder.Next(),
        
        # Execute payment to relayer
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: App.globalGet(Bytes("usdc_id")),
            TxnField.asset_receiver: Txn.sender(),
            TxnField.asset_amount: relayer_fee,
        }),
        InnerTxnBuilder.Submit(),
        
        Log(Concat(
            Bytes("mandate_payment_released:"),
            Itob(amount),
            Bytes(":mandate:"),
            Itob(Txn.sender())
        )),
    ])

def strahn_pi_base_approval():
    """Strahn PI Base approval program"""
    
    method = Txn.application_args[0]
    
    program = Seq([
        Assert(Txn.application_id() != Int(0)),
        
        Cond(
            [method == Bytes("app_optin_usdc"), app_optin_usdc()],
            [method == Bytes("deposit_usdc"), deposit_usdc()],
            [method == Bytes("process_intent"), process_intent()],
            [method == Bytes("setup_mandate_standard"), setup_mandate_standard()],
            [method == Bytes("release_mandate_funds"), release_mandate_funds()],
        ),
        
        Approve(),
    ])
    
    # Handle contract creation
    on_create = Seq([
        # Input validation for creation
        Assert(Len(Txn.application_args[0]) == Int(32)),  # Valid creator address
        Assert(Btoi(Txn.application_args[1]) > Int(0)),   # Valid USDC asset ID
        Assert(Btoi(Txn.application_args[2]) > Int(0)),   # Valid core app ID
        
        App.globalPut(Bytes("creator_addr"), Txn.application_args[0]),
        App.globalPut(Bytes("usdc_id"), Btoi(Txn.application_args[1])),
        App.globalPut(Bytes("strahn_core_app_id"), Btoi(Txn.application_args[2])),
        App.globalPut(Bytes("creator_nonce"), Int(0)),
        Approve(),
    ])
    
    return Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnComplete.NoOp, program],
        [Txn.on_completion() == OnComplete.UpdateApplication, 
         Seq([Assert(is_creator()), Approve()])],
        [Txn.on_completion() == OnComplete.DeleteApplication, 
         Seq([Assert(is_creator()), Approve()])],
    )

def strahn_pi_base_clear():
    """Strahn PI Base clear state program"""
    return Approve()

if __name__ == "__main__":
    # Compile the contract
    approval_program = compileTeal(
        strahn_pi_base_approval(), 
        Mode.Application, 
        version=8
    )
    
    clear_program = compileTeal(
        strahn_pi_base_clear(), 
        Mode.Application, 
        version=8
    )
    
    # Save compiled programs
    with open("../build/strahn_pi_base_approval.teal", "w") as f:
        f.write(approval_program)
    
    with open("../build/strahn_pi_base_clear.teal", "w") as f:
        f.write(clear_program)
    
    print("Strahn PI Base contract compiled successfully!")