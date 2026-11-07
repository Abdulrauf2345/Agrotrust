"""Money and quantity primitives.

* Money is stored as an integer count of minor units (kobo). Never floats.
* Quantities are stored as integer milli-units (1 kg == 1000) so arithmetic is
  exact and SQL comparisons/constraints stay simple.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

from .errors import ValidationFailed

_TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class Money:
    minor: int
    currency: str = "NGN"

    def __post_init__(self) -> None:
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise ValidationFailed("Money.minor must be an int")

    @classmethod
    def from_decimal(cls, value, currency: str = "NGN") -> "Money":
        if isinstance(value, float):
            raise ValidationFailed("floats are not accepted for money; use str/Decimal/int")
        try:
            d = Decimal(str(value)) if not isinstance(value, Decimal) else value
        except InvalidOperation as exc:
            raise ValidationFailed(f"invalid money value: {value!r}") from exc
        if not d.is_finite():
            raise ValidationFailed("money must be finite")
        if d != d.quantize(_TWO_PLACES):
            raise ValidationFailed("money supports at most 2 decimal places")
        return cls(int((d * 100).to_integral_value()), currency)

    def to_decimal(self) -> Decimal:
        return (Decimal(self.minor) / 100).quantize(_TWO_PLACES)

    def _check(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValidationFailed("currency mismatch")

    def __add__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.minor + other.minor, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._check(other)
        return Money(self.minor - other.minor, self.currency)

    def __lt__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor < other.minor

    def __le__(self, other: "Money") -> bool:
        self._check(other)
        return self.minor <= other.minor

    def __gt__(self, other: "Money") -> bool:
        return other < self

    def __ge__(self, other: "Money") -> bool:
        return other <= self

    def bps(self, basis_points: int) -> "Money":
        """Percentage in basis points, banker's rounding to the minor unit."""
        d = (Decimal(self.minor) * basis_points / 10000).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
        return Money(int(d), self.currency)

    def __str__(self) -> str:
        return f"{self.currency} {self.to_decimal():,}"


def to_milli(value) -> int:
    """Decimal-like quantity -> integer milli-units (max 3 decimals)."""
    if isinstance(value, float):
        raise ValidationFailed("floats are not accepted for quantities; use str/Decimal/int")
    try:
        d = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationFailed(f"invalid quantity: {value!r}") from exc
    if not d.is_finite() or d != d.quantize(Decimal("0.001")):
        raise ValidationFailed("quantity supports at most 3 decimal places")
    return int((d * 1000).to_integral_value())


def from_milli(milli: int) -> Decimal:
    return (Decimal(milli) / 1000).quantize(Decimal("0.001"))


def line_total_minor(unit_price_minor: int, qty_milli: int) -> int:
    """price_per_unit * quantity, rounded half-even to a kobo, integer math only."""
    num = unit_price_minor * qty_milli
    q, r = divmod(num, 1000)
    if r * 2 > 1000 or (r * 2 == 1000 and q % 2 == 1):
        q += 1
    return q
