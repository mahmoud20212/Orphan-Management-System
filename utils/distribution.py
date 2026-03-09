from decimal import Decimal, ROUND_HALF_UP

from database.models import GenderEnum


MONEY_QUANT = Decimal("0.01")


def to_decimal_money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def calculate_beneficiary_distribution(beneficiaries, total_amount, mode: str):
    shares = {}
    if not beneficiaries:
        return shares

    total_amount_dec = to_decimal_money(total_amount)
    if total_amount_dec <= Decimal("0.00"):
        return shares

    weighted_beneficiaries = []
    for index, beneficiary in enumerate(beneficiaries):
        if mode == "للذكر مثل حظ الأنثيين":
            weight = Decimal("2") if beneficiary.get("gender") == GenderEnum.male else Decimal("1")
        else:
            weight = Decimal("1")

        if weight <= 0:
            continue

        beneficiary_key = (beneficiary["kind"], beneficiary["id"])
        weighted_beneficiaries.append((index, beneficiary_key, weight))

    if not weighted_beneficiaries:
        return shares

    total_weight = sum(weight for _, _, weight in weighted_beneficiaries)
    if total_weight <= 0:
        return shares

    for _, beneficiary_key, weight in weighted_beneficiaries:
        raw_share = (total_amount_dec * weight) / total_weight
        shares[beneficiary_key] = raw_share.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    rounded_sum = sum(shares.values(), Decimal("0.00"))
    rounding_diff = (total_amount_dec - rounded_sum).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    if rounding_diff != Decimal("0.00"):
        last_key = weighted_beneficiaries[-1][1]
        shares[last_key] = (shares[last_key] + rounding_diff).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)

    return shares