# Forever Translator

Lokální překlad WoW chatu mezi angličtinou a češtinou pro Windows 10/11 x64.
Nepotřebuje Python, Tesseract, internet ani API klíč.

## Rychlý start

1. Rozbalte **celý** `ForeverTranslator-Windows-x64.zip` do běžné složky.
2. Ve složce `ForeverTranslator` spusťte `ForeverTranslator.exe`.
3. V okně **První spuštění** klikněte na **Vybrat WoW a nainstalovat addon**.
4. Vyberte složku verze WoW, kterou hrajete. Musí v ní být `Wow.exe` nebo
   `WowB.exe`, například:
   `C:\Program Files (x86)\World of Warcraft\_classic_beta_`
5. Ve WoW na obrazovce s postavami zapněte addon **Forever Translator Probe**.
   Pokud hra už běží, napište do chatu `/reload`.
6. Jakmile aplikace přečte barevnou mřížku vlevo nahoře, návod zmizí a chat se
   začne automaticky překládat.

Hotovo. Anglické zprávy se zobrazí česky. Pro vlastní zprávu napište český text
do spodního řádku a stiskněte Enter. Anglický překlad se zkopíruje do schránky;
ve WoW jej vložte pomocí `Ctrl+V` a odešlete sami.

> Nespouštějte EXE přímo ze ZIPu a neoddělujte `ForeverTranslator.exe` od složky
> `_internal`. Celou rozbalenou složku můžete mít kdekoli na disku.

## Když návod nezmizí

- Ověřte, že je ve WoW zapnutý **Forever Translator Probe**, a napište `/reload`.
- Ověřte, že je vlevo nahoře vidět malá barevná mřížka.
- Pokud je WoW v okně nebo na jiném monitoru, klikněte v úvodním návodu na
  **Mřížka je jinde – vybrat datový blok ručně** a označte celou mřížku i s
  barevným okrajem.
- Jestli instalace addonu hlásí chybu, vybrali jste nejspíš hlavní složku
  `World of Warcraft`. Vyberte její podsložku konkrétní verze, například
  `_classic_beta_`.

## Ovládání

- Tažením za plochu okna jej přesunete.
- Tažením za pravý dolní roh změníte velikost.
- Pravé tlačítko otevře nabídku. Je v ní ruční výběr mřížky, diagnostika,
  přepínač **Vždy nahoře** a **Zavřít**.
- Okno nemá běžný rám ani tlačítka, aby nepřekáželo ve WoW. Ukončete jej přes
  nabídku pod pravým tlačítkem.
- Pozice, velikost a volba **Vždy nahoře** se ukládají automaticky.

## Co balíček obsahuje

- Windows aplikaci s vlastním Python runtime;
- addon `ForeverTranslatorProbe`;
- offline modely `Helsinki-NLP/opus-mt-en-cs` a
  `Helsinki-NLP/opus-mt-cs-en`, převedené pro CTranslate2 do CPU INT8.

Překlad běží kompletně lokálně. Aplikace nečte paměť hry, nepoužívá DLL
injection, nesnímá síťový provoz a sama neposílá žádné zprávy ani stisky kláves
do WoW.

## Jak přenos funguje

Addon zachytí veřejné `CHAT_MSG_*` události a zakóduje přesná UTF-8 data do malé
čtyřbarevné mřížky. Windows aplikace snímá pouze oblast této mřížky, kontroluje
pakety checksumem, skládá dlouhé zprávy a předává je lokálnímu překladači. Není
to QR kód ani OCR a Tesseract není potřeba.

Český překlad je v okně první a výrazný, anglický originál menší a šedý. Kanály
používají barvy WoW a jména hráčů jejich class barvu, pokud ji WoW poskytne.
Odkazy na předměty, questy a další herní objekty zůstávají rozpoznatelné a jejich
název se nepřekládá.

## Vývoj

Běžný uživatel tuto část nepotřebuje.

Požadavky: Windows, Python 3.11+ s Tkinterem a připravené `.venv`.

Spuštění ze zdrojů:

```powershell
.\run_probe.ps1 -Optical
```

Simulace bez WoW:

```powershell
.\run_probe.ps1 -Simulate
```

Příprava překladových modelů a sestavení přenosného balíčku:

```powershell
.\setup_translation.ps1
.\build_portable.ps1
```

Výsledek je `dist\ForeverTranslator-Windows-x64.zip`. Build používá PyInstaller
v režimu one-folder; README a licence se kopírují do rozbalené složky i do ZIPu.

Testy:

```powershell
$env:PYTHONPATH = "$PWD\app"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Diagnostické fallbacky pro vývojáře zůstávají dostupné přes `-Ocr` a čtení
`WoWChatLog.txt`, ale distribuovaná aplikace používá automaticky optický režim.
