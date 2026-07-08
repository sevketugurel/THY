# Mikro-Karar Günlüğü

Kod yazarken karşılaşılan, brief'i değiştirmeyen ama bir uygulama detayını
belirleyen kararlar. Her satır: karar + tek satır gerekçe. Kritik/skoru etkileyen
kararlar için `ASSUMPTIONS.md`'ye bakınız (bu dosyadakiler daha küçük ölçekli).

---

- **2026-07-09** — `adjustable_window_min` varsayılanı 720→180 dk. Gerekçe: M1
  Big-M türetimi (per-candidate) ile 720dk pencerede bazı adaylar M>1440'a
  çıkıyordu (hesap: M1 tasarım notu); 180dk hem Big-M disiplinini koruyor hem
  operasyonel olarak gerçekçi (birkaç saatlik kayma).
