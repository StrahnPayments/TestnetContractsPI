from pyteal import *
from utils.common import *

@Subroutine(TealType.uint64)
def is_owner():
    """Check if sender is the contract owner"""
    return Txn.sender() == App.globalGet(Bytes("owner_addr"))
# In strahn_core.py
# In strahn_core.py

@Subroutine(TealType.none)
def set_bytecode():
    """
    Creates/resets a box and initializes it with the first chunk of bytecode.
    Takes the total intended size of the box as an argument.
    """
    box_name = Txn.application_args[1]
    total_size = Btoi(Txn.application_args[2]) # Total size of the box
    
    return Seq([
        Assert(is_owner()),

        Assert(Or(
            box_name == Bytes("approval"),
            box_name == Bytes("clear")
        )),

        # Pop() the result of App.box_delete to ensure TealType.none
        Pop(App.box_delete(box_name)), 

        # Create a new box with the total specified size.
        # This allocates the full space.
        Pop(App.box_create(box_name, total_size)), 
        
        # Write the first chunk at offset 0.
        App.box_replace(box_name, Int(0), Txn.note()), 
        
        Log(Concat(Bytes("set_bytecode_complete:"), box_name))
    ])


@Subroutine(TealType.none)
def append_bytecode():
    """
    Appends the content of the transaction note to an existing box.
    This is an owner-only function.
    """
    box_name = Txn.application_args[1]
    
    # We now get the current length using App.box_len, not App.box_get,
    # as App.box_get will fail for boxes > 4KB.
    current_len_maybe = App.box_length(box_name)
    current_len_var = ScratchVar(TealType.uint64)
    new_len_var = ScratchVar(TealType.uint64)

    return Seq([
        Assert(is_owner()),

        Assert(Or(
            box_name == Bytes("approval"),
            box_name == Bytes("clear")
        )),

        # Ensure the box exists and get its current length
        current_len_maybe, # Execute App.box_len
        Assert(current_len_maybe.hasValue()), # Check if box exists
        current_len_var.store(current_len_maybe.value()), # Store current length

        # Calculate the new total length after appending this chunk
        new_len_var.store(current_len_var.load() + Len(Txn.note())),

        # Explicitly resize the box to the new total length.
        # This will only succeed if the box was originally created with enough
        # capacity, or if the network allows dynamic growth (it does, but still needs `box_resize`).
        App.box_resize(box_name, new_len_var.load()),
        
        # Now, replace (append) the new chunk at the previous end
        App.box_replace(
            box_name, 
            current_len_var.load(), # Offset: start writing at the end of current content
            Txn.note()               # Data to write (the chunk from Txn.note())
        ),
        
        Log(Concat(Bytes("append_bytecode_complete:"), box_name))
    ])


# In strahn_core.py

# ... (set_bytecode and append_bytecode are correct now, no changes needed to them) ...

