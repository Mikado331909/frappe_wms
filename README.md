# Frappe WMS

Frappe WMS is een Warehouse Management System laag voor ERPNext. De app voegt fysieke locatievoorraad, putaway, picking, kwaliteitscontrole, cross-dock, cycle counting en WMS rapportage toe bovenop de standaard ERPNext voorraadadministratie.

De basisgedachte is eenvoudig:

- ERPNext blijft leidend voor voorraadboekingen, waardering, batches, inkoop, verkoop, productie en de stock ledger.
- Frappe WMS houdt bij waar voorraad fysiek ligt binnen een warehouse: zone, locatie, batch, klant en hoeveelheid.
- Elke WMS voorraadmutatie schrijft een auditregel in `Batch Location Movement`.
- De app is bedoeld voor batch-gestuurde voorraad. Serienummers worden niet als hoofdproces beheerd door deze app.

De app richt zich op ERPNext/Frappe versie 16 en bevat compatibiliteit voor batchinformatie via Serial and Batch Bundle.

---

## Inhoud

1. [Wat deze app oplost](#wat-deze-app-oplost)
2. [Belangrijke uitgangspunten](#belangrijke-uitgangspunten)
3. [Module en workspace](#module-en-workspace)
4. [Architectuur](#architectuur)
5. [Datamodel](#datamodel)
6. [ERPNext integraties](#erpnext-integraties)
7. [Workflows](#workflows)
8. [Picking strategieen](#picking-strategieen)
9. [Klantsegregatie](#klantsegregatie)
10. [Configuratie](#configuratie)
11. [Voorbeeldinrichting](#voorbeeldinrichting)
12. [Dashboards en rapporten](#dashboards-en-rapporten)
13. [Installatie](#installatie)
14. [Upgrade en migratie](#upgrade-en-migratie)
15. [Validatie en testen](#validatie-en-testen)
16. [Beperkingen en aandachtspunten](#beperkingen-en-aandachtspunten)
17. [Technische bestandsstructuur](#technische-bestandsstructuur)
18. [Licentie](#licentie)

---

## Wat deze app oplost

ERPNext weet hoeveel voorraad er in een warehouse ligt. In veel magazijnen is dat niet genoeg. Medewerkers moeten ook weten:

- in welke zone een batch ligt;
- op welke fysieke locatie een batch ligt;
- welke klant eigenaar is van een batch;
- of goederen nog in ontvangst, QC, cross-dock, productie staging of outbound staging staan;
- welke voorraad al fysiek gepickt is;
- welke verschillen uit een telling zijn gekomen;
- of de WMS locatievoorraad nog aansluit op de ERPNext stock ledger.

Frappe WMS vult die operationele laag in.

### Kernfuncties

- WMS workspace met operationele shortcuts, KPI cards en dashboard chart.
- Zones per warehouse, zoals Receiving, Active Storage, QC Hold, Production Staging en Outbound Staging.
- Storage Locations als fysieke locaties binnen zones.
- Batch Location Stock voor exacte voorraad per item, batch, warehouse en locatie.
- Batch Location Movement als auditlog voor iedere fysieke beweging.
- Automatische verwerking van Purchase Receipt, Delivery Note en Stock Entry events.
- QC flow met WMS QC Check.
- Cross-dock flow met WMS Cross Dock.
- Location Pick flow vanuit ERPNext Pick List.
- Putaway suggesties op basis van WMS Putaway Rules.
- Klantsegregatie op opslaglocaties.
- Cycle counting op basis van zones.
- Rapporten voor bezetting, klantvoorraad, pick performance, volume en reconciliatie.

### Wat de app niet probeert te vervangen

- ERPNext Stock Ledger Entry blijft de bron voor financiele en administratieve voorraad.
- ERPNext Warehouse blijft het administratieve warehouse.
- ERPNext Item, Batch, Purchase Receipt, Pick List, Delivery Note en Stock Entry blijven de standaard documenten.
- De app doet geen volledige serial number workflow.
- De app maakt geen waarderingsboekingen buiten ERPNext om.

---

## Belangrijke uitgangspunten

### ERPNext is leidend voor voorraad

Frappe WMS beheert locaties. ERPNext beheert de stock ledger. WMS mag niet stilletjes ERPNext corrigeren. Als WMS en ERPNext verschillen, moet dat zichtbaar worden in het reconciliatie rapport.

### Locatievoorraad wordt niet verwijderd

`Batch Location Stock` records blijven bestaan, ook als de hoeveelheid nul wordt. Dit is bewust. Het geeft historie en voorkomt dat auditinformatie verdwijnt.

### Elke beweging krijgt een auditregel

Voorraad toevoegen, aftrekken of verplaatsen verloopt via gedeelde helpers in `events/utils.py`. Die helpers schrijven altijd een `Batch Location Movement` record.

### Alleen batch-gestuurde voorraad

De kern van deze app werkt met `item_code + batch_no + warehouse + storage_location`. Artikelen die met WMS worden beheerd moeten daarom batch tracking gebruiken in ERPNext.

### Selectieve activatie per warehouse

Een warehouse doet alleen mee in WMS als er actieve Storage Locations voor dat warehouse zijn ingericht. Daardoor kan de app gefaseerd worden gebruikt.

---

## Module en workspace

De app registreert een module `WMS`.

Belangrijke app metadata:

- App name: `frappe_wms`
- Module: `WMS`
- Workspace route: `/desk/wms`
- App home: `/desk/wms`
- Workspace document: `WMS`
- Workspace export: `frappe_wms/wms/workspace/wms/wms.json`

De app bevat ook een Dashboard record `WMS`, zodat WMS zichtbaar is in Build > Dashboard. De Dashboard fixture koppelt dezelfde KPI cards en chart als de workspace:

- Pending QC Checks
- Cross-dock Pending
- Active Storage Locations
- Warehouse Movements by Type

---

## Architectuur

Frappe WMS hangt als event-driven laag aan ERPNext documenten.

```text
ERPNext Purchase Receipt
  -> on_submit
     -> normale ontvangst naar Receiving
     -> QC ontvangst naar QC Hold + WMS QC Check
     -> cross-dock ontvangst naar Cross-dock Staging + WMS Cross Dock

ERPNext Pick List
  -> knop in formulier
     -> Generate Location Pick
     -> WMS zoekt Batch Location Stock op opslaglocaties
     -> WMS maakt Location Pick regels

Location Pick
  -> submit
     -> verplaatst voorraad van opslaglocatie naar Outbound/Picking Staging

ERPNext Delivery Note
  -> on_submit
     -> trekt voorraad af uit Outbound/Picking Staging

ERPNext Stock Entry
  -> on_submit
     -> bronkant trekt af uit staging
     -> doelkant gaat naar Receiving of Inspection

WMS Cycle Count
  -> genereert telregels uit Batch Location Stock
  -> submit corrigeert locatievoorraad en schrijft movement audit
```

### Gedeelde voorraadhelpers

De gedeelde helpers staan in `frappe_wms/wms/events/utils.py`.

| Helper | Doel |
|---|---|
| `iter_batch_entries` | Leest batches uit ERPNext v16 Serial and Batch Bundle of oudere batchvelden. |
| `get_receiving_location` | Vindt actieve Receiving locatie voor een warehouse. |
| `get_picking_staging_location` | Vindt Picking Staging of Outbound Staging locatie. |
| `get_qc_hold_location` | Vindt QC Hold locatie. |
| `get_cross_dock_location` | Vindt Cross-dock Staging locatie. |
| `get_quarantine_location` | Vindt Quarantine locatie. |
| `get_production_staging_location` | Vindt Production Staging locatie. |
| `evaluate_putaway_rule` | Bepaalt beste zone en locatie op basis van WMS Putaway Rule. |
| `add_location_qty` | Verhoogt of maakt Batch Location Stock en schrijft movement. |
| `deduct_location_qty` | Verlaagt Batch Location Stock en schrijft movement. |
| `move_location_qty` | Verplaatst voorraad tussen twee locaties en schrijft movement. |

---

## Datamodel

### WMS Zone

Een WMS Zone groepeert fysieke locaties binnen een ERPNext warehouse.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `zone_code` | Data | Unieke zonecode. |
| `zone_name` | Data | Leesbare naam. |
| `warehouse` | Link | ERPNext Warehouse. |
| `zone_type` | Select | Functionele zone. |
| `dedicated_customer` | Link | Optionele klant voor gereserveerde zone. |
| `is_active` | Check | Actief of niet. |

Zone types:

- Receiving
- Active Storage
- QC Hold
- Production Staging
- Outbound Staging
- Cross-dock Staging
- Inspection
- Quarantine

Voorbeeld:

```text
zone_code: ZONE-A
zone_name: Opslagzone A
warehouse: WH-01
zone_type: Active Storage
dedicated_customer: Klant A
is_active: 1
```

### Storage Location

Een Storage Location is een fysieke plek in een zone, zoals een vak, stelling, palletplaats of staginglocatie.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `location_code` | Data | Locatiecode. |
| `location_name` | Data | Leesbare naam. |
| `warehouse` | Link | ERPNext Warehouse. |
| `zone` | Link | WMS Zone. |
| `location_type` | Select | Functie van de locatie. |
| `pick_sequence` | Int | Sorteervolgorde voor pickroute. |
| `max_qty` | Float | Capaciteit; nul betekent geen vaste limiet. |
| `is_active` | Check | Actief of niet. |

Location types:

- Storage
- Receiving
- Picking Staging
- Active Storage
- QC Hold
- Production Staging
- Outbound Staging
- Cross-dock Staging
- Inspection
- Quarantine

Voorbeeld:

```text
location_code: A-01-01
warehouse: WH-01
zone: ZONE-A
location_type: Active Storage
pick_sequence: 10
max_qty: 500
is_active: 1
```

### Batch Location Stock

Dit is de kern van WMS locatievoorraad. Een record beschrijft hoeveel van een batch op een fysieke locatie ligt.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `item_code` | Link | ERPNext Item. |
| `item_name` | Data | Itemnaam. |
| `batch_no` | Link | ERPNext Batch. |
| `customer` | Link | Klant/eigenaar van batch. |
| `zone` | Link | WMS Zone. |
| `warehouse` | Link | ERPNext Warehouse. |
| `storage_location` | Link | Fysieke locatie. |
| `qty` | Float | Huidige locatiehoeveelheid. |
| `uom` | Link | Eenheid. |
| `reserved_qty` | Float | Gereserveerde hoeveelheid voor latere uitbreiding. |

Validaties:

- De gekozen Storage Location moet bij hetzelfde warehouse horen.
- Er mag geen tweede record bestaan voor dezelfde combinatie item, batch, warehouse en locatie.
- Als `validate_against_erpnext` actief is, mag de totale WMS locatievoorraad voor item/batch/warehouse de ERPNext voorraad niet overschrijden.

### Batch Location Movement

Dit is de auditlog van WMS.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `posting_date` | Date | Datum van beweging. |
| `posting_time` | Time | Tijd van beweging. |
| `item_code` | Link | ERPNext Item. |
| `batch_no` | Link | ERPNext Batch. |
| `movement_type` | Select | Soort beweging. |
| `customer` | Link | Klant/eigenaar van batch. |
| `warehouse` | Link | ERPNext Warehouse. |
| `from_location` | Link | Bronlocatie. |
| `to_location` | Link | Doellocatie. |
| `qty` | Float | Hoeveelheid. |
| `reference_doctype` | Link | Brondocumenttype. |
| `reference_name` | Dynamic Link | Brondocument. |
| `remarks` | Small Text | Opmerking. |

Movement types:

- Inbound
- Putaway
- Pick
- Cross-dock
- QC Release
- Production
- Production Return
- Cycle Count
- Manual

### WMS Putaway Rule

Putaway Rules bepalen naar welke zone ontvangen voorraad bij voorkeur gaat.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `priority` | Int | Laagste waarde wordt eerst geprobeerd. |
| `warehouse` | Link | Optioneel warehousefilter. |
| `customer` | Link | Optionele klantmatch. |
| `item_group` | Link | Optionele itemgroepmatch. |
| `target_zone` | Link | Doelzone. |
| `is_active` | Check | Actief of niet. |

Regelvolgorde:

1. Sorteer actieve regels op prioriteit.
2. Match warehouse als ingevuld.
3. Match klant als ingevuld.
4. Match item group als ingevuld.
5. Zoek beste locatie binnen target zone.
6. Geef voorkeur aan consolidatie met bestaande voorraad van dezelfde klant.
7. Als dat niet kan, kies een lege actieve opslaglocatie.

### Location Pick

Location Pick is het WMS pickdocument dat vanuit een of meer ERPNext Pick Lists wordt gegenereerd.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `naming_series` | Select | Nummerreeks `WMS-PICK-.YYYY.-.#####`. |
| `pick_lists` | Table | Gekoppelde Pick Lists. |
| `pick_list` | Link | Legacy/enkelvoudige Pick List referentie. |
| `status` | Select | Draft, Open, Completed, Cancelled. |
| `picking_strategy` | Select | Pick Sequence, FEFO of FIFO. |
| `picker` | Link | Gebruiker die pickt. |
| `posting_date` | Date | Datum. |
| `posting_time` | Time | Tijd. |
| `items` | Table | Pickregels. |

Child table `Location Pick Source`:

| Veld | Type | Doel |
|---|---|---|
| `pick_list` | Link | ERPNext Pick List die is opgenomen. |

Child table `Location Pick Line`:

| Veld | Type | Doel |
|---|---|---|
| `pick_list` | Link | ERPNext Pick List. |
| `item_code` | Link | Item. |
| `item_name` | Data | Itemnaam. |
| `batch_no` | Link | Batch. |
| `warehouse` | Link | Warehouse. |
| `source_location` | Link | WMS bronlocatie. |
| `required_qty` | Float | Te picken hoeveelheid. |
| `picked_qty` | Float | Werkelijk gepickte hoeveelheid. |
| `uom` | Link | Eenheid. |
| `pick_list_item` | Data | ERPNext Pick List Item rij. |

### WMS QC Check

WMS QC Check wordt gebruikt voor goederen die eerst moeten worden gecontroleerd.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `naming_series` | Select | Nummerreeks `WMS-QC-.YYYY.-.#####`. |
| `purchase_receipt` | Link | Bron Purchase Receipt. |
| `warehouse` | Link | Warehouse. |
| `check_type` | Select | Kwaliteit, Kwantiteit of Beide. |
| `status` | Select | Pending, In Progress, Completed. |
| `inspector` | Link | Controleur. |
| `check_date` | Date | Controledatum. |
| `items` | Table | QC regels. |
| `remarks` | Small Text | Opmerking. |

Child table `WMS QC Check Line`:

| Veld | Type | Doel |
|---|---|---|
| `item_code` | Link | Item. |
| `item_name` | Data | Itemnaam. |
| `batch_no` | Link | Batch. |
| `from_location` | Link | QC Hold locatie. |
| `received_qty` | Float | Ontvangen hoeveelheid. |
| `approved_qty` | Float | Goedgekeurde hoeveelheid. |
| `rejected_qty` | Float | Afgekeurde hoeveelheid. |
| `outcome` | Select | Goedgekeurd, Afgekeurd of Gedeeltelijk. |
| `quality_remarks` | Small Text | Opmerking. |

### WMS Cross Dock

WMS Cross Dock wordt gebruikt voor goederen die niet naar opslag gaan, maar direct doorstromen naar uitlevering.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `naming_series` | Select | Nummerreeks `WMS-XD-.YYYY.-.#####`. |
| `purchase_receipt` | Link | Bron Purchase Receipt. |
| `customer` | Link | Klant. |
| `status` | Select | Pending, Staged, Delivered, Cancelled. |
| `posting_date` | Date | Datum. |
| `items` | Table | Cross-dock regels. |
| `notes` | Small Text | Notities. |

Child table `WMS Cross Dock Item`:

| Veld | Type | Doel |
|---|---|---|
| `item_code` | Link | Item. |
| `item_name` | Data | Itemnaam. |
| `batch_no` | Link | Batch. |
| `warehouse` | Link | Warehouse. |
| `xdock_location` | Link | Cross-dock locatie. |
| `sales_order` | Link | Gekoppelde Sales Order. |
| `qty` | Float | Ontvangen hoeveelheid. |
| `staged_qty` | Float | Naar staging verplaatste hoeveelheid. |
| `delivered_qty` | Float | Geleverde hoeveelheid. |
| `uom` | Link | Eenheid. |

### WMS Cycle Count

WMS Cycle Count ondersteunt periodieke tellingen per zone.

Belangrijke velden:

| Veld | Type | Doel |
|---|---|---|
| `naming_series` | Select | Nummerreeks `WMS-CC-.YYYY.-.#####`. |
| `count_date` | Date | Teldatum. |
| `warehouse` | Link | Warehouse. |
| `status` | Select | Draft, In Progress, Completed, Cancelled. |
| `counted_by` | Link | Teller. |
| `count_zones` | Table | Zones die geteld worden. |
| `count_lines` | Table | Telregels. |

Child table `WMS Cycle Count Zone`:

| Veld | Type | Doel |
|---|---|---|
| `zone` | Link | Te tellen zone. |

Child table `WMS Cycle Count Line`:

| Veld | Type | Doel |
|---|---|---|
| `storage_location` | Link | Locatie. |
| `zone` | Data | Zone. |
| `item_code` | Link | Item. |
| `item_name` | Data | Itemnaam. |
| `batch_no` | Link | Batch. |
| `customer` | Link | Klant/eigenaar. |
| `system_qty` | Float | WMS systeemhoeveelheid. |
| `counted_qty` | Float | Getelde hoeveelheid. |
| `difference` | Float | Verschil. |
| `status` | Select | Pending, Counted, Corrected. |
| `remarks` | Small Text | Opmerking. |

### WMS Settings

Single DocType voor globale WMS instellingen.

| Veld | Type | Doel |
|---|---|---|
| `auto_create_on_receipt` | Check | Automatisch WMS voorraad maken bij Purchase Receipt. |
| `validate_against_erpnext` | Check | WMS locatievoorraad toetsen aan ERPNext voorraad. |
| `default_putaway_mode` | Select | Manual, Suggest of Enforce. |
| `qc_trigger` | Select | Per Receipt Line of Never. |
| `auto_create_cross_dock` | Check | Cross-dock automatisch detecteren. |

Let op: niet elke setting is al in elke flow volledig afdwingend. De belangrijkste actieve settings zijn `auto_create_on_receipt` en `validate_against_erpnext`.

---

## ERPNext integraties

### Custom Fields

De app voegt velden toe aan ERPNext documenten.

Op `Batch`:

| Veld | Type | Doel |
|---|---|---|
| `customer` | Link Customer | Klant/eigenaar van de batch voor WMS segregatie. |

Op `Purchase Receipt Item`:

| Veld | Type | Doel |
|---|---|---|
| `wms_customer` | Link Customer | Klant/eigenaar voor deze ontvangstregel. |
| `wms_require_qc` | Check | Ontvangstregel moet naar QC Hold. |
| `wms_cross_dock` | Check | Ontvangstregel moet naar cross-dock. |
| `wms_cross_dock_so` | Link Sales Order | Optionele gekoppelde Sales Order voor cross-dock. |

### Purchase Receipt

Hook:

```python
doc_events = {
    "Purchase Receipt": {
        "on_submit": "frappe_wms.wms.events.purchase_receipt.on_submit",
        "on_cancel": "frappe_wms.wms.events.purchase_receipt.on_cancel",
    }
}
```

Bij submit:

- Als `auto_create_on_receipt` uit staat, doet WMS niets.
- WMS leest batchregels via `iter_batch_entries`.
- `wms_customer` wordt op de Batch gezet als daar nog geen klant staat.
- Cross-dock heeft voorrang boven QC.
- Cross-dock regels gaan naar Cross-dock Staging.
- QC regels gaan naar QC Hold.
- Normale regels gaan naar Receiving.
- Voor QC wordt automatisch een `WMS QC Check` gemaakt.
- Voor cross-dock wordt automatisch een `WMS Cross Dock` gemaakt.

Bij cancel:

- WMS probeert de eerder ontvangen hoeveelheid terug te draaien vanaf de verwachte locatie.
- Er wordt nooit meer afgetrokken dan nog beschikbaar is op die locatie.

### Pick List

De app voegt client-side functionaliteit toe aan ERPNext Pick List.

Knop:

```text
WMS -> Generate Location Pick
```

De gebruiker kiest:

- picking strategie;
- nieuwe Location Pick of toevoegen aan bestaande open Location Pick.

WMS zoekt daarna beschikbare `Batch Location Stock` op actieve opslaglocaties en maakt Location Pick regels.

### Delivery Note

Bij submit van Delivery Note:

- WMS zoekt de staginglocatie voor het warehouse.
- WMS trekt batchhoeveelheid af uit staging.
- De movement krijgt type `Pick`.

### Stock Entry

Bij submit van Stock Entry:

- De bronkant trekt voorraad af uit staging, als daar voorraad staat.
- De doelkant plaatst voorraad in Receiving.
- Als het een productie-retour is (`Material Transfer` met `work_order`), probeert WMS eerst naar Inspection te boeken.

---

## Workflows

### 1. Standaard inbound ontvangst

Doel: batchvoorraad na Purchase Receipt zichtbaar maken in Receiving.

```text
Purchase Receipt submit
  -> WMS leest batchregels
  -> WMS zet klant op Batch als wms_customer is ingevuld
  -> WMS zoekt Receiving locatie
  -> WMS maakt/verhoogt Batch Location Stock
  -> WMS schrijft Batch Location Movement met movement_type Inbound
```

Voorbeeld:

```text
Item: ITEM-A
Batch: BATCH-001
Warehouse: WH-01
Receiving locatie: RECV-01
Qty: 100
Klant: Klant A
```

Resultaat:

```text
Batch Location Stock
  item_code: ITEM-A
  batch_no: BATCH-001
  warehouse: WH-01
  storage_location: RECV-01
  qty: 100
  customer: Klant A
```

### 2. QC ontvangst

Doel: goederen eerst blokkeren voor controle.

```text
Purchase Receipt Item: wms_require_qc = 1
  -> WMS zoekt QC Hold locatie
  -> voorraad komt in QC Hold
  -> WMS QC Check wordt aangemaakt
```

Daarna:

```text
WMS QC Check
  -> medewerker vult approved_qty en rejected_qty
  -> submit
     -> approved_qty naar Receiving
     -> rejected_qty naar Quarantine
```

Voorbeeld:

```text
Ontvangen: 100
Goedgekeurd: 95
Afgekeurd: 5
```

Resultaat:

- 95 gaat van QC Hold naar Receiving.
- 5 gaat van QC Hold naar Quarantine.
- Beide bewegingen krijgen movement type `QC Release`.

### 3. Cross-dock ontvangst

Doel: goederen niet opslaan, maar direct doorzetten naar uitlevering.

Cross-dock kan handmatig:

```text
Purchase Receipt Item:
  wms_cross_dock = 1
  wms_cross_dock_so = SO-0001
```

Of via een bestaande koppeling tussen Purchase Order Item en Sales Order.

Flow:

```text
Purchase Receipt submit
  -> WMS zoekt Cross-dock Staging locatie
  -> WMS plaatst voorraad op cross-dock locatie
  -> WMS Cross Dock document wordt aangemaakt
```

Vervolgens:

```text
WMS Cross Dock
  -> knop Gereed voor Verzending
  -> WMS verplaatst beschikbare qty van Cross-dock Staging naar Outbound/Picking Staging
```

### 4. Putaway van Receiving naar opslag

Doel: ontvangen voorraad naar de juiste opslaglocatie verplaatsen.

Flow:

```text
Open Batch Location Stock record in Receiving
  -> klik Voorraad Verplaatsen
  -> WMS vraagt putaway suggestie op
  -> gebruiker kiest doel locatie
  -> WMS controleert compatibiliteit
  -> WMS verplaatst voorraad en schrijft movement
```

Putaway suggestie:

1. Zoek actieve WMS Putaway Rules.
2. Match warehouse, klant en item group.
3. Kies target zone.
4. Zoek eerst locatie met voorraad van dezelfde klant.
5. Anders zoek lege actieve opslaglocatie.

Compatibiliteit:

- Andere klant op opslaglocatie: geblokkeerd.
- Zelfde klant met bestaande voorraad: waarschuwing en bevestiging.
- Capaciteit overschreden: waarschuwing.

### 5. Outbound picking

Doel: ERPNext Pick List vertalen naar fysieke pickregels.

```text
ERPNext Pick List
  -> knop WMS Generate Location Pick
  -> kies picking strategie
  -> WMS maakt Location Pick
```

De Location Pick bevat regels per batch en fysieke source location.

Bij submit:

```text
Location Pick submit
  -> WMS controleert of picked_qty beschikbaar is
  -> WMS verplaatst picked_qty naar Outbound/Picking Staging
  -> status wordt Completed
```

Na submit toont de client een controle als WMS picked qty afwijkt van ERPNext Pick List `picked_qty`. De gebruiker kan dan kiezen om ERPNext picked qty bij te werken naar de WMS waarden.

### 6. Delivery Note uitlevering

Doel: stagingvoorraad afboeken wanneer ERPNext uitlevering wordt geboekt.

```text
Delivery Note submit
  -> WMS zoekt Outbound/Picking Staging
  -> WMS trekt beschikbare staged qty af
  -> movement_type Pick
```

### 7. Productie staging

Doel: materiaal naar staging brengen en bij Stock Entry verwerken.

WMS kan Pick Lists voor productie omzetten naar Location Picks. Het submitten van Location Pick brengt materiaal naar staging.

Bij Stock Entry submit:

- Bronwarehouse met stagingvoorraad: WMS trekt af uit staging.
- Target warehouse: WMS voegt batch toe aan Receiving.
- Productieretour met `Material Transfer` en `work_order`: WMS boekt naar Inspection als die locatie bestaat.

### 8. Cycle count

Doel: fysieke tellingen per zone uitvoeren.

```text
WMS Cycle Count
  -> kies warehouse
  -> voeg zones toe
  -> klik Telregels Genereren
  -> WMS vult count_lines vanuit Batch Location Stock
  -> medewerker vult counted_qty
  -> submit
```

Bij submit:

- Verschillen worden berekend.
- Positief verschil verhoogt Batch Location Stock.
- Negatief verschil verlaagt Batch Location Stock.
- Movement type is `Cycle Count`.
- Regels krijgen status `Corrected`.

Belangrijk: deze correctie wijzigt WMS locatievoorraad. Voor financiele voorraadcorrecties blijft ERPNext leidend. Controleer verschillen met het reconciliatie rapport.

---

## Picking strategieen

Location Pick ondersteunt drie sorteringen.

| Strategie | Sortering |
|---|---|
| Pick Sequence | `Storage Location.pick_sequence` oplopend, daarna grootste beschikbare qty. |
| FEFO - First Expired, First Out | Batch expiry date oplopend, lege expiry dates als laatste, daarna pick sequence. |
| FIFO - First In, First Out | Batch creation oplopend, daarna pick sequence. |

Voorbeeld:

```text
Vraag: 80 stuks ITEM-A batch BATCH-001

Beschikbaar:
  A-01-01: 30
  A-01-02: 70

Resultaat:
  Pickregel 1: A-01-01, 30
  Pickregel 2: A-01-02, 50
```

WMS kan dus een pickvraag splitsen over meerdere locaties.

---

## Klantsegregatie

Klantsegregatie voorkomt dat voorraad van verschillende klanten op dezelfde opslaglocatie wordt gemengd.

Deze controle geldt voor opslaglocaties:

- Storage
- Active Storage

Deze controle geldt niet voor transitlocaties:

- Receiving
- Picking Staging
- Outbound Staging
- QC Hold
- Production Staging
- Cross-dock Staging
- Inspection
- Quarantine

Regels:

| Situatie | Resultaat |
|---|---|
| Locatie is leeg | Toegestaan. |
| Zelfde klant, zelfde item | Toegestaan. |
| Zelfde klant, ander item | Toegestaan na waarschuwing. |
| Andere klant | Geblokkeerd. |
| Eigen voorraad gemengd met klantvoorraad | Geblokkeerd. |

Voorbeeld:

```text
Locatie A-01-01 bevat:
  ITEM-A, BATCH-001, Klant A, qty 50

Nieuwe putaway:
  ITEM-B, BATCH-002, Klant A, qty 25

Resultaat:
  WMS toont waarschuwing, maar staat toe na bevestiging.
```

```text
Locatie A-01-01 bevat:
  ITEM-A, BATCH-001, Klant A, qty 50

Nieuwe putaway:
  ITEM-C, BATCH-003, Klant B, qty 10

Resultaat:
  WMS blokkeert de verplaatsing.
```

---

## Configuratie

### Stap 1: WMS Settings

Open:

```text
WMS -> WMS Settings
```

Aanbevolen startinstellingen:

| Setting | Waarde |
|---|---|
| Auto Create on Receipt | Aan |
| Validate Against ERPNext | Aan |
| Default Putaway Mode | Suggest |
| QC Trigger | Per Receipt Line |
| Auto Create Cross Dock | Aan indien cross-dock gebruikt wordt |

### Stap 2: Zones aanmaken

Maak minimaal de zones die bij jouw proces horen.

Aanbevolen basis:

| Zone | Type | Doel |
|---|---|---|
| RECV-ZONE | Receiving | Binnenkomende goederen. |
| STORAGE-A | Active Storage | Normale opslag. |
| QC-ZONE | QC Hold | Te controleren goederen. |
| OUT-STAGE | Outbound Staging | Gepickte goederen voor verzending. |
| XDOCK-ZONE | Cross-dock Staging | Direct door te zetten goederen. |
| INSP-ZONE | Inspection | Productieretouren of controle. |
| QUAR-ZONE | Quarantine | Afgekeurde of geblokkeerde goederen. |

### Stap 3: Storage Locations aanmaken

Voor elk WMS warehouse moet er minimaal een actieve Receiving locatie zijn als inbound automatisch moet werken.

Aanbevolen basis:

| Locatie | Type | Zone | Pick sequence |
|---|---|---|---|
| RECV-01 | Receiving | RECV-ZONE | 0 |
| A-01-01 | Active Storage | STORAGE-A | 10 |
| A-01-02 | Active Storage | STORAGE-A | 20 |
| QC-01 | QC Hold | QC-ZONE | 0 |
| OUT-01 | Outbound Staging | OUT-STAGE | 0 |
| XDOCK-01 | Cross-dock Staging | XDOCK-ZONE | 0 |
| INSP-01 | Inspection | INSP-ZONE | 0 |
| QUAR-01 | Quarantine | QUAR-ZONE | 0 |

### Stap 4: Putaway Rules aanmaken

Voorbeeldregels:

| Priority | Warehouse | Customer | Item Group | Target Zone |
|---|---|---|---|---|
| 1 | WH-01 | Klant A |  | STORAGE-A |
| 2 | WH-01 | Klant B |  | STORAGE-B |
| 10 | WH-01 |  | Grondstoffen | STORAGE-RAW |
| 99 | WH-01 |  |  | STORAGE-GENERAL |

Gebruik lege velden als wildcard.

### Stap 5: ERPNext Items voorbereiden

Voor WMS beheerde artikelen:

- Zet batch tracking aan op Item.
- Gebruik batches bij Purchase Receipt, Pick List, Delivery Note en Stock Entry.
- Controleer dat ERPNext v16 Serial and Batch Bundle correct wordt aangemaakt.

---

## Voorbeeldinrichting

Onderstaand voorbeeld gebruikt alleen generieke namen.

### Warehouse

```text
WH-01
```

### Zones

```text
RECV-ZONE       Receiving
STORAGE-A       Active Storage
STORAGE-B       Active Storage
QC-ZONE         QC Hold
OUT-STAGE       Outbound Staging
XDOCK-ZONE      Cross-dock Staging
INSP-ZONE       Inspection
QUAR-ZONE       Quarantine
```

### Locaties

```text
RECV-01         Receiving             RECV-ZONE
A-01-01         Active Storage        STORAGE-A
A-01-02         Active Storage        STORAGE-A
B-01-01         Active Storage        STORAGE-B
QC-01           QC Hold               QC-ZONE
OUT-01          Outbound Staging      OUT-STAGE
XDOCK-01        Cross-dock Staging    XDOCK-ZONE
INSP-01         Inspection            INSP-ZONE
QUAR-01         Quarantine            QUAR-ZONE
```

### Artikelen en batches

```text
ITEM-A          Batch tracked item
ITEM-B          Batch tracked item
BATCH-001       Batch voor ITEM-A
BATCH-002       Batch voor ITEM-B
```

### Klanten

```text
Klant A
Klant B
```

### Inbound voorbeeld

```text
Purchase Receipt:
  ITEM-A, BATCH-001, qty 100, customer Klant A

Na submit:
  Batch Location Stock:
    ITEM-A / BATCH-001 / WH-01 / RECV-01 / qty 100 / Klant A
```

### Putaway voorbeeld

```text
Move stock:
  source: RECV-01
  target: A-01-01
  qty: 100

Na bevestiging:
  RECV-01 qty wordt 0
  A-01-01 qty wordt 100
  movement_type wordt Putaway
```

### Pick voorbeeld

```text
Pick List vraagt 40 van ITEM-A, BATCH-001.

Location Pick:
  source_location: A-01-01
  required_qty: 40
  picked_qty: 40

Na submit:
  A-01-01 qty wordt 60
  OUT-01 qty wordt 40
```

### Delivery voorbeeld

```text
Delivery Note submit voor 40 ITEM-A, BATCH-001.

Na submit:
  OUT-01 qty wordt 0
```

---

## Dashboards en rapporten

### Workspace

De WMS workspace toont:

- Shortcuts voor Location Pick, Batch Location Stock, Storage Location en WMS Cycle Count.
- KPI cards voor QC, cross-dock en actieve locaties.
- Chart `Warehouse Movements by Type`.
- Link cards voor Operations, Stock & Locations, Setup en Reports.

### Dashboard record

De app levert een Dashboard record `WMS` met:

- drie Number Cards;
- een Dashboard Chart;
- module `WMS`.

Dit zorgt ervoor dat WMS ook zichtbaar is onder Build > Dashboard.

### Number Cards

| Card | Bron | Filter |
|---|---|---|
| Pending QC Checks | WMS QC Check | `status = Pending` |
| Cross-dock Pending | WMS Cross Dock | `status = Pending` |
| Active Storage Locations | Storage Location | `is_active = 1` |

### Dashboard Chart

| Chart | Bron | Doel |
|---|---|---|
| Warehouse Movements by Type | Batch Location Movement | Aantal bewegingen per movement type. |

### Rapporten

| Rapport | Doel |
|---|---|
| Zone Occupancy | Bezetting per zone op basis van locaties, capaciteit en actuele voorraad. |
| Customer Stock Overview | Voorraad per klant, zone, warehouse, item, batch en locatie. |
| Pick Performance | Vereiste versus gepickte aantallen per Location Pick en picker. |
| Inbound Outbound Volume | Bewegingen per datum, warehouse, movement type en klant. |
| Location Pick Lines | Detailoverzicht van alle Location Pick regels. |
| Location Stock Reconciliation | Vergelijkt ERPNext voorraad met WMS locatievoorraad per item, batch en warehouse. |

### Reconciliatie rapport

`Location Stock Reconciliation` is belangrijk voor beheer. Het toont:

- ERPNext Qty;
- Location Qty;
- Difference;
- Location Breakdown.

Als `Difference` niet nul is, moet onderzocht worden of:

- een ERPNext boeking buiten WMS om is gedaan;
- een WMS cycle count correctie nodig is;
- een batch of Serial and Batch Bundle ontbreekt;
- een warehouse geen WMS locaties heeft;
- een migratie of historische boeking niet volledig is verwerkt.

---

## Installatie

Voor een normale bench installatie:

```bash
bench get-app <repository-url>
bench --site <site-name> install-app frappe_wms
bench --site <site-name> migrate
```

Voor Frappe Cloud:

1. Voeg de app toe aan de site.
2. Controleer dat de juiste branch en commit actief zijn.
3. Deploy de app.
4. Run migrate.
5. Hard refresh de browser met `Ctrl+Shift+R`.
6. Open `/desk/wms`.

Na installatie:

1. Open WMS Settings.
2. Maak WMS Zones aan.
3. Maak Storage Locations aan.
4. Maak Putaway Rules aan.
5. Controleer dat de WMS workspace zichtbaar is.
6. Test met een kleine Purchase Receipt en batch.

---

## Upgrade en migratie

Na een update:

```bash
bench --site <site-name> migrate
bench --site <site-name> clear-cache
```

De app bevat patches voor:

- aanmaken en normaliseren van WMS workspace;
- verwijderen van oude user-specifieke WMS workspace rows;
- opschonen van oude workspace link targets;
- toevoegen van Purchase Receipt custom fields;
- toevoegen van Batch customer veld;
- fasegewijze schema uitbreidingen;
- normalisatie van WMS app routing voor ERPNext/Frappe v16.

Belangrijke patch:

```text
frappe_wms.patches.v1_1.normalize_wms_v16_app_routing
```

Deze patch:

- ruimt oude workspace namen op;
- forceert de public WMS workspace naar de juiste module/app velden;
- maakt of werkt Dashboard `WMS` bij;
- wist cache na afloop.

---

## Validatie en testen

### Minimale functionele test

Voer deze test uit op een testsite of veilige omgeving.

1. Maak `WH-01` aan.
2. Maak zones en locaties aan:
   - Receiving
   - Active Storage
   - Outbound Staging
   - QC Hold
   - Cross-dock Staging
   - Quarantine
3. Zet WMS Settings aan:
   - Auto Create on Receipt
   - Validate Against ERPNext
4. Maak batch tracked item `ITEM-A`.
5. Boek een Purchase Receipt met batch `BATCH-001`.
6. Controleer Batch Location Stock op Receiving.
7. Verplaats voorraad naar Active Storage.
8. Maak Pick List.
9. Genereer Location Pick.
10. Vul picked_qty.
11. Submit Location Pick.
12. Controleer voorraad op Outbound/Picking Staging.
13. Boek Delivery Note.
14. Controleer dat stagingvoorraad is afgetrokken.
15. Open Location Stock Reconciliation.

### QC test

1. Maak Purchase Receipt Item met `wms_require_qc = 1`.
2. Submit Purchase Receipt.
3. Controleer dat voorraad in QC Hold staat.
4. Controleer dat WMS QC Check is aangemaakt.
5. Vul approved en rejected qty.
6. Submit WMS QC Check.
7. Controleer Receiving en Quarantine.

### Cross-dock test

1. Maak Purchase Receipt Item met `wms_cross_dock = 1`.
2. Koppel optioneel een Sales Order.
3. Submit Purchase Receipt.
4. Controleer WMS Cross Dock.
5. Klik Gereed voor Verzending.
6. Controleer dat voorraad naar Outbound/Picking Staging is verplaatst.

### Cycle count test

1. Maak WMS Cycle Count.
2. Kies warehouse en zones.
3. Klik Telregels Genereren.
4. Vul counted_qty afwijkend in.
5. Submit.
6. Controleer Batch Location Stock.
7. Controleer Batch Location Movement met movement type `Cycle Count`.

### Technische lokale controles

Voor ontwikkelaars:

```bash
python -m py_compile frappe_wms/hooks.py frappe_wms/wms/events/utils.py
python -m py_compile frappe_wms/wms/doctype/location_pick/location_pick.py
python -m py_compile frappe_wms/wms/doctype/batch_location_stock/batch_location_stock.py
```

Als er een bench testsite beschikbaar is:

```bash
bench --site <test-site> run-tests --app frappe_wms
```

---

## Beperkingen en aandachtspunten

### Geen volledige serial number WMS

ERPNext v16 Serial and Batch Bundle wordt gelezen om batchinformatie te vinden. De app beheert geen volledige serial number locatievoorraad als apart kernproces.

### Cycle count corrigeert WMS locatievoorraad

Cycle Count past `Batch Location Stock` aan. Financiele voorraadcorrecties moeten via ERPNext worden beheerd. Gebruik het reconciliatie rapport om verschillen te zien.

### Putaway mode is deels voorbereid

`default_putaway_mode` bevat Manual, Suggest en Enforce. De huidige UI gebruikt vooral suggesties en bevestigingen. Volledige afdwinging kan per proces verder worden uitgebreid.

### Auto cross-dock setting

`auto_create_cross_dock` bestaat als instelling. De Purchase Receipt logica detecteert cross-dock vooral via handmatige velden of bestaande PO/SO koppeling.

### Warehouse inrichting is verplicht

Zonder actieve Storage Locations per warehouse slaat WMS sommige events bewust over. Dit voorkomt dat niet-WMS warehouses onverwacht fouten geven.

### Geen standaard rollenpakket

De huidige app definieert geen uitgebreid eigen rollenmodel. Toegang loopt via standaard Frappe/ERPNext rechten op DocTypes en reports.

---

## Technische bestandsstructuur

Belangrijke bestanden en mappen:

```text
frappe_wms/
  hooks.py
  modules.txt
  patches.txt
  config/
    desktop.py
  fixtures/
    custom_field.json
    dashboard.json
    dashboard_chart.json
    number_card.json
    workspace.json
  public/
    images/
      frappe-wms-logo.svg
    js/
      batch_location_stock.js
      batch_location_stock_list.js
      location_pick.js
      pick_list.js
      purchase_receipt.js
      wms_cross_dock.js
      wms_cycle_count.js
      wms_qc_check.js
  patches/
    v1_0/
    v1_1/
  wms/
    events/
      delivery_note.py
      purchase_receipt.py
      stock_entry.py
      utils.py
    doctype/
      batch_location_movement/
      batch_location_stock/
      location_pick/
      location_pick_line/
      location_pick_source/
      storage_location/
      wms_cross_dock/
      wms_cross_dock_item/
      wms_cycle_count/
      wms_cycle_count_line/
      wms_cycle_count_zone/
      wms_putaway_rule/
      wms_qc_check/
      wms_qc_check_line/
      wms_settings/
      wms_zone/
    report/
      customer_stock_overview/
      inbound_outbound_volume/
      location_pick_lines/
      location_stock_reconciliation/
      pick_performance/
      zone_occupancy/
    workspace/
      wms/
        wms.json
```

### Hooks

`hooks.py` bevat:

- app metadata;
- app home route `/desk/wms`;
- app screen registration;
- fixtures;
- ERPNext document events;
- client scripts for ERPNext and WMS forms.

### Fixtures

Fixtures leveren:

- custom fields op Batch en Purchase Receipt Item;
- number cards;
- dashboard chart;
- dashboard record.

### Patches

Patches zorgen dat bestaande sites worden bijgewerkt zonder handmatige databasecorrecties.

---

## Ontwikkelnotities

### Naamgeving

Gebruik de documentnamen zoals ze in de app bestaan:

- `WMS`
- `WMS Zone`
- `Storage Location`
- `Batch Location Stock`
- `Batch Location Movement`
- `Location Pick`
- `WMS QC Check`
- `WMS Cross Dock`
- `WMS Cycle Count`
- `WMS Settings`

Vermijd oude of alternatieve workspacenamen. De actieve workspace hoort `WMS` te heten en via `/desk/wms` te openen.

### Data-integriteit

Bij nieuwe functionaliteit:

- Schrijf voorraadmutaties via `add_location_qty`, `deduct_location_qty` of `move_location_qty`.
- Schrijf geen directe SQL updates op `Batch Location Stock.qty` buiten gecontroleerde migraties.
- Schrijf altijd een movement audit.
- Houd ERPNext stock ledger leidend.
- Test met ERPNext v16 Serial and Batch Bundle.

### UI uitbreidingen

Bestaande client scripts gebruiken Frappe form buttons en whitelisted Python methods. Nieuwe UI-acties kunnen het beste hetzelfde patroon volgen:

```text
Form button
  -> frappe.call
  -> whitelisted method
  -> server-side validatie
  -> voorraadhelper
  -> reload form
```

---

## Licentie

MIT
