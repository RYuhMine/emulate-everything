#!/usr/bin/env python3
"""

GNUv2.0 License. Made by RYuh

emu-v7-9.py — Unicorn-емуляція прошивки Beurer PO 80 (GD32F350, Cortex-M) + GUI на tkinter.

Запуск:   python emu-v7-9.py [flash.bin]
Без вікна: python emu-v7-9.py flash.bin --headless 6000 --shot screen.png   (6000 мс емульованого часу)

GUI: екран ST7789 240x240 (SPI1, D/C=PC6), кнопки (затискаються мишею або клавішами 1-4,
права кнопка миші = "залипання"), поворот екрана (R), пауза (Пробіл), масштаб (+/-),
швидкість, скріншот (S), ползунок значення АЦП, UART-лог і пін-и, які прошивка опитує.

НОВЕ у v3 — емуляція САМИХ ДАТЧИКІВ (прошивка сама обробляє сигнал і сама малює результат):
  • оптичний датчик: LED червоний/ІЧ (PC2/PC3) + фотодіод → перетворювач «світло→частота» на вході TIMER0 CH0,
    DMA пише часові мітки фронтів у буфер; прошивка рахує частоту, відфільтровує пульсову хвилю, рахує SpO2/PR;
  • батарея: АЦП (результат конверсії по IRQ12), прошивка сама вирішує, який значок показати;
  • час: живий RTC (BCD-регістри TIME/DATE), іде від емульованого часу;
  • звук: ШІМ TIMER2 CH0 → піщалка (sounddevice | winsound | aplay/paplay/afplay) або запис у --wav.
  SIMSCRIPT="20000:bat=3.5;30000:spo2=90,finger=0"  — зміна параметрів у заданий момент (мс емульованого часу).

НОВЕ у v4 — ПАМ'ЯТЬ ТА СТАН:
  • SRAM = 16 КБ, як у справжнього GD32F350RBT6 (адреси вище 0x20004000 мапляться «про запас», але перший доступ туди друкується як попередження);
  • повний знімок стану (--state FILE): CPU, SRAM, периферія, екран, RTC, датчики, батарея; GUI: «Зберегти/Завантажити стан», F5 / F9 — швидке збереження;
  • сирий дамп SRAM (--sram-dump FILE, --sram-load FILE) та кнопки в GUI; переглядач SRAM з підсвіткою змінених байтів.

НОВЕ у v5 — USB (перехоплення виводу пристрою):
  • емулюється периферія USBFS (GD32 OTG-FS у режимі пристрою, IRQ 67) і віртуальний «комп'ютер» на кінці кабелю:
    ресет шини → енумерація (дескриптори, SET_ADDRESS, SET_CONFIGURATION, HID-звіт) → той самий обмін, що в hid_pulse_oximeter
    (HID-звіти по 64 байти: init, модель, ім'я користувача, час, налаштування, keep-alive; у відповідь пристрій шле SpO2/PR);
  • усе, що пристрій надсилає й отримує по USB, пишеться в USB-журнал під екраном (GUI) — з розшифровкою (PR, SpO2, модель…);
  • --no-usb — не підключати віртуальний ПК;  --usb-log FILE — записати USB-журнал у файл при виході ('-' = у консоль);
  • у GUI: перемикач «кабель USB» (відключити/підключити з новою енумерацією), «повні пакети», «Очистити», «Зберегти…».

НОВЕ у v6 — пристрій тепер ВІДПОВІДАЄ по USB (причини, чому у v5 не було жодного IN-пакета):
  1) USB-переривання виникає ОДРАЗУ після запису в регістр USBFS (EPENA у DIEPCTLn), як у залізі: usbd_ep_send кладе кадр
     у буфер на стеку й повертається, а у FIFO його копіює ISR за TXFE. Якщо ISR запізнився — стек перезаписано (сміття у пакеті).
  2) TXFE — рівень (FIFO ендпойнта порожній), а не «завжди 1» (інакше шторм переривань).
  3) Віртуальний ПК чекає, поки прошивка дійде до головного циклу (0x08017494, ≈1.8 с) — раніше команди 0x81/0x8E/... приходили
     до того, як хтось читав кільцевий буфер, і він переповнювався.
  4) Відповіді пристрою — кадри [cmd][...][CRC], кілька кадрів можуть іти в одному 64-байтному звіті.

НОВЕ у v7 — перевірено запуском (unicorn 2.1.4), виправлено формат кадрів:
  • CRC кадру = (сума попередніх байтів) & 0x7F (7-бітна!). Довжини: F0 → 2 (відповідь на 0x80), F1 → 10, FE → 10, EB 00 → 6, EB 01 → 8.
  • EB 00 = потік плетизмограми [хвиля 0..127][стовпчик = хвиля>>3], біт 6 байта 2 = удар пульсу (♥); EB 01 = [прапори][PR][SpO2][PI?][0].
  • потік EB стартує лише після команди 9B 00 1B; 0x83 (встановлення часу) прошивка приймає, але годинник не змінює.
  • перед кожною відповіддю прошивка сама шле ZLP (hid_send спершу запускає передачу з 0 байт) — це не артефакт емулятора.
  • GUI: чекбокс «хвиля/ZLP» ховає службовий потік; після «Завантажити стан» застарілий пакет з SRAM відкидається;
    bus_reset скидає DIEPFEINTEN.

НОВЕ у v7.5 — звук: запасний бекенд (winsound/aplay) більше не показує «помилку» про відсутній sounddevice; FMC: стирання/запис flash за галочкою «Дозволити запис у flash»
  (--flash-write, --flash-out); «Перезапуск прошивки» скидає лише прошивку (поточний або оригінальний flash — на вибір), повний перезапуск програми лишився окремою кнопкою;
  «Редактор пам'яті»: перегляд і запис SRAM/Flash наживо (hex або "текст", «тримати значення»).
  «Швидкість» справді працює (пропуск очікування SysTick); запис прошивкою в RTC (час/дата, напр. 2027) тепер приймається; мова інтерфейсу: English (за замовчуванням) / Українська (--lang en|uk, перемикач 🌐 у GUI).
НОВЕ у v7.2 — ЗВУК: на Windows без sounddevice winsound кидав RuntimeError (SND_MEMORY+SND_ASYNC) і помилка ковталась → тепер WAV-файл (SND_FILENAME);
  короткі сигнали (100 мс) на aplay/afplay/winsound не обриваються раніше 0.12 с; «вимкнути звук» справді зупиняє; помилки звуку видно в GUI; кнопка «Тест звуку».

НОВЕ у v7.3 — ІНТЕРФЕЙС: довгі рядки (UART, повідомлення) переносяться на новий рядок, а не розтягують колонку й не виштовхують панель датчиків;
  кнопки: [1] PB5, [2] PB6 «Зарядка» (затиснути й підняти заряд — прошивка бачить зарядку),
  [3] PB7 «Режим при старті» (діє лише якщо затиснута ДО запуску: інша гілка ініціалізації, «Low power»). PB9 — не кнопка, а лінія даних
  програмного послідовного обміну (PB8 = такт), яку прошивка читає лише на старті, тож кнопку прибрано.

НОВЕ у v7.4 — UART-ЖУРНАЛ (як USB-журнал) у середній колонці під статусом: час, hex, ASCII, відмітка «CRC7 ✓» для кадрів пристрою
  (CRC = сума попередніх байтів & 0x7F), автопрокрутка, «Очистити», «Зберегти…». Байти TX групуються в пачки (пауза > 30 мс).

Змінні середовища (як у emu.py): KEYLOW=пін@старт-кінець(мс),...  ADC=0xB00  IRQS=15,19  DBG=1
Нові:  BTNS="5:Кнопка,6:Зарядка,7:Режим при старті"  — які піни порту B показувати кнопками (за замовчуванням саме ці)
       IDLEHI="5"                           — піни, у яких спокій = 1, натиск = 0
"""
import pickle, zlib
import sys, os, struct, collections, time, argparse, math, random, datetime, wave, shutil, subprocess, tempfile, threading
from unicorn import *
from unicorn.arm_const import *

# ================================================================= I18N / Мова інтерфейсу (за замовчуванням — англійська)
# Ключі словника EN — оригінальні українські рядки; T(s) повертає переклад для LANG='en' і сам рядок для 'uk'.
_LANG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'po80_emu_lang.txt')
def _init_lang():
    for _i, _a in enumerate(sys.argv):
        if _a == '--lang' and _i + 1 < len(sys.argv): return sys.argv[_i + 1]
        if _a.startswith('--lang='): return _a[7:]
    try: return open(_LANG_FILE, encoding='utf-8').read().strip()          # остання обрана в GUI мова
    except Exception: return 'en'
LANG = _init_lang()
if LANG not in ('en', 'uk'): LANG = 'en'
EN = {
    '\nпомилка: ': '\nerror: ',
    '\nпрошивка опитує: {0}': '\nfirmware polls: {0}',
    '  (змінено)': '  (modified)',
    ' (flash змінено напряму, минаючи FMC)': ' (flash modified directly, bypassing the FMC)',
    '(--headless) в кінці записати сирий дамп SRAM (16 КБ)': '(--headless) write a raw SRAM dump (16 KB) at the end',
    '(--headless) записати звук піщалки у WAV': '(--headless) write the beeper sound to a WAV file',
    '(--headless) у кінці зберегти поточний образ flash (128 КБ) у файл': '(--headless) save the current flash image (128 KB) to a file at the end',
    '(t={0} мс)': '(t={0} ms)',
    ', відхилено: %d': ', rejected: %d',
    ', змінений': ', modified',
    '--- USB-журнал ---': '--- USB log ---',
    'Beurer PO 80 — емулятор прошивки': 'Beurer PO 80 — firmware emulator',
    'Config: %d Б, HID report %d Б, EP IN %d / OUT %d, пакет %d Б': 'Config: %d B, HID report %d B, EP IN %d / OUT %d, packet %d B',
    'Device: VID:PID=%04X:%04X, bcdUSB=%X.%02X, EP0=%d Б': 'Device: VID:PID=%04X:%04X, bcdUSB=%X.%02X, EP0=%d B',
    'EB-запис тип %d, дані %s': 'EB record type %d, data %s',
    'F5: збережено quicksave.po80state (t={0:.1f} с)': 'F5: saved quicksave.po80state (t={0:.1f} s)',
    'F9: завантажено quicksave.po80state': 'F9: loaded quicksave.po80state',
    'HID Report descriptor: %d Б  %s': 'HID Report descriptor: %d B  %s',
    'PR=%s уд/хв  SpO2=%s  (прапори %02X)': 'PR=%s bpm  SpO2=%s  (flags %02X)',
    'SET_IDLE не підтримується (нормально)': 'SET_IDLE not supported (normal)',
    'SRAM ({0} КБ) → {1}': 'SRAM ({0} KB) → {1}',
    'SRAM завантажено, байт:': 'SRAM loaded, bytes:',
    'SRAM збережено:': 'SRAM saved:',
    'SRAM → файл .bin': 'SRAM → .bin file',
    'SpO2 пацієнта, %% (40-100)': 'patient SpO2, %% (40-100)',
    'TX: 0 Б': 'TX: 0 B',
    'TX: {0} Б': 'TX: {0} B',
    'UART-журнал': 'UART log',
    'UART-журнал збережено: ': 'UART log saved: ',
    'USB-журнал': 'USB log',
    'USB-журнал збережено: ': 'USB log saved: ',
    'USB-журнал:': 'USB log:',
    'USB: %s — немає статус-фази': 'USB: %s — no status phase',
    'USB: %s — пристрій не відповів': 'USB: %s — device did not respond',
    'USB: Full-Speed, енумерація': 'USB: Full-Speed, enumeration',
    'USB: відкинуто застарілий пакет після завантаження стану (%d Б, артефакт відновлення SRAM)': 'USB: dropped a stale packet after loading state (%d B, SRAM restore artifact)',
    'USB: головний цикл прошивки ожив (t=%.3f с)': 'USB: firmware main loop is alive (t=%.3f s)',
    'USB: головний цикл прошивки так і не запустився — продовжую': 'USB: firmware main loop never started — continuing',
    'USB: енумерація не вдалася, хост здався': 'USB: enumeration failed, host gave up',
    'USB: кабель відключено': 'USB: cable unplugged',
    'USB: кабель підключено': 'USB: cable plugged in',
    'USB: немає відповіді на 0x%02X — повторюю запит': 'USB: no response to 0x%02X — retrying',
    'USB: повтор енумерації…': 'USB: retrying enumeration…',
    'USB: пристрій налаштовано — обмін HID-звітами': 'USB: device configured — exchanging HID reports',
    'USB: прошивка не обробила ENUMF': 'USB: firmware did not handle ENUMF',
    'USB: прошивка не обробила USBRST': 'USB: firmware did not handle USBRST',
    'USB: ресет шини': 'USB: bus reset',
    'USB: стан завантажено — перепідключення': 'USB: state loaded — reconnecting',
    'USB: хост {0}; пакетів ПК→пристрій {1}, пристрій→ПК {2}, керуючих передач {3}; останні дані: {4}': 'USB: host {0}; packets PC→device {1}, device→PC {2}, control transfers {3}; last data: {4}',
    'USB: чекаю, поки прошивка дійде до головного циклу…': 'USB: waiting for the firmware to reach the main loop…',
    '[!] USB-журнал не збережено:': '[!] USB log not saved:',
    '[!] доступ поза 16 КБ SRAM справжнього чипа @ {0:#x} pc={1:#x} (далі мовчки)': "[!] access outside the real chip's 16 KB SRAM @ {0:#x} pc={1:#x} (silent from now on)",
    '[!] не вдалося завантажити стан:': '[!] could not load state:',
    '[!] стан не збережено:': '[!] state not saved:',
    'autoshot.png, t=%d мс': 'autoshot.png, t=%d ms',
    'flash збережено:': 'flash saved:',
    'flash збережено: ': 'flash saved: ',
    'flash: дозвіл={0} стирань={1} записів(півслів)={2} відхилено={3}': 'flash: allowed={0} erases={1} writes(halfwords)={2} rejected={3}',
    'init підтверджено': 'init acknowledged',
    't={0:7.2f} с   PC={1:08X}\nLCD: {2} ком., MADCTL={3:02X}, поворот {4}°\nRTC {5:%H:%M:%S}   ': 't={0:7.2f} s   PC={1:08X}\nLCD: {2} cmds, MADCTL={3:02X}, rotation {4}°\nRTC {5:%H:%M:%S}   ',
    '{0} байт записано в SRAM (прошивка бачить зміни одразу)': '{0} bytes written to SRAM (the firmware sees the changes immediately)',
    'АЦП={0}  рівень: {1}': 'ADC={0}  level: {1}',
    'Батарея, В (оцінка за дільником 1:2)': 'Battery, V (estimated from the 1:2 divider)',
    'Варіабельність ритму': 'Rhythm variability',
    'Встановити': 'Set',
    'Віртуальний кабель: вимкнено → шина тиха (suspend); увімкнено → ресет шини й енумерація з нуля.': 'Virtual cable: off → bus is quiet (suspend); on → bus reset and enumeration from scratch.',
    'Годинник RTC (ГГ:ХХ:СС)': 'RTC clock (HH:MM:SS)',
    'ДАТЧИКИ (прошивка сама обробляє сигнал)': 'SENSORS (the firmware processes the signal itself)',
    'Дамп SRAM': 'SRAM dump',
    'Записати': 'Write',
    'Зарядка': 'Charger',
    'Зберегти образ flash': 'Save flash image',
    'Зберегти…': 'Save…',
    'Йти': 'Go',
    'Кнопка': 'Button',
    'Кнопки (ЛКМ — тримати, ПКМ — залипання)': 'Buttons (left click — hold, right click — latch)',
    'Макс': 'Max',
    'Низька': 'Low',
    'Очистити': 'Clear',
    "ПАМ'ЯТЬ І СТАН": 'MEMORY & STATE',
    'ПК → Пристрій  %s   [%s%s]': 'PC → Device  %s   [%s%s]',
    'ПК → Пристрій  EP%d NAK: пристрій не готовий приймати (%s)': 'PC → Device  EP%d NAK: device not ready to receive (%s)',
    'Перфузія (розмах хвилі), %': 'Perfusion (wave amplitude), %',
    'Повна': 'Full',
    'Пристрій → ПК  %s   [%s]': 'Device → PC  %s   [%s]',
    'Пристрій → ПК  EP%d  ZLP': 'Device → PC  EP%d  ZLP',
    'Прошивка перечитує RTC раз на ~60 с (як на реальному пристрої)': 'The firmware re-reads the RTC about once per 60 s (like the real device)',
    'Пульс, уд/хв': 'Pulse, bpm',
    'РОЗРЯД — прошивка вимикає екран': 'DISCHARGED — the firmware turns the screen off',
    "Редактор пам'яті (SRAM / Flash) — наживо": 'Memory editor (SRAM / Flash) — live',
    "Редактор пам'яті — ": 'Memory editor — ',
    'Режим при старті': 'Boot mode',
    'Розряд': 'Empty',
    'Рядки: виробник %r, виріб %r, серійний %r': 'Strings: manufacturer %r, product %r, serial %r',
    'Середня': 'Medium',
    'Стан емулятора': 'Emulator state',
    'Текст': 'Text',
    'Усі': 'All',
    'Усі файли': 'All files',
    'Файл .bin → SRAM': '.bin file → SRAM',
    'Час ПК': 'PC time',
    'Швидкість:': 'Speed:',
    'Шум / рух, %': 'Noise / motion, %',
    'автооновлення': 'auto-refresh',
    'автопрокрутка': 'auto-scroll',
    'адреса:': 'address:',
    'активний': 'active',
    'без вікна: прогнати MS мс і зберегти знімок': 'no window: run MS ms and save a screenshot',
    'вимкнути звук': 'mute the sound',
    'встановити час': 'set time',
    'відключено': 'disconnected',
    'годинник RTC: {0:%H:%M:%S}   АЦП батареї={1} ({2:.2f} В) → рівень {3}': 'RTC clock: {0:%H:%M:%S}   battery ADC={1} ({2:.2f} V) → level {3}',
    'датчики: SpO2={0:.0f}% PR={1:.0f} PI={2:.1f}% палець={3}  |  RAM прошивки: SpO2={4}': 'sensors: SpO2={0:.0f}% PR={1:.0f} PI={2:.1f}% finger={3}  |  firmware RAM: SpO2={4}',
    'дозволити прошивці стирати/писати flash (FMC); без цього запис ігнорується': 'allow the firmware to erase/write flash (FMC); otherwise writes are ignored',
    'емульовано {0} мс, LCD-команд {1}, UART: {2!r}': 'emulated {0} ms, LCD commands {1}, UART: {2!r}',
    'енумерація': 'enumeration',
    'запис: %d півслів, стирань: %d%s%s': 'written: %d halfwords, erases: %d%s%s',
    'записано %d байт @ %08X%s': 'wrote %d bytes @ %08X%s',
    "записати USB-журнал у файл при виході ('-' = надрукувати)": "write the USB log to a file on exit ('-' = print)",
    'запит моделі': 'model query',
    'запит імені користувача': 'user name query',
    'запустити оригінальний flash.bin': 'run the original flash.bin',
    'запустити поточний flash (з моїми змінами)': 'run the current flash (with my changes)',
    'збережено ': 'saved ',
    'звук:': 'sound:',
    'звуковий бекенд: ': 'sound backend: ',
    'знімок стану: завантажити при старті (якщо є) і зберегти при виході': 'state snapshot: load on start (if it exists) and save on exit',
    'знімок:': 'screenshot:',
    'кабель USB': 'USB cable',
    'кадр 0x%02X': 'frame 0x%02X',
    'клік по байту — підставити адресу й поточне значення; Enter — записати': 'click a byte to fill in its address and current value; Enter — write',
    'команда 0x%02X': 'command 0x%02X',
    'масштаб екрана (1-4)': 'screen scale (1-4)',
    'модель %r': 'model %r',
    'налаштування': 'settings',
    'напруга батареї, В (оцінка за дільником)': 'battery voltage, V (estimated from the divider)',
    'не пропускати очікування SysTick (delay_ms) — повільніше, але кожна мс виконує повні 8000 інструкцій': 'do not skip SysTick waits (delay_ms) — slower, but every ms runs the full 8000 instructions',
    'не підключати віртуальний USB-хост (ПК)': 'do not attach the virtual USB host (PC)',
    'немає (pip install sounddevice)': 'none (pip install sounddevice)',
    'нові байти (hex: DE AD BE EF   або   "текст"):': 'new bytes (hex: DE AD BE EF   or   "text"):',
    'опитувані піни PB:': 'polled PB pins:',
    'оригінальний': 'original',
    'очікування пристрою': 'waiting for device',
    'палець не вставлено': 'no finger inserted',
    'перейти до адреси:': 'go to address:',
    'перфузійний індекс (розмах пульсової хвилі), %%': 'perfusion index (pulse wave amplitude), %%',
    'повна (3)': 'full (3)',
    'повні пакети': 'full packets',
    'повтор': 'retry',
    'поза SRAM (0x20000000–0x20003FFF)': 'outside SRAM (0x20000000–0x20003FFF)',
    'поза flash (0x08000000–0x0801FFFF)': 'outside flash (0x08000000–0x0801FFFF)',
    'помилка': 'error',
    'помилка енумерації': 'enumeration error',
    'помилка: %s': 'error: %s',
    'помилка: {0}': 'error: {0}',
    'порожнє значення': 'empty value',
    'порожній звіт': 'empty report',
    'поточний': 'current',
    'початковий поворот екрана: 0-3 (×90° проти год. стрілки)': 'initial screen rotation: 0-3 (×90° counter-clockwise)',
    'початковий час RTC HH:MM[:SS] (за замовчуванням — годинник ПК)': 'initial RTC time HH:MM[:SS] (default: PC clock)',
    'прошивку перезапущено (flash: %s)': 'firmware restarted (flash: %s)',
    'пульс, уд/хв': 'pulse, bpm',
    'після старту записати сирий дамп у SRAM': 'after start, write a raw dump into SRAM',
    'піщалка: {0} сигналів': 'beeper: {0} beeps',
    'скріншот не вдався: {0}': 'screenshot failed: {0}',
    'стан завантажено:': 'state loaded:',
    'стан завантажено: ': 'state loaded: ',
    'стан збережено для іншої прошивки': 'the state was saved for a different firmware',
    'стан збережено:': 'state saved:',
    'стан збережено: ': 'state saved: ',
    'тримати значення (SRAM)': 'hold value (SRAM)',
    'файл знімка для --headless': 'screenshot file for --headless',
    'формат часу: ГГ:ХХ:СС': 'time format: HH:MM:SS',
    'хвиля %d, стовпчик %d%s': 'wave %d, column %d%s',
    'хвиля/ZLP': 'wave/ZLP',
    'це не файл стану цього емулятора': 'this is not a state file of this emulator',
    'час встановлено; екран оновить його при наступному читанні RTC (≤ 60 с)': 'time set; the screen will pick it up on the next RTC read (≤ 60 s)',
    'шум/рух, 0-100 %%': 'noise/motion, 0-100 %%',
    "ім'я користувача %r": 'user name %r',
    '↺ Перезапуск прошивки': '↺ Restart firmware',
    '⏸ Пауза (Пробіл)': '⏸ Pause (Space)',
    '▶ Продовжити (Пробіл)': '▶ Resume (Space)',
    '☝ Палець у датчику': '☝ Finger in sensor',
    '♪ {0:.0f} Гц, заповн. {1:.0f}%': '♪ {0:.0f} Hz, duty {1:.0f}%',
    '✏ Дозволити запис у flash': '✏ Allow flash writes',
    '⟳ Перезапуск програми (повний)': '⟳ Restart the program (full)',
    '⟳ Повернути екран (R)': '⟳ Rotate screen (R)',
    '🌐': '🌐',
    '💾 flash → файл…': '💾 flash → file…',
    '💾 Зберегти стан (F5 — швидко)': '💾 Save state (F5 — quick)',
    '📂 Завантажити стан (F9 — швидко)': '📂 Load state (F9 — quick)',
    '📷 Скріншот (S)': '📷 Screenshot (S)',
    '🔊 Звук піщалки': '🔊 Beeper sound',
    '🔔 Тест звуку (2500 Гц)': '🔔 Sound test (2500 Hz)',
    "🧠 Редактор пам'яті (SRAM / Flash)": '🧠 Memory editor (SRAM / Flash)',
}
REV = {v: k for k, v in EN.items()}                    # англ. текст → український ключ (для перемикання мови «наживо»)
def T(s): return EN.get(s, s) if LANG == 'en' else s
def set_lang(l):
    global LANG
    LANG = l
    try: open(_LANG_FILE, 'w', encoding='utf-8').write(l)
    except Exception: pass

