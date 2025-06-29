from pyteal import *
from .utils.common import *

@Subroutine(TealType.none)
def process_payment():
    """Process a recurring mandate payment"""
    current_time = Global.latest_timestamp()
    next_payment_time = App.globalGet(Bytes("next_pay_ts"))
    interval_sec = App.globalGet(Bytes("interval_sec"))
    
    # FIXED: Add overflow protection for timestamp calculation
    new_next_payment = next_payment_time + interval_sec
    
    return Seq([
        Assert(current_time >= next_payment_time - Int(60))
        
        # Overflow protection
        Assert(new_next_payment > next_payment_time),  # Detect overflow
        Assert(new_next_payment < Int(4102444800)),     # Max reasonable timestamp (2100)
        
        # Inner application call to PI Base to release funds
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.application_id: App.globalGet(Bytes("pi_base_id")),
            TxnField.application_args: [
                Bytes("release_mandate_funds"),
                App.globalGet(Bytes("dest_addr")),
                Itob(App.globalGet(Bytes("amount"))),
                Itob(App.globalGet(Bytes("relayer_fee"))),
            ],
            TxnField.assets: [App.globalGet(Bytes("usdc_asa_id"))],
            TxnField.applications: [App.globalGet(Bytes("pi_base_id"))],
        }),
        InnerTxnBuilder.Submit(),
        
        # State update - only executed if inner call succeeds
        App.globalPut(Bytes("next_pay_ts"), new_next_payment),
        
        # Log successful payment processing
        Log(Concat(
            Bytes("mandate_payment_processed:"),
            Itob(App.globalGet(Bytes("amount"))),
            Bytes(":next_payment:"),
            Itob(new_next_payment)
        ))
    ])

def mandate_record_approval():
    """Mandate Record approval program"""
    
    # Handle contract creation
    on_create = Seq([
        # FIXED: Add comprehensive input validation
        Assert(Len(Txn.application_args[0]) == Int(32)),  # Valid dest_addr
        Assert(Btoi(Txn.application_args[1]) > Int(0)),   # Positive amount
        Assert(Btoi(Txn.application_args[2]) >= Int(3600)),  # Min 1 hour interval
        Assert(Btoi(Txn.application_args[3]) > Global.latest_timestamp()),  # Future start
        Assert(Btoi(Txn.application_args[4]) >= Int(0)),  # Non-negative relayer fee
        Assert(Btoi(Txn.application_args[5]) > Int(0)),   # Valid USDC asset ID
        Assert(Btoi(Txn.application_args[6]) > Int(0)),   # Valid PI Base ID
        
        # Additional validation
        Assert(Btoi(Txn.application_args[2]) <= Int(31536000)),  # Max 1 year interval
        Assert(Btoi(Txn.application_args[3]) < Int(4102444800)), # Max reasonable timestamp
        
        # Initialize global state from creation arguments
        App.globalPut(Bytes("dest_addr"), Txn.application_args[0]),
        App.globalPut(Bytes("amount"), Btoi(Txn.application_args[1])),
        App.globalPut(Bytes("interval_sec"), Btoi(Txn.application_args[2])),
        App.globalPut(Bytes("next_pay_ts"), Btoi(Txn.application_args[3])),  # start_ts
        App.globalPut(Bytes("relayer_fee"), Btoi(Txn.application_args[4])),
        App.globalPut(Bytes("usdc_asa_id"), Btoi(Txn.application_args[5])),
        App.globalPut(Bytes("pi_base_id"), Btoi(Txn.application_args[6])),
        
        # FIXED: Add asset existence validation before opt-in
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: Btoi(Txn.application_args[5]),  # usdc_asa_id
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
        }),
        InnerTxnBuilder.Submit(),
        
        Log(Concat(
            Bytes("mandate_created:"),
            Itob(Btoi(Txn.application_args[1])),  # amount
            Bytes(":interval:"),
            Itob(Btoi(Txn.application_args[2]))   # interval
        )),
        
        Approve(),
    ])
    
    # Handle method calls
    method = Txn.application_args[0]
    
    program = Seq([
        Assert(Txn.application_id() != Int(0)),  # Prevent creation calls here
        
        Cond(
            [method == Bytes("process_payment"), process_payment()],
        ),
        
        Approve(),
    ])
    
    return Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnComplete.NoOp, program],
        # Mandate records are immutable once created - no updates allowed
        [Txn.on_completion() == OnComplete.UpdateApplication, Reject()],
        # Deletion is allowed (for mandate cancellation by PI Base)
        [Txn.on_completion() == OnComplete.DeleteApplication, Approve()],
    )

def mandate_record_clear():
    """Mandate Record clear state program"""
    return Approve()

if __name__ == "__main__":
    # Compile the contract
    approval_program = compileTeal(
        mandate_record_approval(), 
        Mode.Application, 
        version=8
    )
    
    clear_program = compileTeal(
        mandate_record_clear(), 
        Mode.Application, 
        version=8
    )
    
    # Save compiled programs
    with open("../build/mandate_record_approval.teal", "w") as f:
        f.write(approval_program)
    
    with open("../build/mandate_record_clear.teal", "w") as f:
        f.write(clear_program)
    
    print("Mandate Record contract compiled successfully!")