---
## Come Funzionano le Factory Rules
- Il dataclass `ClusteringRuleFactory` contiene una tupla `rules`, che elenca le classi delle regole da usare:
    
    rules: tuple[type[ClusteringRule], ...] = (
      MergeSmallGroupsRule,
      SplitLargeGroupsRule,
      ProfessionalServicesLimitRule,
    )
    
    - L'ordine è FONDAMENTALE: le regole vengono applicate in questa sequenza.
- Il metodo `.build()` restituisce un'istanza di ciascuna classe di regole, in ordine.

### Utilizzo nella Pipeline
- `ScheduleClusteringPipeline` (vedere il metodo `.cluster()`) riceve la factory e chiama `.build()` per ottenere la lista di regole.
- In `.cluster()`:
    
    for rule in self.rule_factory.build():
      schedule_item_groups = rule.apply(schedule_item_groups, context)
    
    Ogni metodo `apply` di una regola viene chiamato nell'ordine definito dalla factory.

---

## Come Impostare/Cambiare la Priorità tra le Regole

La priorità/l’ordine delle regole è determinata dalla posizione nella tupla `rules` dentro `ClusteringRuleFactory`.

- La prima regola nella tupla viene applicata per prima, la seconda dopo, ecc.
- Per modificare quale regola ha "priorità più alta", basta spostarla in una posizione precedente nella tupla.
- Esempio: se vuoi che `ProfessionalServicesLimitRule` sia applicata per prima, scrivi:
  rules: tuple[type[ClusteringRule], ...] = (
  ProfessionalServicesLimitRule,
  MergeSmallGroupsRule,
  SplitLargeGroupsRule,
  )
  - La “priorità” è codificata tramite l’ordine—non esiste un campo di priorità numerica o un peso: conta solo l’ordine da sinistra a destra nella lista.

---

## Tabella Riassuntiva

| Priorità/Ordine | Nome Regola                   | Descrizione (dedotta dal nome)                     |
| :-------------: | :---------------------------- | :------------------------------------------------- |
|   1 (Massima)   | MergeSmallGroupsRule          | Probabile fusione di gruppi troppo piccoli         |
|        2        | SplitLargeGroupsRule          | Probabile divisione di gruppi troppo grandi        |
|   3 (Minima)    | ProfessionalServicesLimitRule | Probabile applicazione di vincoli su servizi prof. |

- Più alta è la posizione nella lista = eseguita prima (priorità maggiore).

---

## Come aggiungere Nuove Regole o Cambiare Priorità

- Per AGGIUNGERE una regola: importala e inserisci la classe della regola nella tupla `rules`, nella posizione desiderata rispetto alla priorità voluta.
- Per RIMUOVERE o RIORDINARE: modifica semplicemente la tupla `rules` di conseguenza.

---

## File e Classi Chiave Coinvolte

- `src/schedulation/clustering.py`
  - `ClusteringRuleFactory`
  - `ScheduleClusteringPipeline`
  - Le classi delle regole sono importate dai sottopacchetti `clustering_rules`

---

## In sintesi

La "priorità" tra le regole è controllata semplicemente dall’ordine nella tupla `rules` all’interno di `ClusteringRuleFactory` in `src/schedulation/clustering.py`. Le regole vengono applicate in sequenza: la prima nella tupla ha la priorità più alta. Modifica quest’ordine per cambiare la priorità/regola applicata prima.
