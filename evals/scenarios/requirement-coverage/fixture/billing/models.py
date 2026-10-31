from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass
class Customer:
    id: int
    legal_name: str
    trade_name: str | None = None
    preferences: dict = field(default_factory=dict)  # e.g. {"no_contact": True, "language": "es"}

    @property
    def name(self) -> str:
        return self.trade_name or self.legal_name


@dataclass
class Invoice:
    number: str
    customer: Customer
    amount: Decimal
    due: date
    paid: bool = False