@Subroutine(TealType.none)
def set_version():
    """
    Sets the bytecode version number and copies the current 'approval' and 'clear'
    boxes to versioned boxes ('approval_v{version}', 'clear_v{version}').
    Handles large boxes by copying in chunks.
    """
    version = Btoi(Txn.application_args[1])
    current_version_on_chain = App.globalGet(Bytes("bytecode_version"))

    # Define a helper subroutine for copying a box without App.box_get
    @Subroutine(TealType.none)
    def copy_box(source_box_name: Expr, dest_box_name: Expr):
        
        source_box_len_maybe = App.box_length(source_box_name)
        
        # Declare scratch variables for the loop
        offset = ScratchVar(TealType.uint64)
        chunk_data = ScratchVar(TealType.bytes)
        source_box_len = ScratchVar(TealType.uint64)
        
        # Loop constants
        MAX_CHUNK_SIZE = Int(1024)
        
        # ScratchVar to hold the calculated current_chunk_size
        current_chunk_size_var = ScratchVar(TealType.uint64)
        
        return Seq([
            # Get the source box length (without loading contents)
            source_box_len_maybe,
            Assert(source_box_len_maybe.hasValue()), # Assert box exists
            source_box_len.store(source_box_len_maybe.value()), # Assign actual length
            
            # Create the destination box with the determined total size
            Pop(App.box_delete(dest_box_name)), # Ensure clean
            Pop(App.box_create(dest_box_name, source_box_len.load())),

            # Loop through the source box and copy chunks
            For(offset.store(Int(0)), offset.load() < source_box_len.load(), offset.store(offset.load() + MAX_CHUNK_SIZE)).Do(
                Seq([
                    # CRITICAL FIX HERE: Implement Min using If/Else
                    If(MAX_CHUNK_SIZE < source_box_len.load() - offset.load())
                        .Then(current_chunk_size_var.store(MAX_CHUNK_SIZE))
                        .Else(current_chunk_size_var.store(source_box_len.load() - offset.load())),
                    
                    # Read a chunk from the source box using box_extract
                    chunk_data.store(App.box_extract(source_box_name, offset.load(), current_chunk_size_var.load())),
                    
                    # Write the chunk to the destination box
                    App.box_replace(dest_box_name, offset.load(), chunk_data.load())
                ])
            )
        ])

    return Seq([
        Assert(is_owner()),
        Assert(version > current_version_on_chain), # Prevent rollback

        # Perform the actual copies by calling copy_box
        copy_box(Bytes("approval"), Concat(Bytes("approval_v"), Itob(version))),
        copy_box(Bytes("clear"), Concat(Bytes("clear_v"), Itob(version))),

        # Update the master version number
        App.globalPut(Bytes("bytecode_version"), version),

        Log(Concat(Bytes("version_set:v"), Itob(version)))
    ])

