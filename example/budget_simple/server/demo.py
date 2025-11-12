# /// script
# requires-python = ">=3.13"
# dependencies = ["fastapi", "uvicorn"]
# ///

from fastapi import FastAPI, Query, HTTPException
from typing import Dict
import uuid

app = FastAPI()

# Predefined users with budgets
users: Dict[str, int] = {
    "a": 10,
    "b": 10,
    "c": 10,
}

# Store transactions: tx_id -> {user, reserved_amount, settled}
transactions: Dict[str, Dict] = {}

@app.get("/reserve")
async def reserve(user: str = Query(..., description="User ID"), 
                  amount: int = Query(..., description="Amount to reserve")):
    """Reserve an amount from a user's budget."""
    if user not in users:
        raise HTTPException(status_code=404, detail=f"User '{user}' not found")
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    
    if users[user] < amount:
        raise HTTPException(status_code=400, detail=f"Insufficient budget. Available: {users[user]}, Requested: {amount}")
    
    # Reserve the amount
    users[user] -= amount
    
    # Create transaction
    tx_id = str(uuid.uuid4())
    transactions[tx_id] = {
        "user": user,
        "reserved_amount": amount,
        "settled": False
    }
    
    return {"tx_id": tx_id, "reserved": amount, "remaining_budget": users[user]}

@app.get("/settle")
async def settle(tx_id: str = Query(..., description="Transaction ID"),
                 amount: int = Query(..., description="Amount to settle")):
    """Settle a transaction. If amount is less than reserved, return the difference to budget."""
    if tx_id not in transactions:
        raise HTTPException(status_code=404, detail=f"Transaction '{tx_id}' not found")
    
    tx = transactions[tx_id]
    
    if tx["settled"]:
        raise HTTPException(status_code=400, detail="Transaction already settled")
    
    if amount < 0:
        raise HTTPException(status_code=400, detail="Amount must be non-negative")
    
    if amount > tx["reserved_amount"]:
        raise HTTPException(status_code=400, detail=f"Amount {amount} exceeds reserved amount {tx['reserved_amount']}")
    
    # Calculate difference to return to budget
    difference = tx["reserved_amount"] - amount
    
    if difference > 0:
        users[tx["user"]] += difference
    
    # Mark as settled
    tx["settled"] = True
    tx["settled_amount"] = amount
    tx["returned_amount"] = difference
    
    return {
        "tx_id": tx_id,
        "settled": amount,
        "returned": difference,
        "user_budget": users[tx["user"]]
    }

@app.get("/debug")
async def debug():
    return {
        "users": users,
        "transactions": transactions
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)