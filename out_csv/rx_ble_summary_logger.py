from network import Bluetooth
import time
import pycom
import os

TARGET_NAME = "Lopy_Server"
TOTAL_S = 90  # ölçüm süresi (sn)

# senaryo etiketleri
RX_ID     = "rx01"
ENV       = "indoor_open"
DIST_M    = 5
RUN_LEVEL = "L2"   # Bu run'ın etiketi (L0/L1/L2/L3) - garanti fallback

LOG_DIR  = "/flash/logs"
# Her level için ayrı dosya (karışmaz)
LOG_FILE = "{}/summary_{}_{}m_{}.csv".format(LOG_DIR, ENV, DIST_M, RUN_LEVEL)

pycom.heartbeat(False)
pycom.rgbled(0x7f0000)

bt = Bluetooth()
try:
    bt.init(antenna=Bluetooth.INT_ANT)
except:
    try:
        bt.init()
    except:
        pass


def ensure_dir(path):
    try:
        os.stat(path)
    except:
        os.mkdir(path)


def file_exists(path):
    try:
        os.stat(path)
        return True
    except:
        return False


ensure_dir(LOG_DIR)

if not file_exists(LOG_FILE):
    with open(LOG_FILE, "w") as f:
        f.write("ts,rx_id,env,dist_m,tx_level,rssi_mean,adv_rate\n")


# saniyelik bucket
bucket_s  = None
count     = 0
rssi_sum  = 0

# TX level otomatik okunacak (okunamazsa RUN_LEVEL kullanılacak)
current_lvl = ""


def parse_level_from_adv(adv_obj):
    """
    Manufacturer data örn: b'12345|L0'
    İçinden L0/L1/L2/L3 çekmeye çalışır.
    """
    try:
        mfg = bt.resolve_adv_data(adv_obj.data, Bluetooth.ADV_MANUFACTURER_DATA)
        if not mfg:
            return None

        s = mfg.decode("utf-8", errors="ignore")
        if "|" not in s:
            return None

        lvl = s.split("|")[-1]
        # null char temizle + strip
        lvl = lvl.replace("\x00", "").strip()

        if lvl in ("L0", "L1", "L2", "L3"):
            return lvl
        return None
    except:
        return None


def flush_bucket(ts_to_write):
    global count, rssi_sum, current_lvl

    if ts_to_write is None:
        return

    # tx_level: parse edilemezse RUN_LEVEL'e düş
    lvl_to_write = current_lvl if current_lvl else RUN_LEVEL

    if count > 0:
        rssi_mean = (rssi_sum / count)
    else:
        rssi_mean = ""

    adv_rate = count  # 1 saniyelik bucket -> count direkt rate

    with open(LOG_FILE, "a") as f:
        f.write("{},{},{},{},{},{},{}\n".format(
            ts_to_write, RX_ID, ENV, DIST_M, lvl_to_write, rssi_mean, adv_rate
        ))


def on_adv(e):
    global bucket_s, count, rssi_sum, current_lvl

    adv = bt.get_adv()
    if not adv:
        return

    # name filtresi
    name = bt.resolve_adv_data(adv.data, Bluetooth.ADV_NAME_CMPL)
    if name != TARGET_NAME:
        name2 = bt.resolve_adv_data(adv.data, Bluetooth.ADV_NAME_SHORT)
        if name2 != TARGET_NAME:
            return

    # level'i her pakette güncelle (varsa)
    lvl = parse_level_from_adv(adv)
    if lvl:
        current_lvl = lvl

    # rssi
    now_s = int(time.time())
    rssi = getattr(adv, "rssi", None)
    if rssi is None:
        return

    if bucket_s is None:
        bucket_s = now_s

    # saniye değiştiyse önceki bucket yaz
    if now_s != bucket_s:
        flush_bucket(bucket_s)
        bucket_s = now_s
        count = 0
        rssi_sum = 0

    count += 1
    rssi_sum += rssi


bt.callback(trigger=None, handler=None)
bt.callback(trigger=Bluetooth.NEW_ADV_EVENT, handler=on_adv)

start = time.time()
try:
    while time.time() - start < TOTAL_S:
        try:
            bt.start_scan(1000)  # 1s
        except:
            try:
                bt.stop_scan()
            except:
                pass
            time.sleep_ms(50)
            bt.start_scan(1000)

        time.sleep(1.05)
        try:
            bt.stop_scan()
        except:
            pass
        time.sleep(0.05)

finally:
    # son bucket flush
    try:
        flush_bucket(bucket_s)
    except:
        pass

    try:
        bt.stop_scan()
    except:
        pass

    pycom.rgbled(0x000000)
    print("done ->", LOG_FILE)