# ... rest of strahn_core.py's main logic unchanged ...
# ... rest of strahn_core.py's main logic unchanged ...
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
    # pi_base_id = Txn.sender()  # The calling PI Base application ID
    pi_base_id = Txn.applications[1]
    usdc_asa_id = App.globalGetEx(pi_base_id, Bytes("usdc_id"))
    
    return Seq([
        # Validate input parameters
        Assert(Len(dest_addr) == Int(32)),  # Valid Algorand address
        Assert(amount > Int(0)),  # Positive amount
        Assert(interval_sec >= Int(3600)),  # Minimum 1 hour interval
        Assert(start_ts > Global.latest_timestamp()),  # Future start time
        Assert(relayer_fee >= Int(0)),  # Non-negative fee
        
        # Get USDC asset ID from calling PI Base contract
        usdc_asa_id,
        Assert(usdc_asa_id.hasValue()),
        
        # Validate asset ID is reasonable (prevent invalid assets)
        Assert(usdc_asa_id.value() > Int(0)),
        Assert(usdc_asa_id.value() < Int(4294967295)),  # Max uint32
        
        # Deploy mandate contract with corrected schema
        InnerTxnBuilder.Begin(),
        InnerTxnBuilder.SetFields({
            TxnField.type_enum: TxnType.ApplicationCall,
            TxnField.approval_program: approval_bytecode,
            TxnField.clear_state_program: clear_bytecode,
            TxnField.global_num_uints: Int(6),  # FIXED: amount, interval_sec, next_pay_ts, relayer_fee, usdc_asa_id, pi_base_id
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
        Log(Concat(
            Bytes("mandate_deployed:"),
            Itob(InnerTxn.created_application_id()),
            Bytes(":pi_base:"),
            Itob(pi_base_id)
        )),
    ])

@Subroutine(TealType.none)
def deploy_mandate():
    """Deploy a new mandate contract with bytecode verification (TOCTOU fix)"""
    expected_approval_hash = Txn.application_args[1]
    expected_clear_hash = Txn.application_args[2]
    
    # Just define the recipes
    approval_code = App.box_get(Bytes("approval"))
    clear_code = App.box_get(Bytes("clear"))
    
    # A scratch variable to hold the version we read at the start
    initial_version = ScratchVar(TealType.uint64)
    
    return Seq([
        # Store the current version at the beginning of execution
        initial_version.store(App.globalGet(Bytes("bytecode_version"))),
        
        # Now execute the box reads
        approval_code,
        clear_code,

        # Assert that the boxes have values
        Assert(approval_code.hasValue()),
        Assert(clear_code.hasValue()),
        
        # TOCTOU fix: Re-verify version hasn't changed during execution
        # Compare the current version against the one we saved at the start.
        Assert(initial_version.load() == App.globalGet(Bytes("bytecode_version"))),
        
        # Verify bytecode hashes match user expectations
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
        # Validate bytecode size limits to prevent DoS
        Assert(Len(legacy_approval) <= Int(8192)),  # 8KB limit
        Assert(Len(legacy_clear) <= Int(1024)),     # 1KB limit
        
        # Deploy with provided legacy bytecode (bypasses stored code)
        deploy_internal(legacy_approval, legacy_clear),
    ])

@Subroutine(TealType.none)
def get_current_bytecode_hashes():
    """Return SHA-256 hashes of current official bytecode"""
    # Define the recipes
    approval_code = App.box_get(Bytes("approval"))
    clear_code = App.box_get(Bytes("clear"))
    
    return Seq([
        # Step 1: Execute the box_get operations. The results are now available.
        approval_code,
        clear_code,
        
        # Step 2: Assert that the values were found.
        Assert(approval_code.hasValue()),
        Assert(clear_code.hasValue()),
        
        # Step 3: Log the hashes. Now it's safe to use .value() and App.globalGet()
        Log(Concat(
            Bytes("approval_hash:"),
            Sha256(approval_code.value()),
            Bytes(":clear_hash:"),
            Sha256(clear_code.value()),
            Bytes(":version:"),
            Itob(App.globalGet(Bytes("bytecode_version"))) # Get the value directly here
        )),
    ])

def strahn_core_approval():
    """Strahn Core approval program"""
    
    # Handle contract creation
    on_create = Seq([
        App.globalPut(Bytes("owner_addr"), Txn.application_args[0]),
        App.globalPut(Bytes("bytecode_version"), Int(0)),  # Initialize version
        Approve(),
    ])
    
    # Method routing for application calls
    method = Txn.application_args[0]
    
    program = Seq([
        Assert(Txn.application_id() != Int(0)),
        
        Cond(
            # [method == Bytes("update_bytecode"), update_bytecode()], # <-- REMOVE OLD
            [method == Bytes("set_bytecode"), set_bytecode()],       # <-- ADD NEW
            [method == Bytes("set_version"), set_version()],         # <-- ADD NEW
            [method == Bytes("append_bytecode"), append_bytecode()],
            [method == Bytes("deploy_mandate"), 
            Seq([
                Assert(Txn.sender() != Global.zero_address()),
                Assert(Txn.type_enum() == TxnType.ApplicationCall),
                deploy_mandate()
            ])],
            [method == Bytes("deploy_legacy_mandate"), # This legacy one is still fine
            Seq([
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
        [Txn.on_completion() == OnComplete.NoOp, program],
        [Txn.on_completion() == OnComplete.UpdateApplication, 
         Seq([Assert(is_owner()), Approve()])],
        [Txn.on_completion() == OnComplete.DeleteApplication, 
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
        version=10
    )
    
    clear_program = compileTeal(
        strahn_core_clear(), 
        Mode.Application, 
        version=10
    )
    
    # Save compiled programs
    with open("../build/strahn_core_approval.teal", "w") as f:
        f.write(approval_program)
    
    with open("../build/strahn_core_clear.teal", "w") as f:
        f.write(clear_program)
    
    print("Strahn Core contract compiled successfully!")