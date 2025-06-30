import os
import sys
import json
import base64
from algosdk.v2client import algod
from algosdk import account, transaction, encoding, mnemonic
from algosdk.logic import get_application_address

def get_account_details_from_mnemonic():
    """Derives private and public keys from a BIP-39 (12/24 word) mnemonic."""
    try:
        sender_mnemonic = os.environ.get("MNEMONIC")
        if not sender_mnemonic:
            # raise ValueError("MNEMONIC environment variable not set. Please set your 25-word seed phrase.")
            sender_mnemonic = "general high slush peanut yellow exclude range giant sheriff reflect phone mistake crack athlete column mandate great square seminar cool dream ripple cherry able month"

            print("Fallback used!")

        # Get account details from mnemonic
        sender_private_key = mnemonic.to_private_key(sender_mnemonic)
        
        private_key = sender_private_key
        address = account.address_from_private_key(private_key)
        return private_key, address
    except Exception as e:
        raise ValueError(f"Error deriving key from mnemonic: {e}. Ensure it's a valid BIP39 phrase.")