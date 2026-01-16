#!/usr/bin/env python3
import sys
import time
import json
import argparse
import urllib.request
from collections import deque

# metrics_summary.json'den (sizde böyleydi):
EXP_ADV = {1: 21.0, 3: 21.9, 5: 15.0}

# Enerji maliyetleri (duty-cycle enerji modeli)
ENERGY = {"L0": 0.2, "L1": 0.4, "L2": 0.6}

# QoS eşikleri (label üretiminde kullandığınız eşikler)
QOS_L0 = 0.70
QOS_L1 = 0.58

def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x

def decide_level_basic(qos: float) -> str:
    if qos >= QOS_L0:
        return "L0"
    if qos >= QOS_L1:
        return "L1"
    return "L2"

def post_level(url: str, level: str):
    payload = json.dumps({"level": level}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=2) as r:
        r.read()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tx-url", default="", help="http://TX_PC_IP:8080/set_level (optional)")
    ap.add_argument("--dist", type=int, default=3, help="fallback dist_m if stream doesn't include it (1/3/5)")
    ap.add_argument("--min-dwell", type=float, default=15.0, help="min seconds between switches")
    ap.add_argument("--confirm-k", type=int, default=3, help="same decision must repeat K times to switch")
    ap.add_argument("--smooth-n", type=int, default=5, help="QoS moving average window size")
    args = ap.parse_args()

    dist_default = args.dist if args.dist in EXP_ADV else 3

    # Demo için normalize aralığı (istenirse dataset min/max ile daha doğru yapılır)
    rmin, rmax = -90.0, -55.0

    current = "L2"
    last_switch = time.time()
    pending = None
    pending_count = 0

    # QoS smoothing buffer
    qos_hist = deque(maxlen=max(1, args.smooth_n))

    # Enerji sayaçları
    sec_count = 0
    time_in = {"L0": 0, "L1": 0, "L2": 0}

    print("[RX] Expecting lines: ts,rssi_mean,adv_rate[,dist_m]")
    print("[RX] TX URL:", args.tx_url or "(disabled)")
    print("[RX] Dwell:", args.min_dwell, " confirm_k:", args.confirm_k, " smooth_n:", args.smooth_n)

    for line in sys.stdin:
        line = line.strip()
        if not line or line.lower().startswith("ts"):
            continue

        parts = line.split(",")
        if len(parts) < 3:
            continue

        ts = parts[0]
        try:
            rssi = float(parts[1])
            adv  = float(parts[2])
        except Exception:
            # format bozuk satır gelirse atla
            continue

        # dist_m varsa al
        dist = None
        if len(parts) >= 4:
            try:
                dist = int(float(parts[3]))
            except Exception:
                dist = None
        if dist not in EXP_ADV:
            dist = dist_default

        # QoS hesap
        packet_success = clamp01(adv / EXP_ADV[dist])
        rssi_norm = clamp01((rssi - rmin) / (rmax - rmin))
        qos = 0.7 * packet_success + 0.3 * rssi_norm

        # --- SMOOTHING ---
        qos_hist.append(qos)
        qos_smooth = sum(qos_hist) / len(qos_hist)

        # İlk karar (smooth QoS ile)
        decision = decide_level_basic(qos_smooth)

        # --- HYSTERESIS (zıplamayı azaltır) ---
        # 1) L0 -> L2 geçişini zorlaştır: QoS çok düşmedikçe L2'ye gitme
        #    (özellikle yakın mesafe veya genel olarak)
        if current == "L0" and decision == "L2":
            # "hard drop" şartı: qos_smooth 0.50 altına düşmedikçe L2'ye izin verme
            if qos_smooth >= 0.50:
                decision = "L1"  # en azından L1'e düş (daha yumuşak)
        # 2) L2 -> L0 geçişini kolaylaştır: QoS iyi ise direkt L0'a izin ver
        #    (zaten basic karar bunu yapar, burada ekstra yok)

        # Switch mantığı
        now = time.time()
        can_switch = (now - last_switch) >= args.min_dwell

        if decision != current and can_switch:
            if pending != decision:
                pending = decision
                pending_count = 1
            else:
                pending_count += 1

            if pending_count >= args.confirm_k:
                current = decision
                last_switch = now
                pending = None
                pending_count = 0

                sent = "no_tx"
                if args.tx_url:
                    try:
                        post_level(args.tx_url, current)
                        sent = "sent"
                    except Exception as e:
                        sent = f"send_fail({e})"

                print(f"\nSWITCH -> {current} ({sent})\n")

        # Enerji sayaç (1 satır ~ 1 saniye bucket varsayımı)
        time_in[current] += 1
        sec_count += 1

        avg_energy = (
            time_in["L0"]*0.2 + time_in["L1"]*0.4 + time_in["L2"]*0.6
        ) / max(1, sec_count)

        saving_vs_L2 = 1.0 - (avg_energy / 0.6)

        print(
            f"ts={ts} dist={dist} RSSI={rssi:6.1f} ADV={adv:4.0f} "
            f"QoS={qos:4.2f} QoS_s={qos_smooth:4.2f} "
            f"DEC={decision} CUR={current} "
            f"avgE={avg_energy:0.3f} save_vs_L2={saving_vs_L2*100:5.1f}% "
            f"time(L0,L1,L2)=({time_in['L0']},{time_in['L1']},{time_in['L2']})"
        )

if __name__ == "__main__":
    main()
