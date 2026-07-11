"""M5d LNS fold-redesign (plan: .claude/plans/a-evet-ama-iki-tingly-canyon.md,
adim 1): tek dogruluk kaynagi olarak candidate/instance'lari serbest vs
donuk (frozen) olarak siniflandirir. Her fold-tabanli kurucu (B/E1/E2/G)
BUNU kullanir, kendi basina "bu aday serbest mi" sorusunu yeniden turetmez.

Bir aday (candidate) serbesttir <=> r1_id (varis) VEYA r2_id (kalkis)
serbest kumede ise -- yani "en az bir ucu oynayabiliyor" (A'nin partial-pair
desenindeki "bir bacak serbest, digeri sabit" durumuyla ayni ilke). Donuk
bir adayin HER IKI ucu da referans noktada sabit oldugundan gap/x KESIN
sabittir (compute_pair_slack'in ayni formulu, tek dogruluk kaynagi burada
merkezilestirilmis)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class PartitionResult:
    free_arr: frozenset      # {r1_id} -- t_arr icin GERCEK Var olacak
    free_dep: frozenset      # {r2_id} -- t_dep icin GERCEK Var olacak
    frozen_arr: frozenset    # tum r1_id evreni - free_arr
    frozen_dep: frozenset    # tum r2_id evreni - free_dep
    reference_arr: dict      # r1_id -> float, TAM evren (serbest UNION donuk)
    reference_dep: dict      # r2_id -> float, TAM evren
    is_free_candidate: dict  # candidate index i -> bool
    x_const: dict            # yalnizca donuk adaylar icin: i -> 0/1
    gap_const: dict          # yalnizca donuk adaylar icin: i -> int/float


def partition_by_freedom(candidates, free_arr: set, free_dep: set,
                          reference_arr: dict, reference_dep: dict,
                          L: int, U: int) -> PartitionResult:
    full_arr = set(reference_arr)
    full_dep = set(reference_dep)
    assert free_arr <= full_arr, f"free_arr referans evreninde olmayan anahtarlar iceriyor: {sorted(free_arr - full_arr)[:5]}"
    assert free_dep <= full_dep, f"free_dep referans evreninde olmayan anahtarlar iceriyor: {sorted(free_dep - full_dep)[:5]}"

    is_free_candidate, x_const, gap_const = {}, {}, {}
    for i, c in enumerate(candidates):
        free = c.r1_id in free_arr or c.r2_id in free_dep
        is_free_candidate[i] = free
        if not free:
            gap = reference_dep[c.r2_id] - reference_arr[c.r1_id]
            gap_const[i] = gap
            x_const[i] = 1 if L <= gap <= U else 0

    return PartitionResult(
        free_arr=frozenset(free_arr), free_dep=frozenset(free_dep),
        frozen_arr=frozenset(full_arr - free_arr), frozen_dep=frozenset(full_dep - free_dep),
        reference_arr=dict(reference_arr), reference_dep=dict(reference_dep),
        is_free_candidate=is_free_candidate, x_const=x_const, gap_const=gap_const,
    )
