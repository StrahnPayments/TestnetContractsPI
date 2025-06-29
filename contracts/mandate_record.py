from pyteal import *
from .utils.common import *

@Subroutine(TealType.none)
def process_payment():
    """Process a recurring mandate payment"""
    current_time = Global.latest_timestamp()
    next_payment_time = App.globalGet(Bytes("next_pay_ts"))
    
    return Seq([
        # Time-lock verification - payment must be due
        Assert(current_time >= next_payment_time),
        
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
        # Calculate new next payment timestamp
        App.globalPut(
            Bytes("next_pay_ts"),
            next_payment_time + App.globalGet(Bytes("interval_sec"))
        ),
        
        # Log successful payment processing
        Log(Concat(
            Bytes("mandate_payment_processed:"),
            Itob(App.globalGet(Bytes("amount"))),
            Bytes(":"),
            Itob(next_payment_time + App.globalGet(Bytes("interval_sec")))
        )),
    ])

def mandate_record_approval():
    """Mandate Record approval program"""
    
    # Handle contract creation
    on_create = Seq([
        # Initialize global state from creation arguments
        # Args: [dest_addr, amount, interval_sec, start_ts, relayer_fee, usdc_asa_id, pi_base_id]
        App.globalPut(Bytes("dest_addr"), Txn.application_args[0]),
        App.globalPut(Bytes("amount"), Btoi(Txn.application_args[1])),
        App.globalPut(Bytes("interval_sec"), Btoi(Txn.application_args[2])),
        App.globalPut(Bytes("next_pay_ts"), Btoi(Txn.application_args[3])),  # start_ts
        App.globalPut(Bytes("relayer_fee"), Btoi(Txn.application_args[4])),
        App.globalPut(Bytes("usdc_asa_id"), Btoi(Txn.application_args[5])),
        App.globalPut(Bytes("pi_base_id"), Btoi(Txn.application_args[6])),
        
        # Opt-in to USDC asset (required for inner transaction references)
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.AssetTransfer,
            TxnField.xfer_asset: Btoi(Txn.application_args[5]),  # usdc_asa_id
            TxnField.asset_receiver: Global.current_application_address(),
            TxnField.asset_amount: Int(0),
        }),
        InnerTxnBuilder.Submit(),
        
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
        [Txn.on_completion() == OnCall.NoOp, program],
        # Mandate records are immutable once created - no updates allowed
        [Txn.on_completion() == OnCall.UpdateApplication, Reject()],
        # Deletion is allowed (for mandate cancellation by PI Base)
        [Txn.on_completion() == OnCall.DeleteApplication, Approve()],
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