ap = argparse.ArgumentParser(description=__doc__ if LANG == 'uk' else 'Unicorn-based emulation of the Beurer PO 80 pulse-oximeter firmware (flash.bin): LCD, USB HID, UART, beeper, sensors, flash/SRAM editing.',
                             formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--lang', choices=['en', 'uk'], help='interface language / мова інтерфейсу (default: en; the GUI remembers the last choice)')
ap.add_argument('fw', nargs='?', default='flash.bin')
ap.add_argument('--headless', type=int, metavar='MS', help=T('без вікна: прогнати MS мс і зберегти знімок'))
ap.add_argument('--shot', default='screen.png', help=T('файл знімка для --headless'))
ap.add_argument('--scale', type=int, default=2, help=T('масштаб екрана (1-4)'))
ap.add_argument('--rot', type=int, default=1, help=T('початковий поворот екрана: 0-3 (×90° проти год. стрілки)'))
ap.add_argument('--spo2', type=float, default=98.0, help=T('SpO2 пацієнта, %% (40-100)'))
ap.add_argument('--pr', type=float, default=75.0, help=T('пульс, уд/хв'))
ap.add_argument('--pi', type=float, default=3.0, help=T('перфузійний індекс (розмах пульсової хвилі), %%'))
ap.add_argument('--noise', type=float, default=0.0, help=T('шум/рух, 0-100 %%'))
ap.add_argument('--nofinger', action='store_true', help=T('палець не вставлено'))
ap.add_argument('--bat', type=float, default=4.2, help=T('напруга батареї, В (оцінка за дільником)'))
ap.add_argument('--time', help=T('початковий час RTC HH:MM[:SS] (за замовчуванням — годинник ПК)'))
ap.add_argument('--wav', help=T('(--headless) записати звук піщалки у WAV'))
ap.add_argument('--mute', action='store_true', help=T('вимкнути звук'))
ap.add_argument('--state', metavar='FILE', help=T('знімок стану: завантажити при старті (якщо є) і зберегти при виході'))
ap.add_argument('--sram-dump', metavar='FILE', help=T('(--headless) в кінці записати сирий дамп SRAM (16 КБ)'))
ap.add_argument('--sram-load', metavar='FILE', help=T('після старту записати сирий дамп у SRAM'))
ap.add_argument('--flash-write', action='store_true', help=T('дозволити прошивці стирати/писати flash (FMC); без цього запис ігнорується'))
ap.add_argument('--flash-out', metavar='FILE', help=T('(--headless) у кінці зберегти поточний образ flash (128 КБ) у файл'))
ap.add_argument('--no-idle-skip', action='store_true', help=T('не пропускати очікування SysTick (delay_ms) — повільніше, але кожна мс виконує повні 8000 інструкцій'))
ap.add_argument('--no-usb', action='store_true', help=T('не підключати віртуальний USB-хост (ПК)'))
ap.add_argument('--usb-log', metavar='FILE', help=T("записати USB-журнал у файл при виході ('-' = надрукувати)"))
ap.add_argument('--autoquit', type=float, help=argparse.SUPPRESS)   # для автотесту GUI
args = ap.parse_args()

FW = args.fw
fw = open(FW, 'rb').read()
FLASH = 0x08000000

KEYS = []   # скриптові натиски: KEYLOW=6@12000-12100,5@14000-14100
for _k in os.environ.get('KEYLOW', '').split(','):
    if _k:
        _p, _t = _k.split('@'); _a, _b = _t.split('-'); KEYS.append((int(_p), int(_a), int(_b)))
BAT_VREF = float(os.environ.get('BATVREF', '3.2'))      # припущення: опорна напруга АЦП, В
BAT_DIV = float(os.environ.get('BATDIV', '2.0'))        # припущення: дільник напруги батареї 1:2
def volts_to_adc(v): return max(0, min(4095, int(round(v / (BAT_VREF * BAT_DIV) * 4095))))
def adc_to_volts(a): return a / 4095.0 * BAT_VREF * BAT_DIV
BAT_LEVELS = [(0xA66, 'повна (3)'), (0x9DE, '2'), (0x955, '1'), (0x8CD, '0'), (0, 'РОЗРЯД — прошивка вимикає екран')]   # пороги з прошивки
def bat_level(a): return next(n for t, n in BAT_LEVELS if a >= t)
ADC_VAL = [int(os.environ['ADC'], 0) if os.environ.get('ADC') else volts_to_adc(args.bat)]
IDLEHI = 0
for _p in os.environ.get('IDLEHI', '').split(','):
    if _p.strip(): IDLEHI |= 1 << int(_p)
# кнопки GUI: за замовчуванням — піни порту B, які прошивка опитує через GPIO_ReadBit
BTNS = []
for _b in os.environ.get('BTNS', '5:Кнопка,6:Зарядка,7:Режим при старті').split(','):
    _p, _, _n = _b.partition(':'); BTNS.append((int(_p), _n or 'PB' + _p))

# ------------------------------------------------------------------ Unicorn
uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
uc.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M3) if hasattr(uc, 'ctl_set_cpu_model') else None
uc.mem_map(FLASH, 0x20000); uc.mem_write(FLASH, fw)
uc.mem_map(0x0, 0x20000);   uc.mem_write(0x0, fw)          # alias flash @0
uc.mem_map(0x20000000, 0x10000)                            # SRAM 64K
uc.mem_map(0x0F000000, 0x1000); uc.mem_write(0x0F000000, b'\x00\xbf' * 8)  # EXC_RETURN trampoline
uc.mem_map(0x1FFFF000, 0x1000)                             # system memory / UID

regs = collections.defaultdict(int)       # readback-регістри периферії
uart = bytearray()
uart_pending = collections.deque(maxlen=100000)      # (мс емульованого часу, байт) — для UART-журналу в GUI
odr = collections.defaultdict(int)
polled = collections.Counter()            # які піни порту B опитує прошивка
held, latched = set(), set()              # натиснуті з GUI
cnt = [0, -1]                             # [мс емульованого часу, службове для SysTick]

def pressed_mask():
    ms = cnt[0]; m = 0
    for p in held | latched: m |= 1 << p
    for pin, a, b in KEYS:
        if a <= ms < b: m |= 1 << pin
    return m

# ---------------------------------------------------------- ST7789 (SPI1, D/C = PC6, RGB565)
LW, LH = 240, 240
BLACK = b'\x00\x00\x00'
RGB565 = [bytes(((c >> 11) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31)) for c in range(65536)]

class LCD:
    def __init__(s):
        s.rows = [[BLACK] * LW for _ in range(LH)]
        s.cmd = None; s.params = []; s.pend = None
        s.x0 = s.y0 = 0; s.x1 = LW - 1; s.y1 = LH - 1; s.cx = s.cy = 0
        s.madctl = 0; s.ncmd = 0; s.dirty = True

    def byte(s, val):
        if not (odr[0x48000800] >> 6) & 1:                 # D/C=0 → команда
            s.cmd = val; s.params = []; s.ncmd += 1
            if val == 0x2C: s.cx, s.cy, s.pend = s.x0, s.y0, None
            return
        if s.cmd == 0x2C:                                  # RAMWR: 2 байти на піксель
            if s.pend is None: s.pend = val; return
            c = (s.pend << 8) | val; s.pend = None
            px, py = (s.cy, s.cx) if s.madctl & 0x20 else (s.cx, s.cy)
            if s.madctl & 0x40: px = LW - 1 - px
            if s.madctl & 0x80: py = LH - 1 - py
            if 0 <= px < LW and 0 <= py < LH: s.rows[py][px] = RGB565[c]
            s.cx += 1
            if s.cx > s.x1: s.cx = s.x0; s.cy += 1
            if s.cy > s.y1: s.cy = s.y0
            s.dirty = True
        else:
            s.params.append(val); p = s.params
            if s.cmd == 0x2A and len(p) == 4: s.x0 = (p[0] << 8) | p[1]; s.x1 = (p[2] << 8) | p[3]
            if s.cmd == 0x2B and len(p) == 4: s.y0 = (p[0] << 8) | p[1]; s.y1 = (p[2] << 8) | p[3]
            if s.cmd == 0x36 and p: s.madctl = p[0]

lcd = LCD()

def rotated_rows(rot):
    rows = lcd.rows; r = rot % 4
    if r == 1: return list(zip(*rows))[::-1]               # 90° проти год. стрілки
    if r == 2: return [row[::-1] for row in rows[::-1]]    # 180°
    if r == 3: return list(zip(*rows[::-1]))               # 90° за год. стрілкою
    return rows

def ppm(rot):
    return b'P6 %d %d 255\n' % (LW, LH) + b''.join(b''.join(row) for row in rotated_rows(rot))


# ======================================================================= МОДЕЛІ ДАТЧИКІВ
TIMER_HZ = 8e6           # TIMER0: 48 МГц / (PSC+1=6)
WIN = 6000 / 8e6         # вікно захоплення = TIMER13 (ARR 6000, той самий дільник)
# калібрування «відношення відношень» R = (ACчерв/DCчерв)/(ACІЧ/DCІЧ) → SpO2, що показує ця прошивка (виміряно на емуляції)
SPO2_R = [(100, 0.43), (99, 0.50), (98, 0.55), (95, 0.65), (91, 0.75), (88, 0.85), (85, 0.95), (81, 1.05), (75, 1.20),
          (69, 1.35), (63, 1.50), (55, 1.70), (48, 1.90), (40, 2.20)]
def spo2_to_R(s):
    s = max(40.0, min(100.0, s))
    for (s1, r1), (s2, r2) in zip(SPO2_R, SPO2_R[1:]):
        if s2 <= s <= s1: return r2 + (r1 - r2) * (s - s2) / (s1 - s2) if s1 != s2 else r1
    return SPO2_R[-1][1]

