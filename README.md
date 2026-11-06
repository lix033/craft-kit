# craftkit

> **In English:** `craft` rebuilds any software (website, CLI, app, game, library) with the coding
> agent you already use (Claude Code, Codex, Gemini CLI): it studies the original, briefs the agent,
> checks the result against the original and sends it back until it holds. Install with
> `npm install -g craftkit-cli` or `pipx install craftkit`, then type `craft`.

La méthode de Craft Anything, réduite à l'essentiel : **étudier → construire → vérifier → affiner**,
pour recréer ou construire n'importe quel logiciel (site web, outil en ligne de commande, application,
jeu, librairie), depuis le terminal.

Deux façons de l'utiliser :

1. **Le skill** (`craft_kit/SKILL.md`) : la méthode seule, en Markdown. N'importe quel agent de code
   (Claude Code, Codex, Gemini CLI, Cursor…) peut la suivre, avec ou sans la CLI.
2. **La CLI `craft`** : la même méthode, outillée. Elle tient le dossier du projet, collecte les
   preuves, donne la tâche à un agent de code, mesure le résultat et relance l'agent jusqu'à ce que
   ça passe. Python 3.9+, **aucune dépendance**.

```text
 craft · horloge-pomodoro                        cli · Rust · clean room
 ▍study  ./pomodoro ────────────────────────────────────────────────
 ✓ runs    4 runs recorded
 ▍build  building · turn 1 ─────────────────────────────────────────
   0:03 ◇ read   BRIEF.md
   0:05 ☰ plan   2/5 · Writing the timer
   0:41 ✚ write  app/src/main.rs
   1:02 ❯ run    cargo build
   1:20 ✗ failed error[E0425]: cannot find value `paused`
   1:31 ✎ edit   app/src/main.rs
   └ 2m14s · 14 actions: 6 edit, 4 run, 3 read, 1 plan · 1 failed
 ✓ build   I built the timer with pause and resume.
 ▍check  round 1 ───────────────────────────────────────────────────
 ✗ runs    6 of 8 claims hold; output 71% alike.
   │ With --help, it prints what the original prints: 52% of the words match
 ▍refine  refining 1/6 · turn 2 ────────────────────────────────────
   ⠼ refining 1/6 · claude · 0m48s · 3 · Edit app/src/main.rs
```

Pendant le travail, chaque action de l'agent s'affiche en direct (lecture, écriture, commande,
recherche, plan, échec), chacune avec sa couleur, et chaque étape a la sienne : étude bleu ciel,
construction bleu, affinage violet, vérification ambre, prêt vert.

## Installation

Gratuit, au choix :

```sh
npm install -g craftkit-cli   # avec Node ; il faut aussi Python 3.9+ sur la machine
pipx install craftkit             # ou : uv tool install craftkit
```

Pour l'essayer sans rien installer : `npx craftkit-cli` ou `uvx craftkit`.
Ensuite, le skill pour Claude Code (tous les projets) : `craft skill --install ~/.claude/skills`.

Les deux paquets contiennent exactement le même programme Python (aucune dépendance) ; celui de npm
le lance avec le Python de la machine (`CRAFT_PYTHON=/chemin/vers/python3` pour en choisir un).
Mise à jour : `npm update -g craftkit-cli`, `pipx upgrade craftkit` ou `uv tool upgrade craftkit`.

Depuis les sources : `pipx install .` dans ce dossier, ou `python3 -m craft_kit …` sans installer.

Optionnel, pour les sites web : un navigateur pour les captures. La CLI prend, dans l'ordre,
Playwright pour Python (`pip install playwright && playwright install chromium`, qui ajoute les
mesures visibles : polices, couleurs, titres, texte), sinon Chrome/Edge installé (en mode headless,
avec un profil temporaire), sinon Playwright via `npx`.

## Utilisation

Tapez simplement **`craft`** : l'écran d'accueil affiche le titre CRAFT KIT, vos créations
précédentes et « + New project ».

