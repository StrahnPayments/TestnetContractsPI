from pyteal import *
from .utils.common import *

@Subroutine(TealType.uint64)
def is_owner():
    """Check if sender is the contract owner"""
    return Txn.sender() == App.globalGet(Bytes("owner_addr"))

@Subroutine(TealType.none)
def update_bytecode():
    """Update the mandate contract bytecode"""
    approval_code = Txn.application_args[1]
    clear_code = Txn.application_args[2]
    
    return Seq([
        Assert(is_owner()),
        App.box_put(Bytes("approval"), approval_code),
        App.box_put(Bytes("clear"), clear_code),
        Log(Bytes("bytecode_updated")),
    ])

@Subroutine(TealType.none)
def deploy_internal(approval_bytecode: Expr, clear_bytecode: Expr):
    """Internal deployment logic shared by both deployment methods"""
    # Mandate parameters from application args
    dest_addr = Txn.application_args[3]
    amount = Btoi(Txn.application_args[4])
    interval_sec = Btoi(Txn.application_args[5])
    start_ts = Btoi(Txn.application_args[6])
    relayer_fee = Btoi(Txn.application_args[7])
    
    # Get caller context
    pi_base_id = Txn.sender()  # The calling PI Base application ID
    usdc_asa_id = AppParam.global_get_ex(pi_base_id, Bytes("usdc_id"))
    
    return Seq([
        # Get USDC asset ID from calling PI Base contract
        usdc_asa_id,
        Assert(usdc_asa_id.hasValue()),
        
        # Deploy mandate contract with proper schema
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.approval_program: approval_bytecode,
            TxnField.clear_state_program: clear_bytecode,
            TxnField.global_num_uints: Int(5),  # amount, interval_sec, next_pay_ts, relayer_fee, usdc_asa_id, pi_base_id
            TxnField.global_num_byte_slices: Int(1),  # dest_addr
            TxnField.application_args: [
                dest_addr,
                Itob(amount),
                Itob(interval_sec),
                Itob(start_ts),
                Itob(relayer_fee),
                Itob(usdc_asa_id.value()),
                Itob(pi_base_id),
            ],
        }),
        InnerTxnBuilder.Submit(),
        
        # Log the created application ID for the calling PI Base to retrieve
        Log(Itob(InnerTxn.created_application_id())),
    ])

@Subroutine(TealType.none)
def deploy_mandate():
    """Deploy a new mandate contract with bytecode verification"""
    expected_approval_hash = Txn.application_args[1]
    expected_clear_hash = Txn.application_args[2]
    
    approval_code = App.box_get(Bytes("approval"))
    clear_code = App.box_get(Bytes("clear"))
    
    return Seq([
        # Verify bytecode integrity (user consent mechanism)
        Assert(approval_code.hasValue()),
        Assert(clear_code.hasValue()),
        Assert(Sha256(approval_code.value()) == expected_approval_hash),
        Assert(Sha256(clear_code.value()) == expected_clear_hash),
        
        # Deploy using internal helper
        deploy_internal(approval_code.value(), clear_code.value()),
    ])

@Subroutine(TealType.none)
def deploy_legacy_mandate():
    """Deploy a mandate contract with legacy bytecode (user-assumed risk)"""
    legacy_approval = Txn.application_args[1]
    legacy_clear = Txn.application_args[2]
    
    return Seq([
        # Deploy with provided legacy bytecode (bypasses stored code)
        deploy_internal(legacy_approval, legacy_clear),
    ])

@Subroutine(TealType.none)
def get_current_bytecode_hashes():
    """Return SHA-256 hashes of current official bytecode"""
    approval_code = App.box_get(Bytes("approval"))
    clear_code = App.box_get(Bytes("clear"))
    
    return Seq([
        Assert(approval_code.hasValue()),
        Assert(clear_code.hasValue()),
        
        # Log both hashes for client retrieval
        Log(Concat(
            Bytes("approval_hash:"),
            Sha256(approval_code.value()),
            Bytes(":clear_hash:"),
            Sha256(clear_code.value())
        )),
    ])

def strahn_core_approval():
    """Strahn Core approval program"""
    
    # Handle contract creation
    on_create = Seq([
        App.globalPut(Bytes("owner_addr"), Txn.application_args[0]),
        Approve(),
    ])
    
    # Method routing for application calls
    method = Txn.application_args[0]
    
    program = Seq([
        Assert(Txn.application_id() != Int(0)),  # Prevent creation calls
        
        Cond(
            [method == Bytes("update_bytecode"), update_bytecode()],
            [method == Bytes("deploy_mandate"), 
             Seq([
                 # Must be called by another application
                 Assert(Txn.sender() != Global.zero_address()),
                 Assert(Txn.type_enum() == TxnType.ApplicationCall),
                 deploy_mandate()
             ])],
            [method == Bytes("deploy_legacy_mandate"), 
             Seq([
                 # Must be called by another application
                 Assert(Txn.sender() != Global.zero_address()),
                 Assert(Txn.type_enum() == TxnType.ApplicationCall),
                 deploy_legacy_mandate()
             ])],
            [method == Bytes("get_current_bytecode_hashes"), get_current_bytecode_hashes()],
        ),
        
        Approve(),
    ])
    
    return Cond(
        [Txn.application_id() == Int(0), on_create],
        [Txn.on_completion() == OnCall.NoOp, program],
        [Txn.on_completion() == OnCall.UpdateApplication, 
         Seq([Assert(is_owner()), Approve()])],
        [Txn.on_completion() == OnCall.DeleteApplication, 
         Seq([Assert(is_owner()), Approve()])],
    )

def strahn_core_clear():
    """Strahn Core clear state program"""
    return Approve()

if __name__ == "__main__":
    # Compile the contract
    approval_program = compileTeal(
        strahn_core_approval(), 
        Mode.Application, 
        version=8
    )
    
    clear_program = compileTeal(
        strahn_core_clear(), 
        Mode.Application, 
        version=8
    )
    
    # Save compiled programs
    with open("../build/strahn_core_approval.teal", "w") as f:
        f.write(approval_program)
    
    with open("../build/strahn_core_clear.teal", "w") as f:
        f.write(clear_program)
    
    print("Strahn Core contract compiled successfully!")