-- Listino MediaMarket per l'attivita' 2, applicato ai punti vendita 71-75.
-- Generato da scripts/mediamarket_services_import.py (stessi dati, stessa logica):
-- questa e' la versione da incollare in psql quando non si vuole far girare lo script.
--
-- Idempotente: crea solo i servizi che nella company 2 non esistono gia' (match sul
-- nome, trascritto alla lettera dall'Excel), crea solo le associazioni mancanti e
-- riallinea codice e prezzo di quelle gia' presenti.
--
-- Tutto dentro una transazione: se una precondizione non regge, il DO solleva
-- l'eccezione, la transazione si aborta e non resta niente a meta'.

BEGIN;

CREATE TEMP TABLE listino_mediamarket (code text, name text, price double precision) ON COMMIT DROP;

INSERT INTO listino_mediamarket (code, name, price) VALUES
  ('109532', 'STAND TV* – INSTALLAZIONE STAND (consegna e installazione)< 55”', 27),
  ('109534', 'WALL TV* – INSTALLAZIONE WALL TV (consegna e installazione)<55”', 35),
  ('109560', 'SUPPLEMENTO SOUNDBAR x codici ***', 10),
  ('109561', 'SUPPLEMENTO TV GRANDI DIMENSIONI TV ≥ 55’’ e TV ≤ 80” x codici ***', 15),
  ('109562', 'SUPPLEMENTO EXPRESS TV x codici ***', 15),
  ('123619', 'MONTAGGIO KIT COLONNA BUCATO', 10),
  ('123620', 'CONSEGNA COMFORT PLUS FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 27),
  ('126930', 'SUPPLEMENTO COMFORT PLUS x codici ** (Escluso cod.123620)', 2),
  ('156452', 'ALLACCIAMENTO FILTRO ANTI CALCARE', 1.5),
  ('177583', 'CONSEGNA COMFORT (24) FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 27),
  ('204308', 'CONSEGNA COMFORT (48) FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 27),
  ('323299', 'DISINCASSO senza nuovo incasso (e ritiro)', 15),
  ('405322', 'SUPPLEMENTO TV GRANDI DIMENSIONI TV > 80’’ x codici *** Vedi dettaglio capitolato', 35),
  ('550450', 'CONSEGNA EXPRESS FASCIA 1* (consegna 18-21 lo stesso giorno dell’acquisto) inclusiva di allacciamento', 40),
  ('612785', 'SOSTITUZIONE UGELLI (solo servizio di sostituzione ugelli senza alcuna installazione)', 20),
  ('612825', 'INCASSO PIANO COTTURA/FORNO A GAS E CERTIFICAZIONE (senza consegna)', 35),
  ('612887', 'INCASSO PIANO COTTURA/FORNO/CUCINE A GAS CON CONSEGNA E CERTIFICAZIONE', 40),
  ('612921', 'SMONTAGGIO COLONNE FRIGO INCASSO (con consegna nuovo prodotto)', 40),
  ('629813', 'INCASSO PRODOTTI GE – Frigoriferi, Lavelli, Cappe libero posizionamento (con consegna)', 35),
  ('629814', 'INCASSO PRODOTTI GE – Lvs,Lvb, Cappe incas, Forni elett., P. cottura induzione (con consegna)', 35),
  ('629815', 'SOPRALLUOGO per installazioni professionali (senza consegna)', 20),
  ('629816', 'ALLACCIAMENTO RETE IDRICA/ELETTRICA PRODOTTI GRANDI DIMENSIONI (con consegna)', 40),
  ('629817', 'INSTALLAZIONE HOME A/V BASE 3.1 (con consegna)', 30),
  ('629818', 'INSTALLAZIONE HOME A/V FULL 5.1 con canalizzazione esterna (con consegna)', 40),
  ('629819', 'KIT INSTALLAZIONE 2 PRODOTTI DA INCASSO (di cui 1 è un frigo, tutto con consegna)', 55),
  ('630528', 'KIT INSTALLAZIONE 2 PRODOTTI DA INCASSO (no frigo, tutto con consegna)', 55),
  ('651409', 'CONSEGNA BASIC 24H FASCIA 1* (cons. 9-13/14-18 giorno seguente acquisto - ESCLUSI PDT GE e TV >32”)', 15),
  ('707296', 'CONSEGNA COMFORT FASCIA 1* (consegna 9-13/14-18 il giorno seguente all’acquisto) inclusiva di allacciamento', 25),
  ('707298', 'CONSEGNA SERALE FASCIA 1* (consegna 18-21) inclusiva di allacciamento', 28),
  ('723111', 'SUPPLEMENTO GRANDI DIMENSIONI (Combinati-Coreani >400 lt) x codici **', 15),
  ('723112', 'SUPPLEMENTO GRANDI DIMENSIONI FRIGO SIDE BY SIDE/AMERICANI x codici **', 20),
  ('737106', 'INSTALLAZIONE SMART TV (con consegna)', 40),
  ('752267', 'CONSEGNA FASCIA 1* SU APPUNTAMENTO AD ORARIO PREDEFINITO (slot di 1 ora) inclusiva di allacciamento', 30),
  ('20250188', 'CONSEGNA PRODOTTO SUCCESSIVO', 11),
  ('21250224', 'CONSEGNA E ALLACCIAMENTO EXTRA DIMENSIONI (es. Washtower)', 50),
  ('22250209', 'SOPRALLUOGO per consegne e allacciamenti particolari', 18),
  ('23250161', 'CONSEGNA STANDARD FASCIA 1* (consegna 9-13/14-18) senza allacciamento', 22),
  ('23250161', 'RICONSEGNA PER CAUSE INDIPENDENTI DALL’APPALTATORE - (Equivalente al “solo Trasporto”)', 19),
  ('24250191', 'SUPPLEMENTO CONSEGNA FASCIA 2 (in aggiunta a codici CONSEGNA** x distanze da 51 - a 70 km)', 8),
  ('27250174', 'ALLACCIAMENTO PRODOTTO', 3),
  ('28250159', 'INVERSIONE PORTE FRIGORIFERO', 20),
  ('RAEE Trasf', 'Ritiro 1:1 - Trasporto RAEE da PV a LdR/CdR (Se trasporto dedicato) a Bancale', 15),
  ('TCO70', 'TARIFFA CONSEGNA OLTRE I Km 70 Solo Andata', 0.5);


-- Precondizioni: company esistente, i cinque punti vendita esistono, stanno nella
-- company 2 e sono Customer.
DO $$
DECLARE
  invalid text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM company WHERE id = 2) THEN
    RAISE EXCEPTION 'Company 2 inesistente';
  END IF;

  SELECT string_agg(wanted.id::text, ', ') INTO invalid
  FROM (VALUES (71), (72), (73), (74), (75)) AS wanted(id)
  WHERE NOT EXISTS (
    SELECT 1 FROM "user" u WHERE u.id = wanted.id AND u.company_id = 2 AND u.role = 'CUSTOMER'
  );

  IF invalid IS NOT NULL THEN
    RAISE EXCEPTION 'Utenti non utilizzabili (assenti, di altra company o non Customer): %', invalid;
  END IF;

  IF EXISTS (SELECT 1 FROM listino_mediamarket GROUP BY name HAVING count(*) > 1) THEN
    RAISE EXCEPTION 'Nomi duplicati nel listino: a database non sarebbero distinguibili';
  END IF;
END
$$;


-- 1. Servizi mancanti nella company 2.
INSERT INTO service (name, type, professional, company_id, created_at, updated_at)
SELECT l.name, 'DELIVERY'::ordertype, false, 2, now(), now()
FROM listino_mediamarket l
WHERE NOT EXISTS (SELECT 1 FROM service s WHERE s.company_id = 2 AND s.name = l.name);


-- 2. Associazioni mancanti: stesso prezzo per tutti e cinque i punti vendita.
INSERT INTO service_user (code, price, user_id, service_id, company_id, created_at, updated_at)
SELECT l.code, l.price, pv.id, s.id, 2, now(), now()
FROM listino_mediamarket l
JOIN service s ON s.company_id = 2 AND s.name = l.name
CROSS JOIN (VALUES (71), (72), (73), (74), (75)) AS pv(id)
WHERE NOT EXISTS (
  SELECT 1 FROM service_user su WHERE su.user_id = pv.id AND su.service_id = s.id
);


-- 3. Riallineamento di codice e prezzo dove l'associazione esisteva gia'.
UPDATE service_user su
SET code = l.code, price = l.price, updated_at = now()
FROM listino_mediamarket l, service s
WHERE s.company_id = 2
  AND s.name = l.name
  AND su.service_id = s.id
  AND su.user_id IN (71, 72, 73, 74, 75)
  AND (su.code IS DISTINCT FROM l.code OR su.price IS DISTINCT FROM l.price);


-- Verifica: 43 servizi e 215 associazioni (43 x 5), una riga per punto vendita.
SELECT u.id, u.nickname, count(*) AS associazioni, sum(su.price) AS totale_listino
FROM service_user su
JOIN "user" u ON u.id = su.user_id
JOIN service s ON s.id = su.service_id
JOIN listino_mediamarket l ON l.name = s.name AND l.code = su.code AND l.price = su.price
WHERE su.company_id = 2 AND su.user_id IN (71, 72, 73, 74, 75)
GROUP BY u.id, u.nickname
ORDER BY u.id;

COMMIT;
