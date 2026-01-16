from network import Bluetooth
import time
import pycom
TX_LEVEL = "L2"
TOTAL_S  = 999999  # demo

DUTY = {
    "L0": (2, 8),
    "L1": (4, 6),
    "L2": (6, 4),
    "L3": (9, 1),
}

on_s, off_s = DUTY.get(TX_LEVEL, (4, 6))

pycom.heartbeat(False)
pycom.rgbled(0x00007f)

bt = Bluetooth()
bt.advertise(False)

bt.set_advertisement(
    name='Lopy_Server',
    manufacturer_data=("12345|" + TX_LEVEL).encode(),
    service_uuid=b'1234567890123456'
)

print("TX duty started. LEVEL={} on={}s off={}s total={}s".format(TX_LEVEL, on_s, off_s, TOTAL_S))

start = time.time()
while (time.time() - start) < TOTAL_S:
    bt.advertise(True)
    pycom.rgbled(0x00007f)
    t0 = time.time()
    while time.time() - t0 < on_s and (time.time() - start) < TOTAL_S:
        time.sleep(0.2)

    bt.advertise(False)
    pycom.rgbled(0x000000)
    t1 = time.time()
    while time.time() - t1 < off_s and (time.time() - start) < TOTAL_S:
        time.sleep(0.2)

bt.advertise(False)
pycom.rgbled(0x000000)
print("TX finished.")
