"""Motor de séries diárias de custo: nativo-ou-rateio e stitch híbrido.

Sem MPXJ/JVM. Usado por project_parser e pelos testes unitários.
"""

from __future__ import annotations

from datetime import date

COST_EPS = 1e-9
NATIVE_INFLATE_RATIO = 1.01
NATIVE_INFLATE_ABS = 0.01

AccrualKind = str  # "START" | "END" | "PRORATED"


def own_or_assignment(
    task_amount: float, assignment_amount: float, own_cap: float
) -> float:
    """Usa o valor da tarefa se couber no custo próprio; senão só atribuições.

    Evita o rollup WBS (Cost/ActualCost/RemainingCost do pai = soma dos filhos).
    Se a tarefa tem custo próprio (FixedCost + atribuições) e o valor da tarefa
    não ultrapassa esse teto, trata como próprio (custo fixo apropriado).
    """
    if task_amount <= own_cap * NATIVE_INFLATE_RATIO + NATIVE_INFLATE_ABS:
        return max(assignment_amount, task_amount)
    return assignment_amount


def spread_amount(
    amount: float,
    working_indices: list[int],
    accrual_kind: AccrualKind,
    size: int,
) -> list[float]:
    """Distribui um total pelos dias úteis conforme o acúmulo do Project."""
    result = [0.0] * size
    if amount <= COST_EPS or not working_indices:
        return result

    kind = accrual_kind or "PRORATED"
    if kind == "START":
        result[working_indices[0]] = amount
        return result
    if kind == "END":
        result[working_indices[-1]] = amount
        return result

    day_count = len(working_indices)
    share = amount / day_count
    allocated = 0.0
    for position, index in enumerate(working_indices):
        if position == day_count - 1:
            result[index] = amount - allocated
        else:
            result[index] = share
            allocated += share
    return result


def timephased_or_spread(
    native: list[float],
    scalar: float,
    working_indices: list[int],
    accrual_kind: AccrualKind,
) -> tuple[list[float], bool, bool]:
    """Usa o nativo se bater com o total próprio; senão rateia.

    Pai sem custo próprio (scalar ~ 0) zera a série.
    Nativo só entra se a soma estiver a ±1% do total próprio.
    Vazio, abaixo demais ou inflado cai no rateio por dia útil.
    """
    size = len(native)
    if scalar <= COST_EPS:
        return [0.0] * size, False, False

    native_sum = sum(native)
    inflate_limit = scalar * NATIVE_INFLATE_RATIO + NATIVE_INFLATE_ABS
    lower_limit = scalar * (2.0 - NATIVE_INFLATE_RATIO) - NATIVE_INFLATE_ABS
    if COST_EPS < native_sum and lower_limit <= native_sum <= inflate_limit:
        return list(native), False, False

    spread = spread_amount(scalar, working_indices, accrual_kind, size)
    inflated = native_sum > inflate_limit
    return spread, True, inflated


def combine_resource_and_fixed(
    resource: list[float], fixed: list[float]
) -> list[float]:
    """Junta custo de recurso e custo fixo faseado, sem duplicar.

    Se o nativo de recurso já contém o fixo (fixo <= recurso em todo dia),
    devolve só o recurso. Se um dos dois é vazio, devolve o outro. Senão soma.
    """
    if not fixed or sum(fixed) <= COST_EPS:
        return list(resource)
    if not resource or sum(resource) <= COST_EPS:
        return list(fixed)
    if all(f <= r + COST_EPS for r, f in zip(resource, fixed)):
        return list(resource)
    return [r + f for r, f in zip(resource, fixed)]


def indices_on_or_before(
    days: list[date | None], status_date: date, candidates: list[int]
) -> list[int]:
    """Índices candidatos com data até a Status Date (inclusive)."""
    return [
        index
        for index in candidates
        if days[index] is not None and days[index] <= status_date
    ]


def indices_after(
    days: list[date | None], status_date: date, candidates: list[int]
) -> list[int]:
    """Índices candidatos com data estritamente depois da Status Date."""
    return [
        index
        for index in candidates
        if days[index] is not None and days[index] > status_date
    ]


def clip_to_on_or_before(
    values: list[float], days: list[date | None], status_date: date
) -> list[float]:
    """Zera valores depois da Status Date."""
    return [
        value if day is not None and day <= status_date else 0.0
        for value, day in zip(values, days)
    ]


def clip_to_after(
    values: list[float], days: list[date | None], status_date: date
) -> list[float]:
    """Zera valores até a Status Date (inclusive)."""
    return [
        value if day is not None and day > status_date else 0.0
        for value, day in zip(values, days)
    ]


def stitch_hybrid(
    days: list[date | None],
    actual: list[float],
    remaining: list[float],
    status_date: date,
) -> list[float]:
    """Custo projetado: real até a Status Date, remaining depois."""
    result: list[float] = []
    for index, day in enumerate(days):
        if day is None:
            result.append(0.0)
        elif day <= status_date:
            result.append(actual[index])
        else:
            result.append(remaining[index])
    return result
