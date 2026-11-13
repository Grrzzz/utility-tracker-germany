# Utility Tracker Germany

HACS-Integration (Domain `utility_tracker_germany`) fuer Strom, Gas und Wasser: Abschlag vs. tatsaechliche Kosten.

## Sensoren je Instanz
- **Plan**: aufgelaufene Abschlaege (Laufzeit-begrenzt)
- **Ist**: Arbeitspreis x Verbrauch + anteiliger Grundpreis; nach Vertragsende eingefroren (optional Endzaehlerstand)
- **Guthaben** = Plan - Ist (positiv = Guthaben)
- **Restlaufzeit** (Tage bis Vertragsende)
- **Tarif** (aktueller Tarif, Attribute mit allen Perioden)
- **Abschlagsdeckung** (Prognose Ist am Vertragsende / Plan, in %)
- Wasser zusaetzlich Ist Bezug / Ist Abwasser

## Struktur
- `calc.py`: reine Berechnung (ohne HA-Imports), Test: `python tests_calc.py`
- `config_flow.py`: 2-Schritt-Assistent (Vertrag, Preise je Typ) und Options-Flow (Vertragsuebersicht, Vertragsanpassung, Vertrag loeschen). Modell: ein Tracker hat mehrere Vertraege (`options['contracts']`, siehe `contracts.py`), je Vertrag ein Tarif; Sensoren nutzen den laufenden Vertrag. Alte Eintraege (flache data/options) werden beim Lesen zu Vertrag 1 migriert
- `sensor.py`, `const.py`, `translations/{de,en}.json`

## Regeln
- Keine persoenlichen Daten (Namen, Entity-IDs, Zaehlerstaende, Tokens) im Repo.
- Release: Version in `manifest.json` erhoehen, neuer Tag `vX.Y.Z` (Workflow baut die ZIP).
- Release: Jedes Release braucht ein ordentlich geschriebenes, gut lesbares Changelog (Funktionen und Aenderungen in verstaendlicher Sprache, Englisch). Keine Code-Changes, keine Commit-Listen. Der Workflow nutzt dazu RELEASE_NOTES.md (vor jedem Tag aktualisieren), niemals auto-generierte Notes.
- Release-Texte im Stil der AI-on-the-edge-device-Releases: Kurzzeile, ### What is new (fette Stichworte, Nutzersicht), ### Installation.
