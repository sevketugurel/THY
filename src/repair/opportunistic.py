"""M5i RCR Engine — fırsatçı (per-iterasyon) kill seçimi (2026-07-12 gecesi
round-1 otopsi düzeltmesi; spec §4.1'in "LNS kapatmaları kendisi gerçekleştirir"
mekanizmasının DOĞRU implementasyonu).

Sözleşme: bir LNS iterasyonunda x.fix(0) yalnızca, o iterasyonun serbestlik
durumu altında gap'i [L,U] DIŞINA gerçekten taşıyabilen kill-adaylarına
uygulanır. Donuk taraflar referans zamanlarına sabitlendiğinden efektif gap
aralığı daralır; aralık tamamen pencere içindeyse fix(0), B'nin çift yönlü
reifikasyonuyla (gap∈[L,U] ⟺ x=1) çelişir ve alt-modeli KOŞULSUZ infeasible
yapar -- bu adaylar o iterasyonda atlanır (kill, kendi bileşeni hedeflendiği
turda gerçekleşir). Global Σslack muhasebesi zamanlardan türediği için bu
erteleme keep-best metriğini bozmaz."""


def select_opportunistic_kills(candidates, directions_to_kill, free_arr, free_dep,
                               reference_arr, reference_dep, L, U):
    """Returns (fix_indices, n_skipped): bu iterasyonda x.fix(0) uygulanacak
    candidate indeksleri + çelişki nedeniyle atlanan kill-adayı sayısı.

    Efektif gap aralığı: serbest taraf kendi [lo,hi]'sini, donuk taraf
    referans değerini kullanır; aralığın bir noktası [L,U] dışındaysa fix
    güvenlidir (donuk-donuk pencere-dışı dahil -- x=0 zaten tutarlı)."""
    dirset = {tuple(d) for d in directions_to_kill}
    fix_indices, n_skipped = [], 0
    for i, c in enumerate(candidates):
        if (c.o, c.d, c.gun) not in dirset:
            continue
        if c.r1_id in free_arr:
            arr_lo, arr_hi = c.arr_lo, c.arr_hi
        else:
            arr_lo = arr_hi = reference_arr[c.r1_id]
        if c.r2_id in free_dep:
            dep_lo, dep_hi = c.dep_lo, c.dep_hi
        else:
            dep_lo = dep_hi = reference_dep[c.r2_id]
        gap_min = dep_lo - arr_hi
        gap_max = dep_hi - arr_lo
        if gap_min >= L and gap_max <= U:
            n_skipped += 1  # pencere dışına ulaşamaz -- fix(0) alt-modeli zehirler
        else:
            fix_indices.append(i)
    return fix_indices, n_skipped