| Touche | Action |
|--------|--------|
| ↑ ↓ (ou j k) | se déplacer |
| Entrée | ouvrir le projet : continuer, demander un changement, ouvrir le résultat, revérifier, voir le dossier |
| n | nouveau projet (quelques questions, créé dans `~/craft-projects`, ou `CRAFT_PROJECTS_DIR`) |
| x | retirer de la liste (le dossier n'est pas supprimé) |
| q / Échap | retour, ou quitter |

La liste contient tous les projets créés ou ouverts avec `craft` (mémorisés dans
`~/.config/craft/projects.json`), plus ceux du dossier courant.

Raccourcis : `craft-new …` = `craft new …`, `craft-run …` = `craft run …`.

En ligne de commande directe :

```sh
craft new https://exemple.com "recrée ce site en React"   # crée ./recree-ce-site-en-react/
cd recree-ce-site-en-react
craft run                                   # toute la boucle
craft run "le bouton doit être bleu"        # une modification (nouveau budget d'affinage)
craft open                                  # ouvrir le résultat
```

| Commande | Rôle |
|----------|------|
| `craft new [CIBLE] [DEMANDE…]` | crée le projet ; demande ce qui manque. CIBLE = URL, fichier, dossier, commande du PATH, ou rien |
| `craft run [MESSAGE…]` | étude (si pas faite) → construction → vérification → affinage, jusqu'à la réussite |
| `craft study` / `build` / `check` | une étape à la fois |
| `craft check --self` | la vérification que l'agent lance lui-même pendant qu'il travaille (non comptée) |
| `craft` | écran d'accueil : créations précédentes, nouveau projet |
| `craft status` | où en est le projet |
| `craft answer` | répondre aux questions de l'agent |
| `craft brief` | afficher la tâche, pour la coller dans n'importe quel agent |
| `craft agents` | les agents de code installés, et comment en installer un |
| `craft skill [--install DOSSIER]` | afficher ou installer le SKILL.md |

Options de `new` : `--kind website|cli|app|game|tool`, `--stack rust|python|react|html|…`,
`--deep` (regarder à l'intérieur de l'original, usage privé), `--allow-run` (lancer le programme
d'origine pour enregistrer ce qu'il affiche), `--dir`.

## Ce que la CLI reprend de Craft Anything

| Craft Anything | craft-kit |
|----------------|-----------|
| Clean room / Deep | même règle : par défaut, seulement ce qu'un visiteur voit ; `--deep` pour regarder dedans |
| Study → `capture/README.md` | captures à 1440/768/390 px + mesures visibles ; exécutions d'un CLI ; inventaire en Deep |
| Le builder ne touche que `app/` | idem, et `app/craft-app.json` déclare build/test/run |
| `rebuild_check` pendant la construction | `craft check --self` |
| Contrats `--screenshot` / `--self-test` | identiques (applis et jeux) |
| Comparaison des runs d'un programme console | même code de sortie + ≥ 80 % de mots communs |
| `max_rounds` 6, `good_enough` 90 %, arrêt après 2 tours sans changement | identiques ; le budget survit aux relances, seule une nouvelle demande le remet à zéro |
| Cartes question/approbation | `questions.json` → questions numérotées dans le terminal |
| Inconnues (`core_unknown_add`) | `unknowns.md` |
| Processus : stdin fermé, délais, groupe tué | idem (`proc.py`) |

Ce qu'elle ne reprend pas : les ~320 outils d'analyse (désassembleur, décompilateur, Ghidra, adb,
Frida…), l'interface graphique et le serveur MCP. En mode Deep, c'est l'agent qui inspecte avec ses
propres outils.

## Agents

`craft` n'écrit pas le code lui-même : il faut un agent de code sur la machine. Sans agent, `craft`
le dit dès l'écran d'accueil, à `craft new` et au début de `craft run` (avant l'étude), avec les
commandes exactes ; `craft agents` montre ce qui est trouvé :

| Agent | Installer | Puis, une fois |
|-------|-----------|----------------|
| Claude Code | `npm install -g @anthropic-ai/claude-code` (ou `curl -fsSL https://claude.ai/install.sh \| bash`) | lancer `claude` et se connecter |
| Codex | `npm install -g @openai/codex` | lancer `codex` et se connecter |
| Gemini CLI | `npm install -g @google/gemini-cli` (ou `brew install gemini-cli`) | lancer `gemini` et se connecter (offre gratuite avec un compte Google) |

Sans agent du tout : `craft brief` affiche la tâche, à coller dans n'importe quel assistant de code
(Cursor, Copilot…) ouvert dans le dossier du projet, puis `craft check`.

Ordre par défaut : `claude`, `codex`, `gemini` (le premier installé). Choisir : `--agent codex` ou
`CRAFT_AGENT=codex`. La tâche est envoyée sur l'entrée standard (jamais en argument : elle peut être
longue). Ajouter ou modifier un agent dans `~/.config/craft/agents.json` :

```json
{"mon-agent": {"argv": ["mon-agent", "--non-interactive"], "stream": "text"}}
```

Claude Code est lancé avec `--permission-mode acceptEdits` et une liste d'outils autorisés
(lecture/écriture, npm, cargo, go, python, make, craft…), pas en contournant les permissions.

Délais : `CRAFT_TURN_TIMEOUT` (3 h par tour), `CRAFT_IDLE_TIMEOUT` (20 min sans sortie).
Navigateur : `CRAFT_BROWSER=python|chrome|npx|none`, `CRAFT_CHROME=/chemin/vers/chrome`.
Affichage : `CRAFT_FEED=0` garde seulement la ligne animée (sans le fil d'actions) ; `NO_COLOR=1`
retire les couleurs. Hors terminal (pipe, CI), le fil s'écrit en texte simple, une ligne par action.

## Limites connues

- La comparaison visuelle est une grille de couleurs (64 colonnes, tolérance 32) : elle repère les
  écarts de mise en page et de couleur, pas les détails fins.
- Avec Chrome headless, la capture fait 2400 px de haut, pas la page entière ; les mesures visibles
  (polices, titres, texte) demandent Playwright pour Python.
- Les adaptateurs `codex` et `gemini` n'ont pas été essayés en vrai.