class Sensor:
    """Фізична модель пальцевого датчика: на виході — частота імпульсів (Гц) для кожної фази LED."""
    DC_RED, DC_IR, DC_OPEN, AMB = 150000.0, 120000.0, 520000.0, 20000.0   # Гц; без пальця — засвітка > 400 кГц
    def __init__(s, a):
        s.finger = not a.nofinger; s.spo2 = a.spo2; s.pr = a.pr; s.pi = a.pi; s.noise = a.noise; s.hrv = False
        s.ph = 0.0; s.t_prev = 0.0; s.drift = 0.0
    @staticmethod
    def _g(x, m, sg): return math.exp(-0.5 * ((x - m) / sg) ** 2)
    def _raw(s, x): return s._g(x, 0.17, 0.07) + 0.45 * s._g(x, 0.50, 0.10)      # систола + діастолічний горб
    def ppg(s, t):
        dt = t - s.t_prev; s.t_prev = t
        if 0 < dt < 0.2:
            hr = s.pr * (1 + (0.04 * math.sin(2 * math.pi * 0.25 * t) if s.hrv else 0))
            s.ph = (s.ph + dt * hr / 60.0) % 1.0
            s.drift = s.drift * 0.995 + random.gauss(0, 1) * 0.0008 * s.noise / 10.0
        return (s._raw(s.ph) - s.RMIN) / (s.RMAX - s.RMIN) - 0.5       # розмах рівно 1
    def freq(s, led, t):          # led: 'R' | 'I' | None
        f = s.AMB * (1 + random.gauss(0, 0.003))
        if led is None: return f
        if not s.finger: return f + s.DC_OPEN
        R = spo2_to_R(s.spo2); pi = max(0.0, s.pi) / 100.0
        m = pi * R if led == 'R' else pi                     # частка змінної складової (розмах/DC)
        dc = s.DC_RED if led == 'R' else s.DC_IR
        p = s.ppg(t)
        nz = random.gauss(0, 1) * s.noise / 100.0 * 0.25 * max(pi, 0.01)
        return f + dc * (1 - m * p + nz + s.drift * (1 if led == 'R' else 0.9))
_s = Sensor.__new__(Sensor)
Sensor.RMIN = min(Sensor._raw(_s, i / 400) for i in range(400)); Sensor.RMAX = max(Sensor._raw(_s, i / 400) for i in range(400))
sensor = Sensor(args)
capt = {'t': random.random() * 65536, 'n': collections.Counter()}

def led_state():
    o = odr[0x48000800]            # PC2 = червоний, PC3 = ІЧ (обидва вимкнені — фон)
    return 'R' if (o & 4 and not o & 8) else ('I' if (o & 8 and not o & 4) else None)

def dma_capture():
    """DMA CH1: TIMER0 CH0CV → буфер. Генеруємо часові мітки фронтів на вікно WIN."""
    cntv = regs[0x40020020]; maddr = regs[0x40020028]
    f = max(1.0, sensor.freq(led_state(), cnt[0] / 1000.0))
    n = min(cntv, int(f * WIN)); step = TIMER_HZ / f
    t = capt['t'] + random.random() * step
    vals = [int(t + i * step) & 0xFFFF for i in range(n)]
    capt['t'] = (t + n * step + 40) % 65536
    if n: uc.mem_write(maddr, struct.pack('<%dH' % n, *vals))
    regs[0x40020020] = cntv - n

