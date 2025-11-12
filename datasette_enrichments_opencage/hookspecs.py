from pluggy import HookspecMarker
from abc import ABC, abstractmethod

class Tx:
    tx_id: str

class BudgetCheck(ABC):
    
    @abstractmethod
    async def reserve(self, amount: int) -> Tx:
        pass
    
    @abstractmethod
    async def settle(self, tx: Tx, amount: int, meta: dict | None = None):
        pass
    
hookspec = HookspecMarker("datasette")

@hookspec
async def datasette_enrichments_register_budget_check(datasette) -> BudgetCheck:
    ...