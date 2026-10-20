"""Optional domain examples; not part of the workflow engine contract."""
import copy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from errors import WorkflowError


def read_orders(data, params):
    if not isinstance(data, list) or not data or len(data) > 10000:
        raise WorkflowError("Input must be a JSON array containing 1–10000 orders")
    if not all(isinstance(row, dict) for row in data):
        raise WorkflowError("Each order must be a JSON object")
    return copy.deepcopy(data)


def validate_orders(data, params):
    amount_field = params["amount_field"]
    id_field = params["id_field"]
    result, seen = [], set()
    for index, row in enumerate(data):
        identifier = row.get(id_field)
        if not isinstance(identifier, (str, int)) or isinstance(identifier, bool) or not str(identifier).strip():
            raise WorkflowError(f"Record {index + 1} is missing a valid ID field {id_field}")
        if str(identifier) in seen:
            raise WorkflowError(f"Record {index + 1} has a duplicate ID")
        seen.add(str(identifier))
        value = row.get(amount_field)
        if isinstance(value, bool) or value is None:
            raise WorkflowError(f"Record {index + 1} is missing a valid amount field {amount_field}")
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
                raise InvalidOperation
            amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, ValueError):
            raise WorkflowError(f"Record {index + 1} has an invalid amount; expected a number between 0 and 1 billion") from None
        result.append({**row, "order_id": str(identifier), "amount": format(amount, ".2f")})
    return result


def discount_orders(data, params):
    rate = Decimal(str(params["percent"])) / Decimal(100)
    threshold = Decimal(str(params["minimum"]))
    result = []
    for row in data:
        amount = Decimal(row["amount"])
        discount = (amount * rate if amount >= threshold else Decimal(0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result.append({**row, "discount": format(discount, ".2f"), "net": format(amount - discount, ".2f")})
    return result


def summarize_orders(data, params):
    def total(field):
        return format(sum((Decimal(row[field]) for row in data), Decimal(0)), ".2f")
    return {"count": len(data), "currency": params["currency"], "gross": total("amount"), "discount": total("discount"), "net": total("net"), "orders": data}


DEFINITIONS = {
    "read_orders": {"name": "Read orders", "description": "Read this run’s order JSON; do not cache previous data", "input": None, "output": "raw_orders", "defaults": {}, "fields": [], "function": read_orders, "color": "blue"},
    "validate_orders": {"name": "Validate and normalize", "description": "Validate order IDs and amounts, normalizing money precision", "input": "raw_orders", "output": "orders", "defaults": {"id_field": "id", "amount_field": "amount"}, "fields": [{"key": "id_field", "label": "Order ID field", "type": "text"}, {"key": "amount_field", "label": "Amount field (base currency units)", "type": "text"}], "function": validate_orders, "color": "violet"},
    "discount_orders": {"name": "Calculate discount", "description": "Apply a percentage discount with an optional minimum amount", "input": "orders", "output": "priced_orders", "defaults": {"percent": 10, "minimum": 0}, "fields": [{"key": "percent", "label": "Discount (%)", "type": "number", "min": 0, "max": 100}, {"key": "minimum", "label": "Minimum amount (base currency units)", "type": "number", "min": 0, "max": 1000000000}], "function": discount_orders, "color": "amber"},
    "summarize_orders": {"name": "Build summary", "description": "Summarize order count, gross, discount and net amounts", "input": "priced_orders", "output": "report", "defaults": {"currency": "CNY"}, "fields": [{"key": "currency", "label": "Currency label (no exchange conversion)", "type": "text"}], "function": summarize_orders, "color": "green"},
}