# ---- RTC (GD32F3x0: TIME 0x00, DATE 0x04, BCD)
class Clock:
    def __init__(s, spec=None):
        now = datetime.datetime.now().replace(microsecond=0)
        if spec:
            p = [int(x) for x in spec.split(':')] + [0, 0]
            now = now.replace(hour=p[0], minute=p[1], second=p[2])
        s.base = now
    def set(s, hh, mm, ss): s.base = s.now().replace(hour=hh, minute=mm, second=ss); s.t0 = cnt[0]
    t0 = 0
    def now(s): return s.base + datetime.timedelta(milliseconds=cnt[0] - s.t0)
    @staticmethod
    def bcd(v): return ((v // 10) << 4) | (v % 10)
    def reg_time(s): d = s.now(); b = s.bcd; return (b(d.hour) << 16) | (b(d.minute) << 8) | b(d.second)
    def reg_date(s): d = s.now(); b = s.bcd; return (b(d.year % 100) << 16) | ((d.isoweekday()) << 13) | (b(d.month) << 8) | b(d.day)
clock = Clock(args.time)

# ---- звук: TIMER2 CH0 ШІМ
class Beeper:
    RATE = 22050
    AMP = 10000
    MIN_S = 0.12                              # бекенди зі стартом «із затримкою» (aplay/afplay/winsound) грають сигнал щонайменше стільки секунд
    def __init__(s, enabled=True):
        s.enabled = enabled; s.backend = None; s.proc = None; s.on = None; s.events = []; s.stream = None; s.err = None
        s.ph = 0.0; s.f = 0.0; s.duty = 0.5; s.playing = False; s.srate = s.RATE; s.t_start = 0.0; s.gen = 0; s.argv = None
        if not enabled: return
        try:
            import sounddevice as sd
            s.sd = sd
            try:
                s.stream = sd.OutputStream(samplerate=s.RATE, channels=1, dtype='int16', callback=s._cb)
            except Exception:                 # пристрій не вміє 22050 Гц (WASAPI) → його власна частота
                s.srate = int(sd.query_devices(None, 'output')['default_samplerate'])
                s.stream = sd.OutputStream(samplerate=s.srate, channels=1, dtype='int16', callback=s._cb)
            s.stream.start(); s.backend = 'sounddevice'
        except Exception as e:
            s.stream = None; s.err = 'sounddevice: %s' % e       # це лише підказка; не помилка, якщо знайдеться запасний бекенд
            if sys.platform == 'win32':
                try: import winsound; s.ws = winsound; s.backend = 'winsound'
                except Exception as e2: s.err = 'winsound: %s' % e2
            else:
                for exe, argv in (('aplay', ['aplay', '-q', '-t', 'wav', '-']), ('paplay', ['paplay']), ('afplay', None)):
                    if shutil.which(exe): s.backend = exe; s.argv = argv; break
            if s.backend: s.err = None                           # запасний бекенд працює → не показувати «помилку» про відсутній sounddevice
    def _cb(s, out, frames, ti, status):      # sounddevice: безперервний потік
        if not s.playing or s.f <= 0: out[:] = 0; return
        step = s.f / s.srate; ph = s.ph; d = s.duty; A = s.AMP
        try:
            import numpy as np
            p = (ph + step * np.arange(frames)) % 1.0
            out[:, 0] = np.where(p < d, A, -A); s.ph = (ph + step * frames) % 1.0
        except ImportError:
            for i in range(frames):
                out[i, 0] = A if ph < d else -A; ph += step
                if ph >= 1.0: ph -= 1.0
            s.ph = ph
    def wav_bytes(s, f, duty, secs):
        n = int(s.RATE * secs); per = s.RATE / f; cyc = max(1, int(round(n / per))); n = int(round(cyc * per))
        data = b''.join(struct.pack('<h', s.AMP if ((i % per) / per) < duty else -s.AMP) for i in range(n))
        import io
        bio = io.BytesIO(); w = wave.open(bio, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(s.RATE); w.writeframes(data); w.close()
        return bio.getvalue()
    def wav_file(s, f, duty, secs):           # кешований WAV у тимчасовій теці
        fn = os.path.join(tempfile.gettempdir(), 'po80_beep_%d_%d_%d.wav' % (round(f), round(duty * 100), round(secs * 10)))
        if not os.path.exists(fn) or os.path.getsize(fn) < 100:
            with open(fn, 'wb') as fh: fh.write(s.wav_bytes(f, duty, secs))
        return fn
    def start(s, f, duty):
        s.f, s.duty = f, max(0.05, min(0.95, duty)); s.playing = True; s.gen += 1; s.t_start = time.perf_counter()
        if not s.enabled: return
        try:
            if s.backend == 'winsound':
                # SND_MEMORY|SND_ASYNC у winsound не підтримується (RuntimeError) → граємо з файлу
                s.ws.PlaySound(s.wav_file(f, s.duty, 0.2), s.ws.SND_FILENAME | s.ws.SND_ASYNC | s.ws.SND_LOOP)
            elif s.backend in ('aplay', 'paplay', 'afplay'):
                s.stop_proc()
                if s.backend == 'afplay':
                    s.proc = subprocess.Popen(['afplay', s.wav_file(f, s.duty, 3.0)], stderr=subprocess.DEVNULL)
                else:
                    s.proc = subprocess.Popen(s.argv, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
                    try: s.proc.stdin.write(s.wav_bytes(f, s.duty, 3.0)); s.proc.stdin.close()
                    except Exception: pass
            s.err = None if s.backend != 'sounddevice' else s.err
        except Exception as e:
            s.err = '%s: %s' % (s.backend, e)
    def stop_proc(s):
        if s.proc and s.proc.poll() is None:
            try: s.proc.kill()
            except Exception: pass
        s.proc = None
    def _halt(s):
        try:
            if s.backend == 'winsound': s.ws.PlaySound(None, s.ws.SND_PURGE)
            else: s.stop_proc()
        except Exception: pass
    def stop(s, now=False):
        s.playing = False
        if s.backend == 'sounddevice': return                 # колбек сам видає тишу
        left = s.MIN_S - (time.perf_counter() - s.t_start)
        if now or left <= 0.005: s._halt(); return
        g = s.gen                                              # дати короткому сигналу (100 мс) дійти до динаміка
        t = threading.Timer(left, lambda: s._halt() if (s.gen == g and not s.playing) else None); t.daemon = True; t.start()
    def render_wav(s, path, total_ms):
        n = int(s.RATE * total_ms / 1000.0); buf = [0] * n
        for t0, t1, f, d in s.events:
            a = int(t0 * s.RATE / 1000.0); b = min(n, int((t1 if t1 is not None else total_ms) * s.RATE / 1000.0)); per = s.RATE / f
            for i in range(a, b): buf[i] = s.AMP if (((i - a) % per) / per) < d else -s.AMP
        w = wave.open(path, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(s.RATE)
        w.writeframes(struct.pack('<%dh' % n, *buf)); w.close()
beeper = Beeper(not args.mute and args.headless is None)
snd = {'on': False, 'f': 0, 'd': 0}       # поточний стан піщалки (для GUI)

def audio_update():
    car = regs[0x4000042C] + 1; psc = regs[0x40000428] + 1
    en = (regs[0x40000400] & 1) and (regs[0x40000420] & 1) and ((regs[0x40000418] >> 4) & 7) in (6, 7)
    f = 48e6 / (psc * car) if car and psc else 0
    d = min(1.0, regs[0x40000434] / car) if car else 0
    if en and f > 20:
        if not snd['on'] or abs(snd['f'] - f) > 1 or abs(snd['d'] - d) > 0.005:
            if snd['on']: beeper.events[-1][1] = cnt[0]
            snd.update(on=True, f=f, d=d); beeper.events.append([cnt[0], None, f, max(0.05, min(0.95, d))]); beeper.start(f, d)
    elif snd['on']:
        snd['on'] = False; beeper.events[-1][1] = cnt[0]; beeper.stop()

# SIMSCRIPT: зміни параметрів за розкладом (мс емульованого часу)
SCHED = []
for _e in os.environ.get('SIMSCRIPT', '').split(';'):
    if _e.strip():
        _t, _, _kv = _e.partition(':'); SCHED.append((int(_t), [kv.split('=') for kv in _kv.split(',')]))
SCHED.sort(key=lambda x: x[0])
def apply_param(k, v):
    v = float(v)
    if k == 'bat': ADC_VAL[0] = volts_to_adc(v)
    elif k == 'finger': sensor.finger = bool(v)
    elif k == 'hrv': sensor.hrv = bool(v)
    elif k in ('spo2', 'pr', 'pi', 'noise'): setattr(sensor, k, v)
    for cb in GUI_SYNC: cb()
GUI_SYNC = []
def run_schedule():
    while SCHED and SCHED[0][0] <= cnt[0]:
        for k, v in SCHED.pop(0)[1]: apply_param(k.strip(), v)

# ================================================================ USB: GD32 USBFS (OTG-FS, режим пристрою) + віртуальний ПК-хост
# Прошивка має справжній USB-стек (HID, VID:PID 28E9:028A, інтеррапт-ендпойнти IN/OUT по 64 байти). Тут емулюється
# периферія USBFS (регістри 0x50000000, FIFO, IRQ 67) і «комп'ютер» на іншому кінці кабелю: він робить ресет шини,
# енумерацію (дескриптори, SET_ADDRESS, SET_CONFIGURATION, HID-звіт) і далі повторює обмін зі скрипту hid_pulse_oximeter
# (HID-звіти по 64 байти: init, модель, ім'я користувача, час, налаштування, keep-alive).
# Усе, що пристрій надсилає (IN) і отримує (OUT), потрапляє в USB-журнал (під екраном у GUI).
USB = 0x50000000
USB_IRQ = 67                                   # USBFS_IRQn у GD32F3x0
G_SOF, G_RXFNE, G_SP, G_RST, G_ENUMF, G_IEP, G_OEP = 1 << 3, 1 << 4, 1 << 11, 1 << 12, 1 << 13, 1 << 18, 1 << 19
G_STICKY = (1 << 2) | (1 << 3) | (1 << 6) | (1 << 7) | (1 << 11) | (1 << 12) | (1 << 13) | (1 << 31)   # прапори GINTF, що скидаються записом 1
USBDBG = int(os.environ.get('USBDBG', '0'))        # USBDBG=мс: друкувати звернення прошивки до регістрів USBFS починаючи з цього моменту
USB_PACE = int(os.environ.get('USBPACE', '100'))       # пауза між командами хоста, мс (у zip — без пауз; прошивці потрібен час на розбір)
usb_on = [not args.no_usb]                     # «кабель» підключено до віртуального ПК
usb_stat = collections.Counter()               # лічильники пакетів: in / out / ctl
usb_last = {}                                  # останні розібрані дані: PR, SpO2, model, user

class UsbLog:
    """Журнал USB-обміну. kind: 'in' (пристрій→ПК), 'out' (ПК→пристрій), 'ctl' (службове/енумерація), 'info', 'err'."""
    def __init__(s): s.lines = []; s.listeners = []; s.sink = None
    def add(s, kind, text):
        rec = (cnt[0], kind, text); s.lines.append(rec)
        if len(s.lines) > 6000: del s.lines[:1000]
        if s.sink: s.sink(rec)
        for cb in s.listeners: cb(rec)
    @staticmethod
    def fmt(rec): return '%8.3f  %s' % (rec[0] / 1000.0, rec[2])
usblog = UsbLog()

def hexs(d, full=False):
    d = bytes(d); n = len(d)
    if not full: d = d.rstrip(b'\0') or d[:1]
    return ' '.join('%02X' % b for b in d) + ('' if len(d) == n else '  (+%d×00)' % (n - len(d)) if len(d) else '')

OUT_NAMES = {0x80: 'init', 0x81: T('запит моделі'), 0x83: T('встановити час'), 0x8E: T('запит імені користувача'), 0x9A: 'keep-alive', 0x9B: T('налаштування')}
def frames(d):
    """Розбір потоку пристрою на кадри: [cmd][...][CRC], CRC = (сума попередніх байтів) & 0x7F (перевірено на живому потоці).
    Довжини: F0 → 2, F1 → 10, FE → 10, EB 00 → 6, EB 01 → 8. Решта 64-байтного звіту — нулі (доповнення).
    Повертає [(кадр, коректна_сума)]."""
    d = bytes(d); out = []; i = 0
    while i < len(d):
        if not any(d[i:]): break                                # решта звіту — нулі
        c = d[i]
        if c == 0xF0: ln = 2                                    # відповідь на init: F0 70
        elif c in (0xF1, 0xFE): ln = 10                         # F1 + 8 символів моделі / FE 03 + 7 символів імені, + CRC
        elif c == 0xEB and i + 1 < len(d): ln = 8 if d[i + 1] == 1 else 6     # EB 01 (PR/SpO2) — 8 Б, EB 00 (хвиля) — 6 Б
        else: ln = len(d) - i
        ln = max(1, min(ln, len(d) - i)); f = d[i:i + ln]
        out.append((f, len(f) >= 2 and (sum(f[:-1]) & 0x7F) == f[-1])); i += ln
    return out

def decode_frame(f):
    f = bytes(f)
    if f[0] == 0xF0: return T('init підтверджено')
    if f[0] == 0xF1: return T('модель %r') % f[1:9].decode('ascii', 'replace').strip()
    if f[0] == 0xFE and len(f) > 2 and f[1] == 0x03: return T("ім'я користувача %r") % f[2:9].decode('ascii', 'replace').strip()
    if f[0] == 0xEB and len(f) >= 7 and f[1] == 0x01:
        pr, sp = f[3], f[4]
        return T('PR=%s уд/хв  SpO2=%s  (прапори %02X)') % (pr if pr < 127 else '—', ('%d %%' % sp) if sp < 127 else '—', f[2])
    if f[0] == 0xEB and len(f) >= 6 and f[1] == 0x00:           # потік плетизмограми: [хвиля 0..127][стовпчик = хвиля>>3]; біт 6 байта 2 = удар пульсу
        return T('хвиля %d, стовпчик %d%s') % (f[3], f[4], ' ♥' if f[2] & 0x40 else '')
    if f[0] == 0xEB and len(f) > 2: return T('EB-запис тип %d, дані %s') % (f[1], hexs(f[3:-1], True) if len(f) > 4 else '—')
    return T('кадр 0x%02X') % f[0]

def decode_in(d):
    fr = frames(d)
    return '; '.join(decode_frame(f) + ('' if ok else ' (CRC?)') for f, ok in fr) if fr else T('порожній звіт')

class UsbFs:
    """Регістрова модель USBFS у режимі пристрою (FIFO-режим, без DMA), як її бачить бібліотека GD32."""
    NEP = 4
    def __init__(s):
        s.flags = 0; s.suspended = False; s.reset_queues(); regs[USB + 0x804] = 2     # DCTL.SDIS: поки прошивка не «підключила» пристрій
    def reset_queues(s):
        s.rxq = collections.deque(); s.cur = collections.deque()
        s.inbuf = [bytearray() for _ in range(s.NEP)]; s.in_ready = [None] * s.NEP
    ia = staticmethod(lambda n: USB + 0x900 + 0x20 * n)      # DIEPCTLn
    oa = staticmethod(lambda n: USB + 0xB00 + 0x20 * n)      # DOEPCTLn
    def txfe(s, n): return 0 if s.inbuf[n] or s.in_ready[n] is not None else 0x80      # TXFE — рівень: FIFO ендпойнта порожній
    def daint(s):
        d = 0
        for n in range(s.NEP):
            m = (regs[USB + 0x810] & ~0x80) | (((regs[USB + 0x834] >> n) & 1) << 7)          # DIEPINTEN + TXFE (DIEPFEINTEN)
            if (regs[s.ia(n) + 8] | s.txfe(n)) & m: d |= 1 << n
            if regs[s.oa(n) + 8] & regs[USB + 0x814]: d |= 1 << (16 + n)
        return d
    def gintf(s):
        v = s.flags | (G_RXFNE if s.rxq else 0); d = s.daint() & regs[USB + 0x81C]
        return v | (G_IEP if d & 0xFFFF else 0) | (G_OEP if d >> 16 else 0)
    def irq(s): return bool(regs[USB + 0x08] & 1) and bool(s.gintf() & regs[USB + 0x18])
    def connected(s): return not regs[USB + 0x804] & 2 and bool(regs[USB + 0x18] & G_RST)     # SDIS=0 і прошивка чекає USBRST
    def mps0(s): return (64, 32, 16, 8)[regs[s.ia(0)] & 3]
    def stalled(s, n): return bool(regs[s.ia(n)] & (1 << 21) or regs[s.oa(n)] & (1 << 21))

    # ---- регістри (читання / запис з боку прошивки)
    def read(s, off, size):
        a = USB + off; v = regs[a]
        if off == 0x00: return v | 0x000C0000                          # GOTGCS: сесія A/B валідна
        if off == 0x10: return v | 0x80000000                          # GRSTCTL.AHBIDL
        if off == 0x14: return s.gintf()
        if off == 0x1C: return s.rxq[0][0] if s.rxq else 0             # GRSTATR (без вилучення)
        if off == 0x20: return s.rx_pop()                              # GRSTATP (вилучає запис зі стеку статусів)
        if off == 0x808: return 0x6 | (1 if s.suspended else 0) | ((cnt[0] & 0x3FFF) << 8)     # DSTAT: Full-Speed
        if off == 0x818: return s.daint()
        if 0x900 <= off < 0x900 + 0x20 * s.NEP:
            r = off & 0x1F; n = (off - 0x900) >> 5
            if r == 0x08: return v | s.txfe(n)                         # DIEPINTF.TXFE (рівень)
            if r == 0x18: return 0x100                                 # DIEPTFSTAT: місця в FIFO достатньо
        if 0x1000 <= off < 0x1000 * (s.NEP + 1):                       # FIFO: читання = слова пакета OUT/SETUP
            return s.cur.popleft() if s.cur else 0
        return v
    def write(s, off, size, val):
        a = USB + off; r = regs
        if off == 0x04: r[a] &= ~val; return                           # GOTGINTF (w1c)
        if off == 0x10:                                                # GRSTCTL: самоочищувані команди
            if val & 1: s.core_reset()
            if val & 0x10: s.rxq.clear(); s.cur.clear()
            if val & 0x20:
                for n in (range(s.NEP) if val & 0x400 else [(val >> 6) & 0xF]):
                    if n < s.NEP: s.inbuf[n].clear(); s.in_ready[n] = None
            r[a] = 0; return
        if off == 0x14: s.flags &= ~(val & G_STICKY); return           # GINTF (w1c)
        if off == 0x804:                                               # DCTL
            if val & 0x80: s.flags |= 1 << 6                           # SGINAK → GINAKEFF
            if val & 0x200: s.flags |= 1 << 7                          # SGONAK → GONAKEFF
            r[a] = val & ~0xF00; return
        if 0x900 <= off < 0x900 + 0x20 * s.NEP:
            n, reg = (off - 0x900) >> 5, off & 0x1F
            if reg == 0x00: s.in_ctl(n, val); return
            if reg == 0x08: r[a] &= ~val; return                       # DIEPINTF (w1c)
        elif 0xB00 <= off < 0xB00 + 0x20 * s.NEP:
            n, reg = (off - 0xB00) >> 5, off & 0x1F
            if reg == 0x00: s.out_ctl(n, val); return
            if reg == 0x08: r[a] &= ~val; return                       # DOEPINTF (w1c)
        elif 0x1000 <= off < 0x1000 * (s.NEP + 1):                     # FIFO IN-ендпойнта (off>>12)-1
            n = (off >> 12) - 1; s.inbuf[n] += struct.pack('<I', val & 0xFFFFFFFF); s.check_in(n); return
        r[a] = val
    def core_reset(s):
        for k in [k for k in list(regs) if USB + 0x800 <= k < USB + 0x1000]: del regs[k]
        regs[USB + 0x804] = 2; regs[USB + 0x18] = 0; s.flags = 0; s.reset_queues()

    # ---- IN-ендпойнти (пристрій → хост)
    def in_ctl(s, n, val):
        a = s.ia(n); old = regs[a]; epena = (old | val) & (1 << 31)
        new = (val & ~((1 << 26) | (1 << 27) | (1 << 28) | (1 << 29) | (1 << 30) | (1 << 31))) | epena
        if val & (1 << 30) and old & (1 << 31):                        # EPDIS: вимкнути ендпойнт
            new &= ~(1 << 31); regs[a + 8] |= 2; s.inbuf[n].clear(); s.in_ready[n] = None
        elif val & (1 << 31) and not old & (1 << 31): s.inbuf[n].clear(); s.in_ready[n] = None     # новий запуск передачі
        regs[a] = new; s.check_in(n)
    def check_in(s, n):
        if not regs[s.ia(n)] & (1 << 31) or s.in_ready[n] is not None: return
        xs = regs[s.ia(n) + 0x10] & 0x7FFFF
        if len(s.inbuf[n]) >= xs: s.in_ready[n] = bytes(s.inbuf[n][:xs])      # дані повністю у FIFO (або ZLP) — чекають IN-токена хоста
    def complete_in(s, n):
        a = s.ia(n); regs[a] &= ~(1 << 31); regs[a + 8] |= 1; regs[a + 0x10] &= ~0x1FFFFFFF
        s.in_ready[n] = None; s.inbuf[n].clear()

    # ---- OUT-ендпойнти (хост → пристрій)
    def out_ctl(s, n, val):
        a = s.oa(n); old = regs[a]; epena = (old | val) & (1 << 31)
        new = (val & ~((1 << 26) | (1 << 27) | (1 << 28) | (1 << 29) | (1 << 30) | (1 << 31))) | epena
        if val & (1 << 30) and old & (1 << 31): new &= ~(1 << 31); regs[a + 8] |= 2
        regs[a] = new
    def out_ready(s, n): return bool(regs[s.oa(n)] & (1 << 31))
    def host_setup(s, data):
        s.rxq.append([(6 << 17) | (8 << 4), bytes(data)]); s.rxq.append([4 << 17, b''])       # SETUP отримано + SETUP завершено
    def host_out(s, n, data):
        data = bytes(data); s.rxq.append([(2 << 17) | (len(data) << 4) | n, data]); s.rxq.append([(3 << 17) | n, b''])
    def rx_pop(s):
        if not s.rxq: return 0
        st, data = s.rxq.popleft(); kind, ep = (st >> 17) & 0xF, st & 0xF
        w = (len(data) + 3) // 4; s.cur = collections.deque(struct.unpack('<%dI' % w, data.ljust(w * 4, b'\0')))
        if kind == 4: regs[s.oa(ep) + 8] |= 8                          # DOEPINTF.STPF: фаза SETUP завершена
        if kind == 3: regs[s.oa(ep) + 8] |= 1; regs[s.oa(ep)] &= ~(1 << 31)       # DOEPINTF.TF: передачу OUT завершено
        return st
    def bus_reset(s):
        s.reset_queues(); s.suspended = False
        for n in range(s.NEP):
            for f in (s.ia, s.oa): regs[f(n)] = 0x8000 if n == 0 else 0; regs[f(n) + 8] = 0; regs[f(n) + 0x10] = 0
        regs[USB + 0x834] = 0                                                       # DIEPFEINTEN: скасувати відкладені (застарілі) передачі TXFE — інакше ISR віддасть сміття зі старого стека
        regs[USB + 0x800] &= ~0x7F0; s.flags = (s.flags & ~G_SP) | G_RST        # DCFG.DAD = 0
usbfs = UsbFs()

class UsbHost:
    """Віртуальний комп'ютер на кінці кабелю. Сценарій — генератор: yield ('sleep', мс) | ('wait', умова, таймаут_мс)."""
    def __init__(s, fs):
        s.fs = fs; s.gen = None; s.pend = None; s.t0 = 0; s.state = 'відключено'; s.rx_n = 0; s.ep_in = 1; s.ep_out = 1; s.mps = 64; s.tries = 0; s.restored = False
    def start(s): s.gen = s.main(); s.pend = None; s.state = 'очікування пристрою'; s.rx_n = 0
    def stop(s): s.gen = None; s.pend = None; s.state = 'відключено'
    def tick(s):
        if s.gen is None: return
        for _ in range(64):
            if s.pend is None: res = None
            else:
                kind, a, b = s.pend
                if kind == 'sleep':
                    if cnt[0] < s.t0 + a: break
                    res = True
                elif a(): res = True
                elif cnt[0] >= s.t0 + b: res = False
                else: break
                s.pend = None
            try: p = s.gen.send(res)
            except StopIteration: s.gen = None; break
            s.pend = (p[0], p[1], p[2] if len(p) > 2 else 0); s.t0 = cnt[0]
        s.poll()
    def poll(s):                      # хост опитує IN-ендпойнти (крім EP0): забирає готові пакети
        if s.state != 'активний': return
        fs = s.fs
        for n in range(1, fs.NEP):
            d = fs.in_ready[n]
            if d is not None and not fs.stalled(n): fs.complete_in(n); s.on_in(n, d)
    def on_in(s, n, d):
        s.rx_n += 1; usb_stat['in'] += 1
        if s.restored:                                                  # після «Завантажити стан»: SRAM прошивки може містити застарілий вказівник на буфер передачі
            if d and d[0] in (0xF0, 0xF1, 0xFE, 0xEB): s.restored = False
            elif d: usblog.add('info', T('USB: відкинуто застарілий пакет після завантаження стану (%d Б, артефакт відновлення SRAM)') % len(d)); return
        if not d: usblog.add('wave', T('Пристрій → ПК  EP%d  ZLP') % n); return
        txt = decode_in(d)
        for f, ok in frames(d):
            if f[0] == 0xEB and len(f) > 4 and f[1] == 0x01: usb_last.update(PR=f[3] if f[3] < 127 else None, SpO2=f[4] if f[4] < 127 else None, t=cnt[0])
            if f[0] == 0xF1: usb_last['model'] = f[1:9].decode('ascii', 'replace').strip()
            if f[0] == 0xFE and len(f) > 2 and f[1] == 0x03: usb_last['user'] = f[2:9].decode('ascii', 'replace').strip()
        wave = bool(frames(d)) and all(f[0] == 0xEB and f[1:2] == b'\x00' for f, ok in frames(d))      # звіт лише з відліками хвилі (EB 00)
        usblog.add('wave' if wave else 'in', T('Пристрій → ПК  %s   [%s]') % (hexs(d, usb_full[0]), txt))

    # ---- сценарій
    def until(s, cond, timeout): return (yield ('wait', cond, timeout))
    def main(s):
        fs = s.fs
        while True:
            s.state = 'очікування пристрою'
            yield from s.until(lambda: fs.connected(), 10 ** 9)
            yield ('sleep', 60)
            usblog.add('info', T('USB: ресет шини'))
            s.state = 'енумерація'; fs.bus_reset()
            if not (yield from s.until(lambda: not fs.flags & G_RST, 1500)): usblog.add('err', T('USB: прошивка не обробила USBRST')); s.state = 'помилка'; return
            yield ('sleep', 2); fs.flags |= G_ENUMF
            if not (yield from s.until(lambda: not fs.flags & G_ENUMF, 1500)): usblog.add('err', T('USB: прошивка не обробила ENUMF')); s.state = 'помилка'; return
            usblog.add('info', T('USB: Full-Speed, енумерація'))
            yield ('sleep', 20)
            if (yield from s.enumerate()):
                s.state = 'активний'; s.tries = 0; yield from s.session(); return
            s.tries += 1; s.state = 'помилка енумерації'
            if s.tries >= 3: usblog.add('err', T('USB: енумерація не вдалася, хост здався')); return
            usblog.add('err', T('USB: повтор енумерації…')); yield ('sleep', 1000)

    def ctl(s, bm, br, wv, wi, wl, name, out=b''):
        """Керуюча передача. Повертає bytes (дані IN-фази або b'') або None, якщо пристрій не відповів / STALL."""
        fs = s.fs; usb_stat['ctl'] += 1
        fs.host_setup(struct.pack('<BBHHH', bm, br, wv, wi, wl))
        data = b''
        def got(): return fs.in_ready[0] is not None or fs.stalled(0)
        if bm & 0x80 and wl:
            while len(data) < wl:
                if not (yield from s.until(got, 300)): usblog.add('err', T('USB: %s — пристрій не відповів') % name); return None
                if fs.stalled(0) and fs.in_ready[0] is None: usblog.add('err', 'USB: %s — STALL' % name); return None
                pk = fs.in_ready[0]; fs.complete_in(0); data += pk
                if len(pk) < fs.mps0(): break
            fs.host_out(0, b'')                                            # статус-фаза: OUT ZLP
            yield from s.until(lambda: not fs.rxq, 100); yield ('sleep', 2)
            return data[:wl]
        if wl:                                                             # дані OUT, статус — IN ZLP
            fs.host_out(0, out); yield from s.until(lambda: not fs.rxq, 100)
        if not (yield from s.until(got, 300)): usblog.add('err', T('USB: %s — немає статус-фази') % name); return None
        if fs.stalled(0) and fs.in_ready[0] is None: usblog.add('err', 'USB: %s — STALL' % name); return None
        fs.complete_in(0); yield ('sleep', 1)
        return b''

    def enumerate(s):
        L = lambda t: usblog.add('ctl', 'USB: ' + t)
        d = yield from s.ctl(0x80, 6, 0x0100, 0, 64, 'GET_DESCRIPTOR(Device)')
        if not d or len(d) < 8: return False
        L(T('Device: VID:PID=%04X:%04X, bcdUSB=%X.%02X, EP0=%d Б') % (d[8] | d[9] << 8, d[10] | d[11] << 8, d[3], d[2], d[7]) if len(d) >= 12 else 'Device: ' + hexs(d))
        if (yield from s.ctl(0x00, 5, 7, 0, 0, 'SET_ADDRESS')) is None: return False
        L('SET_ADDRESS 7'); yield ('sleep', 5)
        c9 = yield from s.ctl(0x80, 6, 0x0200, 0, 9, 'GET_DESCRIPTOR(Config, 9)')
        if not c9 or len(c9) < 9: return False
        cfg = yield from s.ctl(0x80, 6, 0x0200, 0, c9[2] | c9[3] << 8, 'GET_DESCRIPTOR(Config)')
        if not cfg: return False
        i, hidlen = 0, 0
        while i + 2 <= len(cfg) and cfg[i]:
            ln, ty = cfg[i], cfg[i + 1]
            if ty == 0x21 and ln >= 9: hidlen = cfg[i + 7] | cfg[i + 8] << 8
            if ty == 5 and ln >= 7:
                if cfg[i + 2] & 0x80: s.ep_in = cfg[i + 2] & 15
                else: s.ep_out = cfg[i + 2] & 15
                s.mps = cfg[i + 4] | cfg[i + 5] << 8
            i += ln
        L(T('Config: %d Б, HID report %d Б, EP IN %d / OUT %d, пакет %d Б') % (len(cfg), hidlen, s.ep_in, s.ep_out, s.mps))
        lang = yield from s.ctl(0x80, 6, 0x0300, 0, 255, 'GET_DESCRIPTOR(String 0)')
        names = []
        for idx in (1, 2, 3):
            b = yield from s.ctl(0x80, 6, 0x0300 | idx, 0x0409, 255, 'GET_DESCRIPTOR(String %d)' % idx)
            names.append(b[2:].decode('utf-16le', 'replace') if b and len(b) > 2 else '?')
        L(T('Рядки: виробник %r, виріб %r, серійний %r') % tuple(names))
        if (yield from s.ctl(0x00, 9, 1, 0, 0, 'SET_CONFIGURATION')) is None: return False
        L('SET_CONFIGURATION 1')
        if (yield from s.ctl(0x21, 10, 0, 0, 0, 'SET_IDLE')) is None: L(T('SET_IDLE не підтримується (нормально)'))
        if hidlen:
            rep = yield from s.ctl(0x81, 6, 0x2200, 0, hidlen, 'GET_DESCRIPTOR(HID Report)')
            if rep: L(T('HID Report descriptor: %d Б  %s') % (len(rep), hexs(rep, True)))
        usblog.add('info', T('USB: пристрій налаштовано — обмін HID-звітами'))
        return True

    def send(s, data, note=''):
        """OUT-звіт на інтеррапт-ендпойнт (64 байти, перший байт — ID звіту, як у hid_pulse_oximeter)."""
        fs = s.fs; n = s.ep_out; d = bytes(data).ljust(64, b'\0')
        if not (yield from s.until(lambda: fs.out_ready(n), 500)):
            usblog.add('err', T('ПК → Пристрій  EP%d NAK: пристрій не готовий приймати (%s)') % (n, OUT_NAMES.get(d[0], '0x%02X' % d[0]))); return False
        fs.host_out(n, d); usb_stat['out'] += 1
        usblog.add('out', T('ПК → Пристрій  %s   [%s%s]') % (hexs(d, usb_full[0]), OUT_NAMES.get(d[0], T('команда 0x%02X') % d[0]), (', ' + note) if note else ''))
        yield from s.until(lambda: not fs.rxq, 100); yield ('sleep', 2)
        return True
    def session(s):
        if apploop[0] < 3:
            usblog.add('info', T('USB: чекаю, поки прошивка дійде до головного циклу…'))
            if not (yield from s.until(lambda: apploop[0] >= 3, 8000)): usblog.add('err', T('USB: головний цикл прошивки так і не запустився — продовжую'))
        yield ('sleep', 500)                                               # як time.sleep(0.5) у hid_pulse_oximeter
        n = clock.now()
        cmds = (([0x81, 0x01], ''), ([0x8E, 0x03, 0x11], ''), ([0x83, n.year - 2000, n.month, n.day, n.hour, n.minute, n.second, n.weekday(), 4], n.strftime('%Y-%m-%d %H:%M:%S')),
                ([0x80], ''), ([0x9B, 0x01, 0x1C], ''), ([0x9B, 0x00, 0x1B], ''))
        for pkt, note in cmds:
            yield from s.send(pkt, note); yield ('sleep', USB_PACE)        # прошивка обробляє команди у фоновому завданні — даємо їй час
            if pkt[0] in (0x81, 0x8E):                                      # відповідь на запит — чекаємо, при потребі повторюємо
                key = 'model' if pkt[0] == 0x81 else 'user'
                for _ in range(3):
                    if (yield from s.until(lambda: key in usb_last, 300)): break
                    usblog.add('info', T('USB: немає відповіді на 0x%02X — повторюю запит') % pkt[0]); yield from s.send(pkt, T('повтор')); yield ('sleep', USB_PACE)
        last = 0; t_chk = cnt[0]
        while True:
            yield ('sleep', 1)
            if s.rx_n - last > 10: last = s.rx_n; yield from s.send([0x9A, 0x1A])         # keep-alive кожні ~10 прийнятих пакетів
            elif cnt[0] - t_chk > 1000:                                                   # тиша 1 с — теж keep-alive (як у реального ПЗ, що читає з таймаутом 1 с)
                t_chk = cnt[0]
                if s.rx_n == last: yield from s.send([0x9A, 0x1A])
                last = s.rx_n
usb_host = UsbHost(usbfs)
usb_full = [False]
apploop = [0]                                  # скільки разів прошивка пройшла головний цикл (0 = ще завантажується)
MAIN_LOOP = 0x08017494                         # головний цикл прошивки: сюди повертається планувальник (≈1.8 с після старту)
def _mainloop_hook(uc_, addr, size, ud):       # хук дешевий і НЕ видаляє себе (hook_del зсередини колбека ламає емуляцію)
    if apploop[0] < 5:
        apploop[0] += 1
        if apploop[0] == 1: usblog.add('info', T('USB: головний цикл прошивки ожив (t=%.3f с)') % (cnt[0] / 1000.0))
uc.hook_add(UC_HOOK_CODE, _mainloop_hook, None, MAIN_LOOP, MAIN_LOOP)                             # показувати 64-байтні пакети повністю (за замовчуванням — без хвоста з нулів)

def usb_plug(on):
    """Віртуальний кабель: вимкнено → шина тиха (suspend); увімкнено → ресет шини й енумерація з нуля."""
    usb_on[0] = bool(on)
    if on: usbfs.reset_queues(); usbfs.suspended = False; usb_host.start(); usblog.add('info', T('USB: кабель підключено'))
    else: usb_host.stop(); usbfs.reset_queues(); usbfs.suspended = True; usbfs.flags |= G_SP; usblog.add('info', T('USB: кабель відключено'))
if usb_on[0]: usb_host.start()

# ---------------------------------------------------------------- периферія
def mmio_read(uc, off, size, base):
    a = base + off
    if USB <= a < USB + 0x10000:
        v = usbfs.read(a - USB, size) & ((1 << (8 * size)) - 1)
        if USBDBG and cnt[0] >= USBDBG and (a - USB) not in (0x14, 0x808): print('  usb R %04X = %08X  pc=%08X t=%d' % (a - USB, v, uc.reg_read(UC_ARM_REG_PC), cnt[0]))
        return v
    v = regs[a]
    if base == 0x40021000:                      # RCC
        if off == 0x00: v |= (1 << 1) | (1 << 17) | (1 << 25)      # HSIRDY HSERDY PLLRDY
        if off == 0x04: v = (v & ~0xC) | ((v & 3) << 2)             # SWS = SW
        if off == 0x24: v |= 1 << 1                                 # LSIRDY (CSR)
        if off == 0x20: v |= 1 << 1                                 # LSERDY (BDCR)
    elif base == 0x40013800:                    # USART1 (F0-стиль: ISR 0x1C)
        if off == 0x1C: v |= (1 << 7) | (1 << 6)                    # TXE TC
    elif base == 0x40004400:
        if off == 0x1C: v |= (1 << 7) | (1 << 6)
    elif base in (0x40013000, 0x40003800):      # SPI0/SPI1 (GD32 STAT @0x08)
        if off == 0x08: v = (v | 3) & ~0x80                         # RBNE TBE, !TRANS
    elif base == 0x40012400:                    # ADC
        if off == 0x00: v |= 2 | 4                                  # EOC (GD32 STAT)
        if off == 0x08: v &= ~0xC                                   # RSTCLB/CLB самоочищуються
        if off == 0x4C: v = ADC_VAL[0]
    elif base in (0x40000000, 0x40000400, 0x40002000, 0x40014000, 0x40014400, 0x40014800, 0x40012c00, 0x40001000) and off == 0x10:
        v |= 1
    elif base in (0x48000000, 0x48000400, 0x48000800) and off == 0x10:   # IDR: спокій = 0, натиснуто = 1
        v = 0
        if base == 0x48000400: v = pressed_mask() ^ IDLEHI
    elif base == 0x40002800:
        if off == 0x00: v = clock.reg_time()                         # RTC TIME (BCD) — живий годинник
        elif off == 0x04: v = clock.reg_date()                       # RTC DATE
        elif off in (0x0C,): v |= 0x60
    elif base == 0x40007000:                    # PWR
        if off == 0x04: v |= 1 << 1
    elif base == 0x40022000:                    # FLASH
        if off == 0x0C: v &= ~1                                     # !BSY
    return v & ((1 << (8 * size)) - 1)

# ---- FMC (flash): стирання сторінки (PER+START) і програмування півслова (PG), з дозволом від GUI/--flash-write
FMC = 0x40022000; FMC_CTL = FMC + 0x10; FMC_STAT = FMC + 0x0C; FMC_ADDR = FMC + 0x14
fmc = {'allow': [bool(args.flash_write)], 'unlocked': False, 'key': 0, 'writes': 0, 'erases': 0, 'denied': 0, 'dirty': False}
regs[FMC_CTL] = 0x80                          # FMC_CTL після скидання: LK=1
PAGE = 0x400                                  # GD32F350: сторінка 1 КБ
def fmc_key(val):
    if val == 0x45670123: fmc['key'] = 1
    elif val == 0xCDEF89AB and fmc['key'] == 1: fmc['unlocked'] = True; regs[FMC_CTL] &= ~0x80; fmc['key'] = 0
    else: fmc['key'] = 0
def fmc_ctl(val):
    if val & 0x80: fmc['unlocked'] = False; return val & ~0x40 | 0x80      # LK
    if val & 0x40:                              # START
        if val & 2:                             # PER: стирання сторінки за FMC_ADDR
            a = regs[FMC_ADDR] & ~(PAGE - 1)
            if fmc['allow'][0] and fmc['unlocked'] and 0x08000000 <= a < 0x08020000:
                uc.mem_write(a, b'\xff' * PAGE); uc.mem_write(a - 0x08000000, b'\xff' * PAGE); fmc['erases'] += 1; fmc['dirty'] = True
            else: fmc['denied'] += 1; regs[FMC_STAT] |= 1 << 4             # WPERR
        elif val & 4: fmc['denied'] += 1                                    # MER: не підтримується
    return val & ~0x40
def fmc_program(uc, addr, size, ud):          # перехоплення `strh r5,[r4]` у функції програмування (0x080143C8)
    a, v = uc.reg_read(UC_ARM_REG_R4), uc.reg_read(UC_ARM_REG_R5) & 0xFFFF
    if fmc['allow'][0] and fmc['unlocked'] and regs[FMC_CTL] & 1 and 0x08000000 <= a < 0x08020000 and not a & 1:
        old = struct.unpack('<H', bytes(uc.mem_read(a, 2)))[0]; nv = struct.pack('<H', old & v)   # flash лише скидає біти в 0
        uc.mem_write(a, nv); uc.mem_write(a - 0x08000000, nv); fmc['writes'] += 1; fmc['dirty'] = True
    else: fmc['denied'] += 1; regs[FMC_STAT] |= 1 << 2                    # PGERR
    uc.reg_write(UC_ARM_REG_PC, 0x080143CB)   # пропустити сам strh (Thumb)
def flash_image(): return bytes(uc.mem_read(FLASH, 0x20000))

def rtc_write(off, val):
    """RTC_TIME/RTC_DATE (BCD): прошивка (USB-команда «час», меню) записала нові значення → годинник емулятора їх приймає (раніше запис ігнорувався)."""
    bcd = lambda x: ((x >> 4) & 0xF) * 10 + (x & 0xF)
    d = clock.now()
    try:
        if off == 0x00: d = d.replace(hour=bcd((val >> 16) & 0x3F), minute=bcd((val >> 8) & 0x7F), second=bcd(val & 0x7F))
        else: d = d.replace(year=2000 + bcd((val >> 16) & 0xFF), month=bcd((val >> 8) & 0x1F), day=bcd(val & 0x3F))
    except ValueError: return                                                           # некоректна дата (31 лютого тощо) — ігноруємо
    clock.base = d; clock.t0 = cnt[0]

def mmio_write(uc, off, size, val, base):
    a = base + off
    if USB <= a < USB + 0x10000:
        if USBDBG and cnt[0] >= USBDBG: print('  usb W %04X <- %08X  pc=%08X t=%d' % (a - USB, val, uc.reg_read(UC_ARM_REG_PC), cnt[0]))
        usbfs.write(a - USB, size, val)
        # Переривання USBFS у залізі виникає одразу після запису в регістр (напр. EPENA у DIEPCTLn), а не «колись потім».
        # Без цього прошивка не встигає перекласти кадр зі стека у TX-FIFO — стек перезаписується (див. README).
        if not in_irq[0] and (nvic_en[0] >> USB_IRQ) & 1 and usbfs.irq():
            enter_exc(16 + USB_IRQ); uc.emu_stop()
        return
    if base == 0x40013800 and off == 0x28:      # USART1 TDR
        uart.append(val & 0xFF); uart_pending.append((cnt[0], val & 0xFF))
    if base == 0x40003800 and off == 0x0C:      # SPI1 DATA → дисплей
        lcd.byte(val & 0xFF)
    if base == 0x40002800 and off in (0x00, 0x04): rtc_write(off, val)                  # прошивка виставила час/дату
    if base == FMC:
        if off == 0x04: fmc_key(val)
        elif off == 0x10: val = fmc_ctl(val)
        elif off == 0x0C: regs[a] &= ~val; return                          # біти помилок скидаються записом 1
    if 0x48000000 <= base < 0x48002000:
        o = odr[base]
        if off == 0x14: o = val & 0xFFFF
        elif off == 0x18: o = (o | (val & 0xFFFF)) & ~(val >> 16)
        elif off == 0x28: o &= ~(val & 0xFFFF)
        odr[base] = o
    regs[a] = val
    if base == 0x40012400 and off == 0x08 and (val & 0x400000): adc_pend[0] = True       # SWRCST → EOC через IRQ12
    if base == 0x40002000 and off == 0x00 and (val & 1): t13_pend[0] = True              # TIMER13 стартував → вікно захоплення
    if base == 0x40020000 and off == 0x1C and (val & 1) and regs[0x40020024] == 0x40012C34: dma_capture()
    if base == 0x40000400 and off in (0x00, 0x18, 0x20, 0x28, 0x2C, 0x34): audio_update()   # TIMER2 CH0 = піщалка

for base in range(0x40000000, 0x40030000, 0x400):
    uc.mmio_map(base, 0x400, mmio_read, base, mmio_write, base)
for base in range(0x50000000, 0x50010000, 0x400):
    uc.mmio_map(base, 0x400, mmio_read, base, mmio_write, base)
for base in range(0x48000000, 0x48002000, 0x400):
    uc.mmio_map(base, 0x400, mmio_read, base, mmio_write, base)

# SCS / SysTick / NVIC
scs = collections.defaultdict(int)
vtor = [0]
nvic_en = [0]
SYST_CSR, SYST_RVR, SYST_CVR = 0xE000E010, 0xE000E014, 0xE000E018
idle = [False]                               # прошивка чекає SysTick (delay_ms) → решту такту емулятор не палить даремно
def scs_r(uc, off, size, ud):
    a = 0xE000E000 + off
    if a == SYST_CSR:
        v = scs[a]
        if v & 1:
            if cnt[0] != cnt[1]: v |= 1 << 16; cnt[1] = cnt[0]
            elif not idle[0] and not in_irq[0] and IDLE_SKIP: idle[0] = True; uc.emu_stop()    # COUNTFLAG з'явиться лише з наступною мс
    elif a == SYST_CVR: v = (scs[SYST_RVR] // 2) & 0xFFFFFF
    else: v = scs[a]
    return v & ((1 << (8 * size)) - 1)
def scs_w(uc, off, size, val, ud):
    a = 0xE000E000 + off
    if a == 0xE000ED08: vtor[0] = val
    if 0xE000E100 <= a < 0xE000E120: nvic_en[0] |= val << (32 * ((a - 0xE000E100) // 4))
    if 0xE000E180 <= a < 0xE000E1A0: nvic_en[0] &= ~(val << (32 * ((a - 0xE000E180) // 4)))
    if a == 0xE000ED04 and val & (1 << 28): scs['pendsv'] = 1
    scs[a] = val
uc.mmio_map(0xE000E000, 0x1000, scs_r, None, scs_w, None)
uc.mem_map(0xE0000000, 0x1000)  # DWT/ITM

# WFI/WFE/SEV -> NOP (Unicorn не вміє їх виконувати)
for _i in range(0, len(fw) - 1, 2):
    if fw[_i:_i + 2] in (b'\x30\xbf', b'\x20\xbf', b'\x40\xbf'):
        uc.mem_write(FLASH + _i, b'\x00\xbf'); uc.mem_write(_i, b'\x00\xbf')
sp, pc = struct.unpack('<II', fw[:8])
uc.reg_write(UC_ARM_REG_SP, sp)
uc.reg_write(UC_ARM_REG_PC, pc & ~1)

vec = lambda n: struct.unpack('<I', bytes(uc.mem_read(vtor[0] + 4 * n, 4)))[0]
in_irq = [0]
nextpc = [None]
def enter_exc(n):
    """Ручний вхід у виняток: збереження кадру і перехід у обробник."""
    h = vec(n)
    if not (h & 1 and 0x08000000 <= h < 0x08020000): return
    if n >= 17 and vtor[0] in (0, 0x08000000): return
    s = uc.reg_read(UC_ARM_REG_SP)
    pc_ = nextpc[0] if nextpc[0] else uc.reg_read(UC_ARM_REG_PC)
    xpsr = uc.reg_read(UC_ARM_REG_XPSR)
    frame = [uc.reg_read(r) for r in (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R12, UC_ARM_REG_LR)] + [pc_, xpsr]
    s -= 32
    uc.mem_write(s, struct.pack('<8I', *frame))
    uc.reg_write(UC_ARM_REG_SP, s)
    if os.environ.get('DBG'): print('inject', n, hex(h), 'vtor', hex(vtor[0]), 'pc', hex(pc_), 'xpsr', hex(xpsr))
    uc.reg_write(UC_ARM_REG_LR, 0x0F000001)
    nextpc[0] = h | 1
    in_irq[0] += 1

def tramp(uc, addr, size, ud):                # повернення з винятку
    s = uc.reg_read(UC_ARM_REG_SP)
    f = struct.unpack('<8I', uc.mem_read(s, 32))
    for r, v in zip((UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R12, UC_ARM_REG_LR), f[:6]):
        uc.reg_write(r, v)
    uc.reg_write(UC_ARM_REG_SP, s + 32)
    uc.reg_write(UC_ARM_REG_XPSR, f[7])
    nextpc[0] = f[6] | 1
    in_irq[0] -= 1
    uc.emu_stop()
uc.hook_add(UC_HOOK_CODE, tramp, None, 0x0F000000, 0x0F000001)

def gpio_readbit_hook(uc, addr, size, ud):    # GPIO_ReadBit(port=R0, mask=R1) у цій прошивці
    if uc.reg_read(UC_ARM_REG_R0) == 0x48000400:
        polled[uc.reg_read(UC_ARM_REG_R1)] += 1
uc.hook_add(UC_HOOK_CODE, gpio_readbit_hook, None, 0x08011922, 0x08011922)
uc.hook_add(UC_HOOK_CODE, fmc_program, None, 0x080143C8, 0x080143C8)

_seen_bad = set()
def bad(uc, access, addr, size, val, ud):
    if (access, addr) not in _seen_bad:
        _seen_bad.add((access, addr))
        print(f'[!] unmapped {access} @ {addr:#x} pc={uc.reg_read(UC_ARM_REG_PC):#x}')
    return False
uc.hook_add(UC_HOOK_MEM_UNMAPPED, bad)

def invalid(uc, ud):
    pc_ = uc.reg_read(UC_ARM_REG_PC)
    h = struct.unpack('<H', uc.mem_read(pc_, 2))[0]
    if h in (0xBF20, 0xBF30, 0xBF40):          # WFE / WFI / SEV — просто пропускаємо
        uc.reg_write(UC_ARM_REG_PC, pc_ + 2); return True
    return False
uc.hook_add(UC_HOOK_INSN_INVALID, invalid)

# ------------------------------------------------- один тік SysTick (1 мс ≈ 8000 інструкцій при 8 МГц)
TICK = 8000
IDLE_SKIP = not args.no_idle_skip
dead = [None]          # текст помилки, якщо емуляція впала

tick_acc = [0.0]; tick_pend = [0]
t13_pend = [False]; adc_pend = [False]
def deliver():
    """Доставити один відкладений IRQ (вкладених немає): TIMER13(19) — кінець вікна захоплення, ADC(12), TIMER1(15) — тік."""
    if in_irq[0]: return
    if t13_pend[0]:
        t13_pend[0] = False
        if (nvic_en[0] >> 19) & 1: enter_exc(16 + 19); return
    if adc_pend[0]:
        adc_pend[0] = False
        if (nvic_en[0] >> 12) & 1: enter_exc(16 + 12); return
    if tick_pend[0] > 0:
        tick_pend[0] -= 1
        if scs[SYST_CSR] & 2: enter_exc(15)
        elif (nvic_en[0] >> 15) & 1: enter_exc(16 + 15)
        return
    if (nvic_en[0] >> USB_IRQ) & 1 and usbfs.irq(): enter_exc(16 + USB_IRQ)       # USBFS

def run_slice(budget):
    remaining = budget
    while remaining > 0:
        pc_ = (nextpc[0] if nextpc[0] else uc.reg_read(UC_ARM_REG_PC)) | 1
        nextpc[0] = None
        uc.emu_start(pc_, 0xFFFFFFFF, count=remaining)
        if idle[0]: break
        if nextpc[0] is None: break          # шматок завершився природно
        remaining -= 200                     # зупинка через повернення з ISR

def run_tick():
    """1 мс емульованого часу = 4 шматки; TIMER1 дає тік кожні (PSC+1)(ARR+1)/48 МГц ≈ 2.78 мс."""
    try:
        if regs[0x40000000] & 1:                                   # TIMER1 (CEN) запущено
            per = (regs[0x40000028] + 1) * (regs[0x4000002C] + 1) / 48000.0   # період у мс
            tick_acc[0] = min(tick_acc[0] + 1.0 / max(per, 0.05), 3.0)
            if tick_acc[0] >= 1.0: tick_acc[0] -= 1.0; tick_pend[0] = min(tick_pend[0] + 1, 4)
        idle[0] = False
        for _ in range(4):
            run_slice(TICK // 4); deliver()
            if idle[0]: break
        cnt[0] += 1
        usb_host.tick()
        if SCHED: run_schedule()
    except UcError as e:
        dead[0] = 'UcError %s pc=%#x' % (e, uc.reg_read(UC_ARM_REG_PC))
        print('[!]', dead[0])

def save_png_or_ppm(path, rot):
    try:
        from PIL import Image
        im = Image.new('RGB', (LW, LH)); im.putdata([struct.unpack('3B', p) for row in rotated_rows(rot) for p in row])
        im.resize((LW * 2, LH * 2), Image.NEAREST).save(path); return path
    except Exception:
        path = os.path.splitext(path)[0] + '.ppm'
        open(path, 'wb').write(ppm(rot)); return path


# ================================================================= SRAM / ЗНІМКИ СТАНУ
SRAM_BASE, SRAM_REAL, SRAM_MAPPED = 0x20000000, 0x4000, 0x10000       # реально 16 КБ; решта замаплена «про запас»
oob = {'n': 0}
def _oob(uc, access, addr, size, val, ud):
    oob['n'] += 1
    if oob['n'] == 1: print(T('[!] доступ поза 16 КБ SRAM справжнього чипа @ {0:#x} pc={1:#x} (далі мовчки)').format(addr, uc.reg_read(UC_ARM_REG_PC)))
uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, _oob, None, SRAM_BASE + SRAM_REAL, SRAM_BASE + SRAM_MAPPED - 1)

FWID = zlib.crc32(fw)
CPU_REGS = [getattr(__import__('unicorn.arm_const', fromlist=['x']), 'UC_ARM_REG_R%d' % i) for i in range(13)] + [UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR]
STATE_MAGIC = 'PO80STATE2'

def snapshot():
    return dict(magic=STATE_MAGIC, fwcrc=FWID, ms=cnt[0],
        cpu=[uc.reg_read(r) for r in CPU_REGS], sram=bytes(uc.mem_read(SRAM_BASE, SRAM_MAPPED)),
        regs=dict(regs), odr=dict(odr), scs=dict(scs), vtor=vtor[0], nvic=nvic_en[0], in_irq=in_irq[0], nextpc=nextpc[0], cnt=list(cnt),
        tick=[tick_acc[0], tick_pend[0], t13_pend[0], adc_pend[0]], polled=dict(polled), uart=bytes(uart),
        lcd=dict(rows=b''.join(b''.join(r) for r in lcd.rows), cmd=lcd.cmd, params=list(lcd.params), pend=lcd.pend,
                 win=(lcd.x0, lcd.y0, lcd.x1, lcd.y1, lcd.cx, lcd.cy), madctl=lcd.madctl, ncmd=lcd.ncmd),
        clock=(clock.base.isoformat(), clock.t0), adc=ADC_VAL[0], capt_t=capt['t'],
        sensor={k: getattr(sensor, k) for k in ('finger', 'spo2', 'pr', 'pi', 'noise', 'hrv', 'ph', 't_prev', 'drift')})

def restore(st):
    if not isinstance(st, dict) or st.get('magic') != STATE_MAGIC: raise ValueError(T('це не файл стану цього емулятора'))
    if st['fwcrc'] != FWID: raise ValueError(T('стан збережено для іншої прошивки'))
    uc.mem_write(SRAM_BASE, st['sram'])
    for r, v in zip(CPU_REGS, st['cpu']): uc.reg_write(r, v)
    for dst, src in ((regs, st['regs']), (odr, st['odr']), (scs, st['scs']), (polled, st['polled'])): dst.clear(); dst.update(src)
    vtor[0] = st['vtor']; nvic_en[0] = st['nvic']; in_irq[0] = st['in_irq']; nextpc[0] = st['nextpc']; cnt[:] = st['cnt']
    tick_acc[0], tick_pend[0], t13_pend[0], adc_pend[0] = st['tick']
    uart[:] = st['uart']; dead[0] = None
    L = st['lcd']; raw = L['rows']
    lcd.rows = [[raw[(y * LW + x) * 3:(y * LW + x) * 3 + 3] for x in range(LW)] for y in range(LH)]
    lcd.cmd, lcd.params, lcd.pend, lcd.madctl, lcd.ncmd = L['cmd'], L['params'], L['pend'], L['madctl'], L['ncmd']
    lcd.x0, lcd.y0, lcd.x1, lcd.y1, lcd.cx, lcd.cy = L['win']; lcd.dirty = True
    clock.base = datetime.datetime.fromisoformat(st['clock'][0]); clock.t0 = st['clock'][1]
    ADC_VAL[0] = st['adc']; capt['t'] = st['capt_t']
    for k, v in st['sensor'].items(): setattr(sensor, k, v)
    usbfs.reset_queues(); usbfs.flags = 0; usb_host.stop()                           # USB: хост перепідключається (ресет шини), прошивка заново енумерується
    if usb_on[0]: usb_host.start(); usb_host.restored = True; usblog.add('info', T('USB: стан завантажено — перепідключення'))
    beeper.stop(); snd.update(on=False); beeper.events.clear(); audio_update()      # відновити піщалку, якщо стан збережено посеред сигналу
    for cb in GUI_SYNC: cb()

def save_state(path):
    with open(path, 'wb') as f: f.write(zlib.compress(pickle.dumps(snapshot(), protocol=4), 6))
def load_state(path):      # довіряйте лише власним файлам: pickle виконує код при розпаковці чужого файлу
    with open(path, 'rb') as f: restore(pickle.loads(zlib.decompress(f.read())))
def dump_sram(path):
    with open(path, 'wb') as f: f.write(bytes(uc.mem_read(SRAM_BASE, SRAM_REAL)))
def load_sram(path):
    d = open(path, 'rb').read()[:SRAM_MAPPED]; uc.mem_write(SRAM_BASE, d); return len(d)

# ---- «апаратне» скидання прошивки без перезапуску програми: повертаємо стан, зняти одразу після ініціалізації (до першого такту)
boot_snap = snapshot(); flash0 = bytes(uc.mem_read(FLASH, 0x20000))        # flash0 = оригінальний образ (з заміною WFI→NOP)
def soft_reset(use_current=True):
    """Скидання як по POR: CPU, SRAM, периферія, LCD, USB. Датчики/батарея/годинник лишаються як є.
    use_current=True — запускати поточний (можливо змінений) flash; False — повернути оригінальний flash.bin."""
    keep = {k: getattr(sensor, k) for k in boot_snap['sensor']}; adc = ADC_VAL[0]; now = clock.now()
    restore(boot_snap)
    for k, v in keep.items(): setattr(sensor, k, v)
    ADC_VAL[0] = adc; clock.base = now; clock.t0 = 0
    if not use_current:
        uc.mem_write(FLASH, flash0); uc.mem_write(0, flash0); fmc['dirty'] = False
    fmc['unlocked'] = False; fmc['key'] = 0; regs[FMC_CTL] = 0x80
    sp0, pc0 = struct.unpack('<II', bytes(uc.mem_read(FLASH, 8)))                 # вектор скидання з поточного flash
    uc.reg_write(UC_ARM_REG_SP, sp0); uc.reg_write(UC_ARM_REG_PC, pc0 & ~1)
def mem_write_live(space, addr, data):
    """Запис у пам'ять «наживо». space='sram' (0x20000000, 16 КБ) або 'flash' (0x08000000, 128 КБ; обходить FMC, дзеркало @0 теж оновлюється)."""
    if space == 'sram':
        if not (SRAM_BASE <= addr and addr + len(data) <= SRAM_BASE + SRAM_REAL): raise ValueError(T('поза SRAM (0x20000000–0x20003FFF)'))
        uc.mem_write(addr, data)
    else:
        if not (0x08000000 <= addr and addr + len(data) <= 0x08020000): raise ValueError(T('поза flash (0x08000000–0x0801FFFF)'))
        uc.mem_write(addr, data); uc.mem_write(addr - 0x08000000, data); fmc['dirty'] = True

if args.state and os.path.exists(args.state):
    try: load_state(args.state); print(T('стан завантажено:'), args.state, T('(t={0} мс)').format(cnt[0]))
    except Exception as e: print(T('[!] не вдалося завантажити стан:'), e)
if args.sram_load:
    try: print(T('SRAM завантажено, байт:'), load_sram(args.sram_load))
    except Exception as e: print('[!] SRAM:', e)

# ------------------------------------------------------------------ headless
if args.headless is not None:
    for _ in range(args.headless):
        run_tick()
        if dead[0]: break
    print(T('емульовано {0} мс, LCD-команд {1}, UART: {2!r}').format(cnt[0], lcd.ncmd, bytes(uart)[:200]))
    print(T('опитувані піни PB:'), {hex(k): v for k, v in polled.most_common(6)})
    rd8 = lambda a: bytes(uc.mem_read(a, 1))[0]
    print(T('датчики: SpO2={0:.0f}% PR={1:.0f} PI={2:.1f}% палець={3}  |  RAM прошивки: SpO2={4}').format(sensor.spo2, sensor.pr, sensor.pi, sensor.finger, rd8(536879396)))
    print(T('годинник RTC: {0:%H:%M:%S}   АЦП батареї={1} ({2:.2f} В) → рівень {3}').format(clock.now(), ADC_VAL[0], adc_to_volts(ADC_VAL[0]), T(bat_level(ADC_VAL[0]))))
    print(T('піщалка: {0} сигналів').format(len(beeper.events)), [(int(e[0]), int(e[1] or cnt[0]), round(e[2])) for e in beeper.events[:6]])
    print(T('USB: хост {0}; пакетів ПК→пристрій {1}, пристрій→ПК {2}, керуючих передач {3}; останні дані: {4}').format(T(usb_host.state), usb_stat['out'], usb_stat['in'], usb_stat['ctl'], usb_last or '—'))
    if args.usb_log:
        _txt = '\n'.join(UsbLog.fmt(r) for r in usblog.lines) + '\n'
        if args.usb_log == '-': print(T('--- USB-журнал ---')); print(_txt, end='')
        else: open(args.usb_log, 'w', encoding='utf-8').write(_txt); print(T('USB-журнал:'), args.usb_log)
    print(T('flash: дозвіл={0} стирань={1} записів(півслів)={2} відхилено={3}').format(fmc['allow'][0], fmc['erases'], fmc['writes'], fmc['denied']))
    if args.flash_out: open(args.flash_out, 'wb').write(flash_image()); print(T('flash збережено:'), args.flash_out)
    if args.wav: beeper.render_wav(args.wav, cnt[0]); print(T('звук:'), args.wav)
    if args.state: save_state(args.state); print(T('стан збережено:'), args.state)
    if args.sram_dump: dump_sram(args.sram_dump); print(T('SRAM збережено:'), args.sram_dump)
    print(T('знімок:'), save_png_or_ppm(args.shot, args.rot))
    sys.exit(0)

# ------------------------------------------------------------------ GUI
import tkinter as tk
from tkinter import ttk

root = tk.Tk()
root.title(T('Beurer PO 80 — емулятор прошивки'))
root.configure(bg='#1e1e1e')
rot = [args.rot % 4]
scale = [max(1, min(4, args.scale))]
paused = [False]
speed = [1.0]                         # None = максимально швидко
sync = {'t': time.perf_counter(), 'ms': 0}
last_render = [0.0]
photo = {'raw': None, 'disp': None}

left = tk.Frame(root, bg='#1e1e1e'); left.grid(row=0, column=0, padx=10, pady=10, sticky='ns'); root.grid_rowconfigure(0, weight=1)
canvas = tk.Canvas(left, width=LW * scale[0], height=LH * scale[0], bg='black', highlightthickness=2, highlightbackground='#555')
canvas.pack(anchor='n')
img_item = canvas.create_image(0, 0, anchor='nw')

side = tk.Frame(root, bg='#1e1e1e'); side.grid(row=0, column=1, padx=(0, 10), pady=10, sticky='ns')
btn_w = {}

def refresh_btn(pin):
    b = btn_w[pin]; on = pin in held or pin in latched
    b.config(relief='sunken' if on else 'raised', bg='#3a7d3a' if pin in latched else ('#6a9fd8' if on else '#d9d9d9'))
def press(pin): held.add(pin); refresh_btn(pin)
def release(pin): held.discard(pin); refresh_btn(pin)
def toggle_latch(pin):
    latched.symmetric_difference_update({pin}); refresh_btn(pin)

tk.Label(side, text=T('Кнопки (ЛКМ — тримати, ПКМ — залипання)'), bg='#1e1e1e', fg='#ccc').pack(anchor='w')
for i, (pin, name) in enumerate(BTNS):
    b = tk.Button(side, text=f'[{i + 1}]  {T(name)}  (PB{pin})', width=24, height=2)
    b.bind('<ButtonPress-1>', lambda e, p=pin: press(p))
    b.bind('<ButtonRelease-1>', lambda e, p=pin: release(p))
    b.bind('<Button-3>', lambda e, p=pin: toggle_latch(p))
    b.pack(pady=2, fill='x'); btn_w[pin] = b

def set_rot(d=1): rot[0] = (rot[0] + d) % 4; lcd.dirty = True; last_render[0] = 0
def set_scale(d):
    scale[0] = max(1, min(4, scale[0] + d)); lcd.dirty = True; last_render[0] = 0
    canvas.config(width=LW * scale[0], height=LH * scale[0])
def toggle_pause():
    paused[0] = not paused[0]; pause_btn.config(text=T('▶ Продовжити (Пробіл)') if paused[0] else T('⏸ Пауза (Пробіл)')); resync()
def resync(): sync['t'] = time.perf_counter(); sync['ms'] = cnt[0]
def do_shot():
    f = f'shot_{cnt[0]}ms.png'
    try: photo['raw'].write(f, format='png'); status_msg.set(T('збережено ') + f)
    except Exception as e: status_msg.set(T('скріншот не вдався: {0}').format(e))
def do_reset():
    a, out, skip = sys.argv[:], [], False
    for x in a:                                  # перезапуск «з нуля»: без --state
        if skip: skip = False; continue
        if x == '--state': skip = True; continue
        if x.startswith('--state='): continue
        out.append(x)
    os.execv(sys.executable, [sys.executable] + out)

ctl = tk.Frame(side, bg='#1e1e1e'); ctl.pack(pady=(10, 0), fill='x')
tk.Button(ctl, text=T('⟳ Повернути екран (R)'), command=set_rot).pack(fill='x', pady=1)
tk.Button(ctl, text='🔍+ (+)', command=lambda: set_scale(1)).pack(side='left', expand=True, fill='x')
tk.Button(ctl, text='🔍− (−)', command=lambda: set_scale(-1)).pack(side='left', expand=True, fill='x')
pause_btn = tk.Button(side, text=T('⏸ Пауза (Пробіл)'), command=toggle_pause); pause_btn.pack(fill='x', pady=1)
tk.Button(side, text=T('📷 Скріншот (S)'), command=do_shot).pack(fill='x', pady=1)
flash_run = tk.StringVar(value='current')
def do_soft_reset():
    soft_reset(flash_run.get() == 'current'); _after_load()
    status_msg.set(T('прошивку перезапущено (flash: %s)') % (T('поточний') + (T(', змінений') if fmc['dirty'] else '') if flash_run.get() == 'current' else T('оригінальний')))
tk.Button(side, text=T('↺ Перезапуск прошивки'), command=do_soft_reset).pack(fill='x', pady=1)
for _v, _t in (('current', T('запустити поточний flash (з моїми змінами)')), ('orig', T('запустити оригінальний flash.bin'))):
    tk.Radiobutton(side, text=_t, variable=flash_run, value=_v, bg='#1e1e1e', fg='#ccc', selectcolor='#333', activebackground='#1e1e1e',
                   activeforeground='#fff', font=('Segoe UI', 8), anchor='w').pack(fill='x')
tk.Button(side, text=T('⟳ Перезапуск програми (повний)'), command=do_reset, font=('Segoe UI', 8)).pack(fill='x', pady=(2, 1))

sp_f = tk.Frame(side, bg='#1e1e1e'); sp_f.pack(fill='x', pady=(8, 0))
tk.Label(sp_f, text=T('Швидкість:'), bg='#1e1e1e', fg='#ccc').pack(side='left')
SPEEDS = [('1×', 1.0), ('2×', 2.0), ('5×', 5.0), ('20×', 20.0), ('Макс', None)]
cb = ttk.Combobox(sp_f, values=[T(k) for k, _ in SPEEDS], width=6, state='readonly'); cb.current(0); cb.pack(side='left', padx=6)
def on_speed(_=None): speed[0] = SPEEDS[cb.current()][1]; resync()
cb.bind('<<ComboboxSelected>>', on_speed)

# ------------------------------------------------ панель датчиків (друга колонка)
side2 = tk.Frame(root, bg='#1e1e1e'); side2.grid(row=0, column=2, padx=(0, 10), pady=10, sticky='n')
def _lbl(t, pad=(8, 0)): tk.Label(side2, text=t, bg='#1e1e1e', fg='#ccc').pack(anchor='w', pady=pad)
def _scale(title, frm, to, res, attr, init):
    _lbl(title)
    sc = tk.Scale(side2, from_=frm, to=to, resolution=res, orient='horizontal', length=250, command=lambda v: setattr(sensor, attr, float(v)))
    sc.set(init); sc.pack(fill='x'); return sc
tk.Label(side2, text=T('ДАТЧИКИ (прошивка сама обробляє сигнал)'), bg='#1e1e1e', fg='#fc6').pack(anchor='w')
fin_var = tk.BooleanVar(value=sensor.finger)
tk.Checkbutton(side2, text=T('☝ Палець у датчику'), variable=fin_var, bg='#1e1e1e', fg='#ccc', selectcolor='#333', activebackground='#1e1e1e',
               command=lambda: setattr(sensor, 'finger', fin_var.get())).pack(anchor='w')
sc_spo2 = _scale('SpO2, %', 40, 100, 1, 'spo2', sensor.spo2)
sc_pr = _scale(T('Пульс, уд/хв'), 30, 250, 1, 'pr', sensor.pr)
sc_pi = _scale(T('Перфузія (розмах хвилі), %'), 0.1, 10, 0.1, 'pi', sensor.pi)
sc_noise = _scale(T('Шум / рух, %'), 0, 100, 1, 'noise', sensor.noise)
hrv_var = tk.BooleanVar(value=sensor.hrv)
tk.Checkbutton(side2, text=T('Варіабельність ритму'), variable=hrv_var, bg='#1e1e1e', fg='#ccc', selectcolor='#333', activebackground='#1e1e1e',
               command=lambda: setattr(sensor, 'hrv', hrv_var.get())).pack(anchor='w')

bat_txt = tk.StringVar()
def on_bat(v):
    ADC_VAL[0] = volts_to_adc(float(v))
    bat_txt.set(T('АЦП={0}  рівень: {1}').format(ADC_VAL[0], T(bat_level(ADC_VAL[0]))))
_lbl(T('Батарея, В (оцінка за дільником 1:2)'), (12, 0))
sc_bat = tk.Scale(side2, from_=3.2, to=4.3, resolution=0.01, orient='horizontal', length=250, command=on_bat)
sc_bat.set(round(adc_to_volts(ADC_VAL[0]), 2)); sc_bat.pack(fill='x')
tk.Label(side2, textvariable=bat_txt, bg='#1e1e1e', fg='#9c9', font=('Consolas', 9)).pack(anchor='w')
bf = tk.Frame(side2, bg='#1e1e1e'); bf.pack(fill='x')
for _n, _v in ((T('Повна'), 4.2), (T('Середня'), 3.9), (T('Низька'), 3.6), (T('Розряд'), 3.4)):
    tk.Button(bf, text=_n, command=lambda v=_v: sc_bat.set(v)).pack(side='left', expand=True, fill='x')

_lbl(T('Годинник RTC (ГГ:ХХ:СС)'), (12, 0))
tf = tk.Frame(side2, bg='#1e1e1e'); tf.pack(fill='x')
time_var = tk.StringVar(value=f'{clock.now():%H:%M:%S}')
ent = tk.Entry(tf, textvariable=time_var, width=10); ent.pack(side='left')
def set_time():
    try:
        p = [int(x) for x in time_var.get().split(':')] + [0, 0]
        clock.set(p[0] % 24, p[1] % 60, p[2] % 60); status_msg.set(T('час встановлено; екран оновить його при наступному читанні RTC (≤ 60 с)'))
    except Exception: status_msg.set(T('формат часу: ГГ:ХХ:СС'))
def pc_time():
    n = datetime.datetime.now(); clock.set(n.hour, n.minute, n.second); time_var.set(f'{n:%H:%M:%S}')
tk.Button(tf, text=T('Встановити'), command=set_time).pack(side='left', padx=3)
tk.Button(tf, text=T('Час ПК'), command=pc_time).pack(side='left')
tk.Label(side2, text=T('Прошивка перечитує RTC раз на ~60 с (як на реальному пристрої)'), bg='#1e1e1e', fg='#888', font=('Segoe UI', 8)).pack(anchor='w')

mute_var = tk.BooleanVar(value=beeper.enabled and beeper.backend is not None)
def on_mute():
    beeper.enabled = mute_var.get()
    if not beeper.enabled: beeper.stop(now=True)
snd_row = tk.Frame(side2, bg='#1e1e1e'); snd_row.pack(anchor='w', pady=(12, 0))
tk.Checkbutton(snd_row, text=T('🔊 Звук піщалки'), variable=mute_var, command=on_mute, bg='#1e1e1e', fg='#ccc', selectcolor='#333',
               activebackground='#1e1e1e').pack(side='left')
flash_var = tk.BooleanVar(value=fmc['allow'][0]); flash_info = tk.StringVar()
def on_flash(): fmc['allow'][0] = flash_var.get()
tk.Checkbutton(snd_row, text=T('✏ Дозволити запис у flash'), variable=flash_var, command=on_flash, bg='#1e1e1e', fg='#ccc', selectcolor='#333',
               activebackground='#1e1e1e').pack(side='left', padx=(8, 0))
snd_var = tk.StringVar()
def snd_label():
    t = T('звуковий бекенд: ') + (beeper.backend or T('немає (pip install sounddevice)'))
    return t + (T('\nпомилка: ') + beeper.err if beeper.err else '')
tk.Label(side2, textvariable=snd_var, bg='#1e1e1e', fg='#888', font=('Segoe UI', 8), justify='left', wraplength=300).pack(anchor='w')
def test_beep():
    beeper.enabled = True; mute_var.set(True)
    beeper.start(2500, 0.5); root.after(400, beeper.stop)
tk.Label(side2, textvariable=flash_info, bg='#1e1e1e', fg='#888', font=('Segoe UI', 8), justify='left', wraplength=300).pack(anchor='w')
btn_row = tk.Frame(side2, bg='#1e1e1e'); btn_row.pack(anchor='w', pady=2)
tk.Button(btn_row, text=T('🔔 Тест звуку (2500 Гц)'), command=test_beep).pack(side='left')
tk.Button(btn_row, text=T('💾 flash → файл…'), command=lambda: save_flash()).pack(side='left', padx=(4, 0))

def save_flash():
    from tkinter import filedialog
    fn = filedialog.asksaveasfilename(title=T('Зберегти образ flash'), defaultextension='.bin', initialfile='flash_modified.bin', filetypes=[('BIN', '*.bin'), (T('Усі'), '*.*')])
    if fn:
        try: open(fn, 'wb').write(flash_image()); status_msg.set(T('flash збережено: ') + fn)
        except Exception as e: status_msg.set(T('помилка: {0}').format(e))
def flash_label():
    return T('запис: %d півслів, стирань: %d%s%s') % (fmc['writes'], fmc['erases'], T(', відхилено: %d') % fmc['denied'] if fmc['denied'] else '', T('  (змінено)') if fmc['dirty'] else '')

def _sync_gui():
    fin_var.set(sensor.finger); hrv_var.set(sensor.hrv); sc_spo2.set(sensor.spo2); sc_pr.set(sensor.pr); sc_pi.set(sensor.pi); sc_noise.set(sensor.noise)
    sc_bat.set(round(adc_to_volts(ADC_VAL[0]), 2))
GUI_SYNC.append(_sync_gui)

status = tk.StringVar(); status_msg = tk.StringVar()
tk.Label(side, textvariable=status, bg='#1e1e1e', fg='#9c9', justify='left', anchor='w', font=('Consolas', 9), width=64, wraplength=440).pack(anchor='w', pady=(8, 0))
tk.Label(side, textvariable=status_msg, bg='#1e1e1e', fg='#fc6', justify='left', anchor='w', wraplength=440).pack(anchor='w')


# ---------------------------------------------------------------- пам'ять / стан (GUI)
from tkinter import filedialog
def _lbl2(t, pad=(12, 0)): tk.Label(side2, text=t, bg='#1e1e1e', fg='#ccc').pack(anchor='w', pady=pad)
_lbl2(T("ПАМ'ЯТЬ І СТАН"))
def _after_load(): lcd.dirty = True; last_render[0] = 0; resync(); uart_reset()
def gui_save_state():
    p = filedialog.asksaveasfilename(defaultextension='.po80state', filetypes=[(T('Стан емулятора'), '*.po80state'), (T('Усі файли'), '*.*')])
    if p: save_state(p); status_msg.set(T('стан збережено: ') + os.path.basename(p))
def gui_load_state():
    p = filedialog.askopenfilename(filetypes=[(T('Стан емулятора'), '*.po80state'), (T('Усі файли'), '*.*')])
    if not p: return
    try: load_state(p); _after_load(); status_msg.set(T('стан завантажено: ') + os.path.basename(p))
    except Exception as e: status_msg.set(T('помилка: {0}').format(e))
def quick_save(_e=None): save_state('quicksave.po80state'); status_msg.set(T('F5: збережено quicksave.po80state (t={0:.1f} с)').format(cnt[0] / 1000))
def quick_load(_e=None):
    try: load_state('quicksave.po80state'); _after_load(); status_msg.set(T('F9: завантажено quicksave.po80state'))
    except Exception as e: status_msg.set(f'F9: {e}')
def gui_dump_sram():
    p = filedialog.asksaveasfilename(defaultextension='.bin', initialfile='sram.bin')
    if p: dump_sram(p); status_msg.set(T('SRAM ({0} КБ) → {1}').format(SRAM_REAL // 1024, os.path.basename(p)))
def gui_load_sram():
    p = filedialog.askopenfilename(filetypes=[(T('Дамп SRAM'), '*.bin'), (T('Усі файли'), '*.*')])
    if p:
        try: n = load_sram(p); status_msg.set(T('{0} байт записано в SRAM (прошивка бачить зміни одразу)').format(n))
        except Exception as e: status_msg.set(T('помилка: {0}').format(e))
for _t, _c in ((T('💾 Зберегти стан (F5 — швидко)'), gui_save_state), (T('📂 Завантажити стан (F9 — швидко)'), gui_load_state),
               (T('SRAM → файл .bin'), gui_dump_sram), (T('Файл .bin → SRAM'), gui_load_sram)):
    tk.Button(side2, text=_t, command=_c).pack(fill='x', pady=1)
root.bind('<F5>', quick_save); root.bind('<F9>', quick_load)

viewer = {'win': None}
SPACES = {'sram': (SRAM_BASE, SRAM_REAL, 'SRAM 0x20000000–0x20003FFF'), 'flash': (0x08000000, 0x20000, 'Flash 0x08000000–0x0801FFFF')}
def parse_bytes(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"': return s[1:-1].encode('latin-1')           # "текст" → ASCII
    out = bytearray()
    for tok in s.replace(',', ' ').split():
        tok = tok[2:] if tok.lower().startswith('0x') else tok
        if len(tok) % 2: tok = '0' + tok
        out += bytes.fromhex(tok)
    return bytes(out)
def open_viewer():
    if viewer['win'] and viewer['win'].winfo_exists(): viewer['win'].lift(); return
    w = tk.Toplevel(root); w.title(T("Редактор пам'яті (SRAM / Flash) — наживо")); w.configure(bg='#1e1e1e'); viewer['win'] = w
    sp = tk.StringVar(value='sram'); auto = tk.BooleanVar(value=True); freeze = tk.BooleanVar(value=False)
    st = {'shown': None, 'frozen': None}
    top = tk.Frame(w, bg='#1e1e1e'); top.pack(fill='x')
    def _rb(text, val): tk.Radiobutton(top, text=text, variable=sp, value=val, command=lambda: (st.update(shown=None), refresh(force=True)), bg='#1e1e1e', fg='#ccc',
                                       selectcolor='#333', activebackground='#1e1e1e').pack(side='left')
    _rb('SRAM', 'sram'); _rb('Flash', 'flash')
    tk.Checkbutton(top, text=T('автооновлення'), variable=auto, bg='#1e1e1e', fg='#ccc', selectcolor='#333', activebackground='#1e1e1e').pack(side='left', padx=(10, 0))
    tk.Label(top, text=T('перейти до адреси:'), bg='#1e1e1e', fg='#ccc').pack(side='left', padx=(10, 2))
    ge = tk.Entry(top, width=10); ge.insert(0, '20002124'); ge.pack(side='left')
    ed = tk.Frame(w, bg='#1e1e1e'); ed.pack(fill='x', pady=(4, 0))
    tk.Label(ed, text=T('адреса:'), bg='#1e1e1e', fg='#ccc').pack(side='left')
    ae = tk.Entry(ed, width=10); ae.insert(0, '20002124'); ae.pack(side='left', padx=(2, 8))
    tk.Label(ed, text=T('нові байти (hex: DE AD BE EF   або   "текст"):'), bg='#1e1e1e', fg='#ccc').pack(side='left')
    ve = tk.Entry(ed, width=28); ve.pack(side='left', padx=2)
    msg = tk.StringVar(value=T('клік по байту — підставити адресу й поточне значення; Enter — записати'))
    def cur(): return SPACES[sp.get()]
    def do_write(_e=None):
        try:
            a = int(ae.get().replace('0x', ''), 16); d = parse_bytes(ve.get())
            if not d: raise ValueError(T('порожнє значення'))
            mem_write_live(sp.get(), a, d)
            if freeze.get() and sp.get() == 'sram': st['frozen'] = (a, d)
            msg.set(T('записано %d байт @ %08X%s') % (len(d), a, T(' (flash змінено напряму, минаючи FMC)') if sp.get() == 'flash' else ''))
            refresh(force=True)
        except Exception as e: msg.set(T('помилка: %s') % e)
    ve.bind('<Return>', do_write); ae.bind('<Return>', do_write)
    tk.Button(ed, text=T('Записати'), command=do_write).pack(side='left', padx=3)
    tk.Checkbutton(ed, text=T('тримати значення (SRAM)'), variable=freeze, command=lambda: st.update(frozen=None) if not freeze.get() else None,
                   bg='#1e1e1e', fg='#ccc', selectcolor='#333', activebackground='#1e1e1e').pack(side='left')
    tk.Label(w, textvariable=msg, bg='#1e1e1e', fg='#fc6', anchor='w').pack(fill='x')
    body = tk.Frame(w, bg='#1e1e1e'); body.pack(fill='both', expand=True)
    txt = tk.Text(body, width=78, height=34, bg='#101010', fg='#9c9', font=('Consolas', 10), wrap='none'); txt.pack(side='left', fill='both', expand=True)
    sb = tk.Scrollbar(body, command=txt.yview); sb.pack(side='right', fill='y'); txt.config(yscrollcommand=sb.set)
    txt.tag_config('chg', foreground='#ff5555', background='#401010')
    def goto(_e=None):
        try:
            base, size, _ = cur(); a = int(ge.get(), 16) - base
            txt.see(f'{a // 16 + 1}.0'); txt.yview_moveto(max(0, (a // 16 - 3)) / (size // 16))
        except Exception: pass
    ge.bind('<Return>', goto); tk.Button(top, text=T('Йти'), command=goto).pack(side='left', padx=3)
    def pick(e):
        try:
            ln, col = [int(x) for x in txt.index('@%d,%d' % (e.x, e.y)).split('.')]
            i = min(15, max(0, (col - 10) // 3)); base, size, _ = cur(); a = base + (ln - 1) * 16 + i
            if a >= base + size: return
            ae.delete(0, 'end'); ae.insert(0, '%08X' % a); ve.delete(0, 'end'); ve.insert(0, '%02X' % bytes(uc.mem_read(a, 1))[0])
        except Exception: pass
    txt.bind('<ButtonRelease-1>', pick)
    def refresh(force=False):
        if not w.winfo_exists(): return
        if auto.get() or force:
            base, size, title = cur(); w.title(T("Редактор пам'яті — ") + title)
            data = bytes(uc.mem_read(base, size)); prev = st['shown']
            if data != prev:
                y0 = txt.yview()[0]
                rows = [f'{base + i:08X}  ' + ' '.join('%02X' % b for b in data[i:i + 16]) + '  ' + ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i + 16])
                        for i in range(0, size, 16)]
                txt.delete('1.0', 'end'); txt.insert('1.0', '\n'.join(rows))
                if prev:
                    for i in [i for i in range(size) if data[i] != prev[i]]:
                        c = 10 + (i % 16) * 3; txt.tag_add('chg', f'{i // 16 + 1}.{c}', f'{i // 16 + 1}.{c + 2}')
                st['shown'] = data; txt.yview_moveto(y0)
    def tick():
        if not w.winfo_exists(): return
        refresh(); w.after(1000, tick)
    def hold():                                          # «тримати значення»: SRAM-діапазон перезаписується кожні 50 мс
        if not w.winfo_exists(): return
        if freeze.get() and st['frozen']:
            try: mem_write_live('sram', *st['frozen'])
            except Exception: pass
        w.after(50, hold)
    refresh(force=True); w.after(1000, tick); hold()
mem_row = tk.Frame(side2, bg='#1e1e1e'); mem_row.pack(anchor='w', pady=1)
tk.Button(mem_row, text=T("🧠 Редактор пам'яті (SRAM / Flash)"), command=open_viewer).pack(side='left')
tk.Label(mem_row, text='🌐', bg='#1e1e1e', fg='#ccc').pack(side='left', padx=(8, 2))
LANG_NAMES = {'English': 'en', 'Українська': 'uk'}
lang_cb = ttk.Combobox(mem_row, values=list(LANG_NAMES), width=10, state='readonly'); lang_cb.set('English' if LANG == 'en' else 'Українська'); lang_cb.pack(side='left')
def _walk(w):
    yield w
    for c in w.winfo_children(): yield from _walk(c)
def apply_lang(l):
    """Перемкнути мову «наживо»: статичні написи знаходимо за зворотним словником, динамічні (статус, журнали) оновляться самі."""
    set_lang(l)
    for w in _walk(root):
        try: txt = w.cget('text')
        except Exception: continue
        if not isinstance(txt, str) or not txt: continue
        new = T(REV.get(txt, txt))
        if new != txt:
            try: w.config(text=new)
            except Exception: pass
    root.title(T('Beurer PO 80 — емулятор прошивки'))
    for i, (pin, name) in enumerate(BTNS): btn_w[pin].config(text=f'[{i + 1}]  {T(name)}  (PB{pin})')
    k = cb.current(); cb.config(values=[T(s) for s, _ in SPEEDS]); cb.current(k)
    lcd.dirty = True; last_render[0] = 0
    status_msg.set('')
def on_lang(_=None): apply_lang(LANG_NAMES[lang_cb.get()])
lang_cb.bind('<<ComboboxSelected>>', on_lang)
# ---------------------------------------------------------------- USB-журнал під екраном
from tkinter import filedialog as _fd
BG = '#1e1e1e'
logf = tk.Frame(left, bg=BG); logf.pack(fill='both', expand=True, pady=(8, 0))
_h1 = tk.Frame(logf, bg=BG); _h1.pack(fill='x')
tk.Label(_h1, text=T('USB-журнал'), bg=BG, fg='#fc6', font=('Segoe UI', 9, 'bold')).pack(side='left')
usb_state = tk.StringVar()
tk.Label(_h1, textvariable=usb_state, bg=BG, fg='#9c9', font=('Consolas', 9)).pack(side='left', padx=8)
_h2 = tk.Frame(logf, bg=BG); _h2.pack(fill='x')
cable_var = tk.BooleanVar(value=usb_on[0]); show_ctl = tk.BooleanVar(value=True); show_wave = tk.BooleanVar(value=True); full_var = tk.BooleanVar(value=False); autoscroll = tk.BooleanVar(value=True)
def _chk(parent, text, var, cmd=None):
    tk.Checkbutton(parent, text=text, variable=var, command=cmd, bg=BG, fg='#ccc', selectcolor='#333', activebackground=BG, activeforeground='#fff',
                   font=('Segoe UI', 8)).pack(side='left', padx=(0, 4))
_chk(_h2, T('кабель USB'), cable_var, lambda: usb_plug(cable_var.get()))
_chk(_h2, T('енумерація'), show_ctl, lambda: usb_rebuild())
_chk(_h2, T('хвиля/ZLP'), show_wave, lambda: usb_rebuild())
_chk(_h2, T('повні пакети'), full_var, lambda: usb_full.__setitem__(0, full_var.get()))
_chk(_h2, T('автопрокрутка'), autoscroll)
usb_txt = tk.Text(logf, width=10, height=8, bg='#101010', fg='#cfcfcf', font=('Consolas', 9), wrap='word', state='disabled', borderwidth=0,
                  highlightthickness=1, highlightbackground='#444', insertbackground='#fff', selectbackground='#335')
usb_sb = tk.Scrollbar(logf, command=usb_txt.yview); usb_txt.config(yscrollcommand=usb_sb.set)
usb_sb.pack(side='right', fill='y'); usb_txt.pack(side='left', fill='both', expand=True, pady=(2, 0))
for _k, _c in (('in', '#7CFC7C'), ('wave', '#4a8a4a'), ('out', '#6FB5FF'), ('ctl', '#8a8a8a'), ('info', '#E0C060'), ('err', '#FF6B6B')): usb_txt.tag_config(_k, foreground=_c)
usb_pending = []; usb_ui = {'t': 0.0}
usblog.listeners.append(usb_pending.append)
def _usb_insert(recs):
    recs = [r for r in recs if (show_ctl.get() or r[1] != 'ctl') and (show_wave.get() or r[1] != 'wave')]
    if not recs: return
    usb_txt.config(state='normal')
    for r in recs[-600:]: usb_txt.insert('end', UsbLog.fmt(r) + '\n', r[1])
    n = int(usb_txt.index('end-1c').split('.')[0])
    if n > 3000: usb_txt.delete('1.0', '%d.0' % (n - 2500))
    usb_txt.config(state='disabled')
    if autoscroll.get(): usb_txt.see('end')
def usb_flush(now):
    if usb_pending and now - usb_ui['t'] > 0.1:
        recs = usb_pending[:]; del usb_pending[:]; usb_ui['t'] = now; _usb_insert(recs)
def usb_rebuild():
    del usb_pending[:]; usb_txt.config(state='normal'); usb_txt.delete('1.0', 'end'); usb_txt.config(state='disabled'); _usb_insert(usblog.lines[-1500:])
def usb_clear():
    del usb_pending[:]; usblog.lines.clear(); usb_stat.clear(); usb_txt.config(state='normal'); usb_txt.delete('1.0', 'end'); usb_txt.config(state='disabled')
def usb_save():
    p = _fd.asksaveasfilename(defaultextension='.txt', initialfile='usb_log.txt', filetypes=[(T('Текст'), '*.txt'), (T('Усі файли'), '*.*')])
    if p:
        with open(p, 'w', encoding='utf-8') as f: f.write('\n'.join(UsbLog.fmt(r) for r in usblog.lines) + '\n')
        status_msg.set(T('USB-журнал збережено: ') + os.path.basename(p))
tk.Button(_h2, text=T('Очистити'), command=usb_clear, font=('Segoe UI', 8), padx=4, pady=0).pack(side='right', padx=1)
tk.Button(_h2, text=T('Зберегти…'), command=usb_save, font=('Segoe UI', 8), padx=4, pady=0).pack(side='right', padx=1)
_usb_insert(usblog.lines[-1500:])

# ---------------------------------------------------------------- UART-журнал (середня колонка, під статусом)
uartf = tk.Frame(side, bg=BG); uartf.pack(fill='both', expand=True, pady=(10, 0))
_u1 = tk.Frame(uartf, bg=BG); _u1.pack(fill='x')
tk.Label(_u1, text=T('UART-журнал'), bg=BG, fg='#fc6', font=('Segoe UI', 9, 'bold')).pack(side='left')
uart_state = tk.StringVar(value=T('TX: 0 Б'))
tk.Label(_u1, textvariable=uart_state, bg=BG, fg='#9c9', font=('Consolas', 9)).pack(side='left', padx=8)
_u2 = tk.Frame(uartf, bg=BG); _u2.pack(fill='x')
uart_ascii = tk.BooleanVar(value=True); uart_auto = tk.BooleanVar(value=True)
_chk(_u2, 'ASCII', uart_ascii, lambda: uart_rebuild())
_chk(_u2, T('автопрокрутка'), uart_auto)
uart_txt = tk.Text(uartf, width=10, height=8, bg='#101010', fg='#cfcfcf', font=('Consolas', 9), wrap='none', state='disabled', borderwidth=0,
                   highlightthickness=1, highlightbackground='#444', insertbackground='#fff', selectbackground='#335')
uart_sb = tk.Scrollbar(uartf, command=uart_txt.yview); uart_txt.config(yscrollcommand=uart_sb.set)
uart_sb.pack(side='right', fill='y'); uart_txt.pack(side='left', fill='both', expand=True, pady=(2, 0))
uart_txt.tag_config('data', foreground='#7CFC7C'); uart_txt.tag_config('crc', foreground='#E0C060')
uart_recs = []                                   # [(мс, bytes)] — «пачки» байтів, розділені паузою > 30 мс
uart_grp = {'t': 0, 'tl': 0, 'b': bytearray()}; uart_n = [0]
def _uart_fmt(rec):
    t, d = rec; rows = [d[i:i + 8] for i in range(0, len(d), 8)]
    crc = len(d) >= 2 and d[0] & 0x80 and (sum(d[:-1]) & 0x7F) == d[-1]      # кадр пристрою: CRC = сума попередніх байтів & 0x7F
    out = []
    for i, r in enumerate(rows):
        asc = ''.join(chr(x) if 32 <= x < 127 else '.' for x in r) if uart_ascii.get() else ''
        out.append((('%8.3f' % (t / 1000.0) if i == 0 else ' ' * 8) + '  ' + ' '.join('%02X' % x for x in r).ljust(23) + ('  ' + asc if asc else '')).rstrip()
                   + ('   CRC7 ✓' if crc and i == len(rows) - 1 else ''))
    return out
def _uart_insert(recs):
    if not recs: return
    uart_txt.config(state='normal')
    for rec in recs:
        for ln in _uart_fmt(rec): uart_txt.insert('end', ln + '\n', 'crc' if ln.endswith('CRC7 ✓') else 'data')
    n = int(uart_txt.index('end-1c').split('.')[0])
    if n > 3000: uart_txt.delete('1.0', '%d.0' % (n - 2500))
    uart_txt.config(state='disabled')
    if uart_auto.get(): uart_txt.see('end')
def _uart_emit():
    g = uart_grp; rec = (g['t'], bytes(g['b'])); g['b'] = bytearray()
    uart_recs.append(rec); del uart_recs[:-1500]; _uart_insert([rec])
def uart_flush():
    g = uart_grp; got = False
    while uart_pending:
        t, b = uart_pending.popleft(); got = True; uart_n[0] += 1
        if g['b'] and (t - g['tl'] > 30 or len(g['b']) >= 32): _uart_emit()
        if not g['b']: g['t'] = t
        g['b'].append(b); g['tl'] = t
    if g['b'] and (paused[0] or cnt[0] - g['tl'] > 30): _uart_emit()          # пачку закриває пауза між байтами
    if got or not uart_n[0]: uart_state.set(T('TX: {0} Б').format(uart_n[0]))
def uart_rebuild():
    uart_txt.config(state='normal'); uart_txt.delete('1.0', 'end'); uart_txt.config(state='disabled'); _uart_insert(uart_recs[-800:])
def uart_reset():                                 # очистити журнал (напр. після завантаження стану — старі байти вже не актуальні)
    uart_pending.clear(); uart_grp['b'] = bytearray(); uart_recs.clear(); uart_n[0] = 0; uart_state.set(T('TX: 0 Б')); uart_rebuild()
def uart_save():
    p = _fd.asksaveasfilename(defaultextension='.txt', initialfile='uart_log.txt', filetypes=[(T('Текст'), '*.txt'), (T('Усі файли'), '*.*')])
    if p:
        with open(p, 'w', encoding='utf-8') as f: f.write('\n'.join(ln for rec in uart_recs for ln in _uart_fmt(rec)) + '\n')
        status_msg.set(T('UART-журнал збережено: ') + os.path.basename(p))
tk.Button(_u2, text=T('Очистити'), command=uart_reset, font=('Segoe UI', 8), padx=4, pady=0).pack(side='right', padx=1)
tk.Button(_u2, text=T('Зберегти…'), command=uart_save, font=('Segoe UI', 8), padx=4, pady=0).pack(side='right', padx=1)
def on_close():
    try:
        if args.state: save_state(args.state)
    except Exception as e: print(T('[!] стан не збережено:'), e)
    try:
        if args.usb_log and args.usb_log != '-': open(args.usb_log, 'w', encoding='utf-8').write('\n'.join(UsbLog.fmt(r) for r in usblog.lines) + '\n')
    except Exception as e: print(T('[!] USB-журнал не збережено:'), e)
    beeper.stop(); root.destroy()
root.protocol('WM_DELETE_WINDOW', on_close)

# клавіатура (з "антидребезгом" авто-повтору)
rel_jobs = {}
def key_press(e):
    if isinstance(e.widget, tk.Entry): return
    k = e.keysym.lower()
    if k.isdigit() and 1 <= int(k) <= len(BTNS):
        pin = BTNS[int(k) - 1][0]
        if pin in rel_jobs: root.after_cancel(rel_jobs.pop(pin))
        press(pin)
    elif k == 'r': set_rot()
    elif k == 'space': toggle_pause()
    elif k in ('plus', 'equal', 'kp_add'): set_scale(1)
    elif k in ('minus', 'kp_subtract'): set_scale(-1)
    elif k == 's': do_shot()
def key_release(e):
    if isinstance(e.widget, tk.Entry): return
    k = e.keysym.lower()
    if k.isdigit() and 1 <= int(k) <= len(BTNS):
        pin = BTNS[int(k) - 1][0]
        rel_jobs[pin] = root.after(40, lambda p=pin: (rel_jobs.pop(p, None), release(p)))
root.bind('<KeyPress>', key_press); root.bind('<KeyRelease>', key_release)

def render():
    photo['raw'] = tk.PhotoImage(data=ppm(rot[0]))
    photo['disp'] = photo['raw'].zoom(scale[0]) if scale[0] > 1 else photo['raw']
    canvas.itemconfig(img_item, image=photo['disp']); lcd.dirty = False

t_start = time.perf_counter()
def pump():
    now = time.perf_counter()
    if not paused[0] and not dead[0]:
        if speed[0] is None: target = cnt[0] + 10 ** 9
        else:
            target = sync['ms'] + (now - sync['t']) * 1000 * speed[0]
            if target - cnt[0] > 300 * max(1, speed[0]): resync(); target = cnt[0]   # не наганяємо відставання
        while cnt[0] < target and time.perf_counter() - now < 0.012 and not dead[0]:
            run_tick()
        if speed[0] is not None and cnt[0] < target - 50: resync()
    usb_flush(now); uart_flush()
    if lcd.dirty and now - last_render[0] > 0.033:
        render(); last_render[0] = now
    if int(now * 5) != getattr(pump, '_s', None):
        pump._s = int(now * 5)
        usb_state.set(f'{T(usb_host.state)} · OUT {usb_stat["out"]} / IN {usb_stat["in"]}')
        snd_var.set(snd_label()); flash_info.set(flash_label())
        btn_pins = {p for p, _ in BTNS}
        poll = ' '.join(f'PB{m.bit_length() - 1}' for m, _ in polled.most_common(8) if m and m & (m - 1) == 0 and m.bit_length() - 1 in btn_pins) or '—'
        status.set(T('t={0:7.2f} с   PC={1:08X}\nLCD: {2} ком., MADCTL={3:02X}, поворот {4}°\nRTC {5:%H:%M:%S}   ').format(cnt[0] / 1000, uc.reg_read(UC_ARM_REG_PC), lcd.ncmd, lcd.madctl, rot[0] * 90, clock.now()) + (T('♪ {0:.0f} Гц, заповн. {1:.0f}%').format(snd['f'], snd['d'] * 100) if snd['on'] else '♪ —') + T('\nпрошивка опитує: {0}').format(poll) + (f'\n!!! {dead[0]}' if dead[0] else ''))
    if args.autoquit and now - t_start > args.autoquit:
        if lcd.dirty: render()
        photo['raw'].write('autoshot.png', format='png'); print(T('autoshot.png, t=%d мс') % cnt[0]); root.destroy(); return
    root.after(10, pump)

root.after(10, pump)
root.mainloop()
