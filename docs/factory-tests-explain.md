---
# Spiegazione dei test: factory-tests-explain.md

## Scopo del File di Test
Questo file contiene test per il clustering degli ordini secondo varie regole – in particolare, verifica che il sistema di raggruppamento applichi correttamente le regole di merging di gruppi piccoli, splitting di gruppi grandi e limiti sui servizi professionali.
---

## Spiegazione delle Funzioni di Test e dei Monkey Patch

### Helper e Monkey Patch

- **\_make_order**: funzione di utilità che crea un ordine fittizio con i campi necessari (cap, prodotti, servizi).
- **\_patch_cap_lookup**: monkeypatcha la funzione `get_lat_lon_by_cap` nel modulo `utils.caps` per restituire coordinate statiche e controllate dal test.
  - **Scopo**: simulare la geolocalizzazione dei CAP senza chiamare funzioni esterne.
  - **monkeypatch**: strumento di pytest che consente di sostituire temporaneamente variabili/metodi per test isolati.

### Test sulle Factory e sulle Regole Base

- **test_clustering_rule_factory_builds_default_rules**
  - Controlla che la factory (`ClusteringRuleFactory`) includa le regole predefinite e nell'ordine atteso (merge, split, limiti servizi professionali).
- **test_build_clustered_schedule_item_groups_merges_small_groups**
  - Verifica che due ordini troppo piccoli vengano uniti in un solo gruppo. Usa monkeypatch per le coordinate CAP.
- **test_build_clustered_schedule_item_groups_splits_large_groups**
  - Verifica che i gruppi troppo grandi siano divisi secondo i parametri.
- **test_assign_orders_to_groups_preserves_delivery_assignment**
  - Controlla che l'assegnazione ai delivery users venga conservata dopo il clustering.

### Test Sui Limiti dei Servizi Professionali

- **test_professional_services_limit_rule_keeps_group_within_limit**
  - 2 ordini e 2 servizi professionali → resta un unico gruppo.
- **test_professional_services_limit_rule_splits_when_exceeds_limit**
  - 3 ordini con 3 servizi professionali diversi → suddivisione in due gruppi al massimo 2 pro per gruppo.
- **test_professional_services_limit_rule_non_professional_services_ignored**
  - Tutto non professionale: nessuna divisione.
- **test_professional_services_limit_rule_rebalances_after_uneven_split**
  - Test avanzato: molti ordini, la regola deve redistribuire i servizi professionali rispettando min/max gruppo e limite di pro per gruppo.

---

## Principali Monkey Patch Utilizzati

- Tutti i test legati ai dati geografici patchano `get_lat_lon_by_cap` per coerenza e ripetibilità.

---

## Come Estendere o Modificare Questi Test

- Definisci helpers come \_make_order per i dati.
- Usa monkeypatch per dipendenze esterne (es. funzioni geografiche).
- Modifica i parametri delle regole per esplorare nuovi edge case.

---

## Sintesi Finale

Questa suite di test garantisce che:

- Le regole siano applicate nell'ordine voluto dalla factory.
- I limiti di dimensione dei gruppi e le regole professionali siano sempre rispettati.
- Gli edge case (ad es. mix di molti ordini pro/non pro) siano gestiti robustamente.

---
